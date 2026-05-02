# Searches/Scripts/Sync-JSONIndex.ps1
# Syncs local JSON/detail from the MCP server if the remote index is more recently updated.
# All connection settings are read from Searches/config.ps1 - nothing is hardcoded.

param(
    [string]$RemoteDir = "/srv/vpo_rag/JSON/detail",
    [switch]$Force
)

# -- Load config.ps1 ----------------------------------------------------------
$configPath = Join-Path $PSScriptRoot "..\Searches\config.ps1"
if (-not (Test-Path $configPath)) {
    Write-Error "config.ps1 not found at $configPath - copy from config.example.ps1 and configure."
    exit 1
}
. $configPath

# -- Derive settings from config ----------------------------------------------
if (-not $JSON_KB_DIR) {
    Write-Error "JSON_KB_DIR is not set in config.ps1"
    exit 1
}
$LocalDir = Join-Path $JSON_KB_DIR "detail"

# SSH connection: host from $JIRA_REMOTE_MYSQL_HOST, user/key from $MCP_SSH_USER / $MCP_SSH_KEY
$sshServer = $JIRA_REMOTE_MYSQL_HOST
$sshUser   = if ($MCP_SSH_USER) { $MCP_SSH_USER } else { "vpomac" }
$sshKey    = if ($MCP_SSH_KEY)  { $MCP_SSH_KEY  } else { Join-Path $HOME ".ssh\vporag_key" }
$SshHost   = "${sshUser}@${sshServer}"

if (-not (Test-Path $sshKey)) {
    Write-Error "SSH key not found at $sshKey - run Ansible\MCP\setup_ssh_key.ps1 first."
    exit 1
}

$sshArgs = @("-i", $sshKey, "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes")

# -- Get newest mtime across all *.jsonl files on the remote ------------------
Write-Host "Checking remote index timestamp at ${SshHost}:${RemoteDir} ..."
$remoteTs = ssh @sshArgs $SshHost "find '$RemoteDir' -name '*.jsonl' -printf '%T@\n' 2>/dev/null | sort -n | tail -1"

if ($LASTEXITCODE -ne 0 -or -not $remoteTs) {
    Write-Error "Could not reach remote server or no JSONL files found at $RemoteDir"
    exit 1
}
$remoteTime = [DateTimeOffset]::FromUnixTimeSeconds([long][double]$remoteTs).LocalDateTime
Write-Host "  Remote newest file: $remoteTime"

# -- Get newest mtime across all local *.jsonl files --------------------------
$localTime = $null
if (Test-Path $LocalDir) {
    $newest = Get-ChildItem -Path $LocalDir -Filter "*.jsonl" -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) { $localTime = $newest.LastWriteTime }
}
Write-Host "  Local  newest file: $(if ($localTime) { $localTime } else { '(none)' })"

# -- Decide whether to sync ---------------------------------------------------
if (-not $Force -and $localTime -and $localTime -ge $remoteTime) {
    Write-Host "Local index is up to date. No sync needed." -ForegroundColor Green
    exit 0
}

$reason = if ($Force) { "forced" } elseif (-not $localTime) { "no local index" } else { "remote is newer" }
Write-Host "Syncing ($reason) ..." -ForegroundColor Cyan

# -- Ensure local dir exists --------------------------------------------------
if (-not (Test-Path $LocalDir)) { New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null }

# -- Copy each category file via scp ------------------------------------------
$remoteFiles = ssh @sshArgs $SshHost "ls '$RemoteDir'/chunks.*.jsonl 2>/dev/null"
if ($LASTEXITCODE -ne 0 -or -not $remoteFiles) {
    Write-Error "No category JSONL files found on remote."
    exit 1
}

$files  = $remoteFiles -split "`n" | Where-Object { $_.Trim() }
$copied = 0
$failed = 0

foreach ($remoteFile in $files) {
    $remoteFile = $remoteFile.Trim()
    $fileName   = Split-Path $remoteFile -Leaf
    $localFile  = Join-Path $LocalDir $fileName

    Write-Host "  Copying $fileName ..." -NoNewline
    scp @sshArgs "${SshHost}:${remoteFile}" $localFile 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green; $copied++ }
    else                      { Write-Host " FAILED" -ForegroundColor Red; $failed++ }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "Sync complete: $copied file(s) updated." -ForegroundColor Green
} else {
    Write-Warning "Sync finished with $failed failure(s). $copied file(s) updated."
    exit 1
}
