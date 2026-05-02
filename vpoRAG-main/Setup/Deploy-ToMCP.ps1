# Deploy-ToMCP.ps1
# Reads Setup/secrets.env and provides helpers for SCP uploads and sudo SSH commands.
# Dot-source to use helpers in other scripts:
#   . "$PSScriptRoot\Deploy-ToMCP.ps1"
#
# Deploy files and restart the MCP service via Deploy-ToMCP.bat, or:
#   powershell -Command "& 'Setup\Deploy-ToMCP.ps1' -Files @('path/a','path/b') -RestartService"

param(
    [string[]]$Files = @(),
    [switch]$RestartService,
    [string]$SecretsFile = "$PSScriptRoot\secrets.env"
)

# -- Load secrets -------------------------------------------------------------

if (-not (Test-Path $SecretsFile)) {
    Write-Error "secrets.env not found at $SecretsFile -- copy Setup\secrets.env.example and fill in values."
    exit 1
}

$secrets = @{}
Get-Content $SecretsFile | Where-Object { $_ -match '^\s*[^#]\S+=\S' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $secrets[$k.Trim()] = $v.Trim()
}

$MCP_HOST      = $secrets["MCP_HOST"]
$MCP_USER      = $secrets["MCP_USER"]
$MCP_SSH_KEY   = $secrets["MCP_SSH_KEY"] -replace '\\', '/'
$MCP_SUDO_PASS = $secrets["MCP_SUDO_PASS"]
$MCP_APP_ROOT  = $secrets["MCP_APP_ROOT"]
$REMOTE        = "${MCP_USER}@${MCP_HOST}"

# -- Helpers ------------------------------------------------------------------

function Invoke-McpScp {
    param([string]$LocalPath)
    $leaf      = Split-Path $LocalPath -Leaf
    $remoteTmp = "/tmp/$leaf"
    $fwdPath   = $LocalPath -replace '\\', '/'
    $key       = $script:MCP_SSH_KEY
    $remote    = $script:REMOTE
    Write-Host "  SCP: $leaf -> $remoteTmp"
    & scp -i $key -o BatchMode=yes -o ConnectTimeout=10 $fwdPath "${remote}:${remoteTmp}"
    if ($LASTEXITCODE -ne 0) { throw "SCP failed for $LocalPath" }
    return $remoteTmp
}

function Invoke-McpSsh {
    param([string]$Command)
    $key       = $script:MCP_SSH_KEY
    $remote    = $script:REMOTE
    $sudoPass  = $script:MCP_SUDO_PASS
    $fullCmd   = "echo $sudoPass | $Command"
    & ssh -i $key -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 $remote $fullCmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $Command" }
}

function Deploy-Files {
    param([string[]]$RelPaths)
    $RepoRoot = Split-Path $PSScriptRoot -Parent
    foreach ($rel in $RelPaths) {
        $local  = Join-Path $RepoRoot ($rel -replace '/', '\')
        $remote = "$script:MCP_APP_ROOT/$($rel -replace '\\', '/')"
        $tmp    = Invoke-McpScp -LocalPath $local
        $chmodCmd = if ($rel -like '*.sh') { " && chmod +x $remote" } else { "" }
        Invoke-McpSsh -Command "sudo -S sh -c 'mv $tmp $remote && chown vporag:vporag $remote$chmodCmd'"
        Write-Host "  Deployed: $rel -> $remote"
    }
}

function Restart-McpService {
    param([string[]]$Services = @('vporag-mcp', 'vporag-dashboard'))
    $key    = $script:MCP_SSH_KEY
    $remote = $script:REMOTE
    # Route through vporag-deploy.sh so the server-side build guard is always enforced.
    # vporag-deploy.sh checks /tmp/vporag_build.pid and skips restart if a build is running.
    Invoke-McpSsh -Command "sudo -S vporag-deploy restart_only"
    Start-Sleep -Seconds 3
    foreach ($svc in $Services) {
        $status = (& ssh -i $key -o BatchMode=yes -o ConnectTimeout=10 $remote "systemctl is-active $svc").Trim()
        Write-Host "  $svc status: $status"
    }
}

# -- Direct invocation --------------------------------------------------------

if ($Files.Count -gt 0 -or $RestartService) {
    if ($Files.Count -gt 0) {
        Write-Host "Deploying $($Files.Count) file(s) to MCP server..."
        Deploy-Files -RelPaths $Files
    }
    Restart-McpService
    Write-Host "Done."
}
