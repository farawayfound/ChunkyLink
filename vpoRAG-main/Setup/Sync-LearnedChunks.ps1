# Setup/Sync-LearnedChunks.ps1
# Pushes locally-learned chunks to the MCP server via the server-side learn engine.
# Each chunk passes through the full pipeline (Gate 1 + Gate 2 + merge) on the server,
# so near-duplicates and already-merged chunks are never re-appended.
#
# Usage:
#   .\Setup\Sync-LearnedChunks.ps1              # dry-run: show pending chunks, no push
#   .\Setup\Sync-LearnedChunks.ps1 -Push        # push pending chunks through server engine
#   .\Setup\Sync-LearnedChunks.ps1 -Push -Force # re-push all chunks (ignore synced marker)

param(
    [switch]$Push,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Load config --------------------------------------------------------------
$configPath = Join-Path $PSScriptRoot "..\Searches\config.ps1"
if (-not (Test-Path $configPath)) {
    Write-Error "config.ps1 not found at $configPath"
    exit 1
}
. $configPath

$sshKey    = if ($MCP_SSH_KEY)  { $MCP_SSH_KEY  } else { Join-Path $HOME ".ssh\vporag_key" }
$sshUser   = if ($MCP_SSH_USER) { $MCP_SSH_USER } else { "vpomac" }
$sshServer = $JIRA_REMOTE_MYSQL_HOST
$SshHost   = "${sshUser}@${sshServer}"
$sshArgs   = @("-i", $sshKey, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2")

$LocalDir     = Join-Path $JSON_KB_DIR "detail"
$LocalLearned = Join-Path $LocalDir "chunks.learned.jsonl"

$RemoteBatchScript = "/tmp/learn_sync_batch.py"
$RemoteBatchInput  = "/tmp/sync_batch.jsonl"
$RemoteVenv        = "/srv/vpo_rag/venv/bin/python"

# -- Validate local file ------------------------------------------------------
if (-not (Test-Path $LocalLearned)) {
    Write-Host "No local chunks.learned.jsonl found - nothing to sync." -ForegroundColor Yellow
    exit 0
}

$localLines = @(Get-Content $LocalLearned -Encoding UTF8 | Where-Object { $_.Trim() })
if ($localLines.Count -eq 0) {
    Write-Host "Local chunks.learned.jsonl is empty - nothing to sync." -ForegroundColor Yellow
    exit 0
}

# -- Identify pending chunks --------------------------------------------------
# Pending = source is "local" (not yet synced) or -Force is set
$pendingChunks = @()
foreach ($line in $localLines) {
    try {
        $rec = $line | ConvertFrom-Json
        $src = $rec.metadata.source
        if ($Force -or $src -eq "local" -or -not $src) {
            $pendingChunks += $line
        }
    } catch {
        Write-Warning "Skipping malformed line: $($line.Substring(0, [Math]::Min(80,$line.Length)))..."
    }
}

if ($pendingChunks.Count -eq 0) {
    Write-Host "No pending chunks to sync (all marked source=synced). Use -Force to re-push all." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "Pending chunks: $($pendingChunks.Count)" -ForegroundColor Cyan
foreach ($line in $pendingChunks) {
    try {
        $rec = $line | ConvertFrom-Json
        $ts  = if ($rec.metadata.session_ts) { $rec.metadata.session_ts.Substring(0,19) } else { "?" }
        $ttl = if ($rec.metadata.title) { $rec.metadata.title.Substring(0,[Math]::Min(60,$rec.metadata.title.Length)) } else { $rec.id }
        Write-Host "  [$ts] $ttl" -ForegroundColor White
    } catch {
        Write-Host "  (unparseable)" -ForegroundColor DarkGray
    }
}

if (-not $Push) {
    Write-Host ""
    Write-Host "Dry run - use -Push to sync through the server engine." -ForegroundColor Yellow
    exit 0
}

# -- SCP batch script and input to server -------------------------------------
Write-Host ""
Write-Host "Uploading batch to server..." -ForegroundColor Cyan

$localBatchScript = Join-Path $PSScriptRoot "..\mcp_server\scripts\learn_sync_batch.py"
if (-not (Test-Path $localBatchScript)) {
    Write-Error "learn_sync_batch.py not found at $localBatchScript"
    exit 1
}

$tmpBatch = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllLines($tmpBatch, $pendingChunks,
        [System.Text.UTF8Encoding]::new($false))

    $scriptSrc = (Resolve-Path $localBatchScript).Path -replace '\\', '/'
    scp @sshArgs $scriptSrc "${SshHost}:${RemoteBatchScript}" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Error "SCP of batch script failed"; exit 1 }

    $batchSrc = $tmpBatch -replace '\\', '/'
    scp @sshArgs $batchSrc "${SshHost}:${RemoteBatchInput}" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Error "SCP of batch input failed"; exit 1 }
} finally {
    Remove-Item $tmpBatch -ErrorAction SilentlyContinue
}

# -- Run batch on server as vporag --------------------------------------------
$chunkWord = if ($pendingChunks.Count -eq 1) { "chunk" } else { "chunks" }
Write-Host "Running engine on server ($($pendingChunks.Count) $chunkWord)..." -ForegroundColor Cyan

$secretsPath = Join-Path $PSScriptRoot "secrets.env"
$sudoPass = ""
if (Test-Path $secretsPath) {
    Get-Content $secretsPath | ForEach-Object {
        if ($_ -match '^MCP_SUDO_PASS=(.+)$') { $sudoPass = $Matches[1].Trim() }
    }
}
if (-not $sudoPass) { Write-Error "MCP_SUDO_PASS not found in Setup/secrets.env"; exit 1 }

$remoteCmd = "echo $sudoPass | sudo -S -u vporag $RemoteVenv $RemoteBatchScript $RemoteBatchInput 2>/dev/null"
$rawOutput = ssh @sshArgs $SshHost $remoteCmd 2>&1

if ($LASTEXITCODE -ne 0 -or -not $rawOutput) {
    Write-Error "Server batch run failed. Output: $rawOutput"
    exit 1
}

# -- Parse results ------------------------------------------------------------
# Strip sudo/warning lines before the JSON array
$jsonLine = ($rawOutput -split "`n" | Where-Object { $_.Trim().StartsWith("[") } | Select-Object -Last 1)
if (-not $jsonLine) {
    Write-Error "Could not parse server response. Raw output:`n$rawOutput"
    exit 1
}

try {
    $results = $jsonLine | ConvertFrom-Json
} catch {
    Write-Error "Failed to parse server JSON: $_`nRaw: $jsonLine"
    exit 1
}

# -- Report results -----------------------------------------------------------
$countOk        = 0
$countMerged    = 0
$countDuplicate = 0
$countRejected  = 0
$countError     = 0
$syncedIds      = @{}

foreach ($r in $results) {
    $status  = $r.status
    $localId = $r.local_id

    switch ($status) {
        "ok"        { $countOk++;        $label = "[SAVED   ]"; $color = "Green"    }
        "merged"    { $countMerged++;    $label = "[MERGED  ]"; $color = "Cyan"     }
        "duplicate" { $countDuplicate++; $label = "[SKIP-DUP]"; $color = "DarkGray" }
        "rejected"  { $countRejected++;  $label = "[REJECTED]"; $color = "Yellow"   }
        default     { $countError++;     $label = "[ERROR   ]"; $color = "Red"      }
    }

    $detail = switch ($status) {
        "ok"        { "chunk_id=$($r.chunk_id)" }
        "merged"    { "into=$($r.chunk_id) sim=$($r.similarity)" }
        "duplicate" { "existing=$($r.existing_chunk_id) sim=$($r.similarity)" }
        "rejected"  { "reason=$($r.reason)" }
        default     { if ($r.reason) { $r.reason } elseif ($r.error) { $r.error } else { "unknown" } }
    }

    Write-Host "  $label $localId - $detail" -ForegroundColor $color

    if ($status -in @("ok","merged") -and $localId) {
        $syncedIds[$localId] = $true
    }
}

Write-Host ""
Write-Host "Sync complete: $countOk saved, $countMerged merged, $countDuplicate duplicate, $countRejected rejected, $countError error" -ForegroundColor Green

# -- Update local file: mark synced chunks ------------------------------------
if ($syncedIds.Count -gt 0) {
    $updatedLines = @()
    foreach ($line in $localLines) {
        try {
            $rec = $line | ConvertFrom-Json
            if ($syncedIds.ContainsKey($rec.id)) {
                $rec.metadata.source = "synced"
                $updatedLines += ($rec | ConvertTo-Json -Compress -Depth 10)
            } else {
                $updatedLines += $line
            }
        } catch {
            $updatedLines += $line
        }
    }
    [System.IO.File]::WriteAllLines($LocalLearned, $updatedLines,
        [System.Text.UTF8Encoding]::new($false))
    Write-Host "Local file updated: $($syncedIds.Count) chunk(s) marked source=synced." -ForegroundColor Cyan
}

# -- Cleanup remote temp files ------------------------------------------------
ssh @sshArgs $SshHost "rm -f $RemoteBatchScript $RemoteBatchInput" 2>&1 | Out-Null
