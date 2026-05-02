# -*- coding: utf-8 -*-
# Run-OnMcp.ps1
# Runs a command on the MCP server and returns stdout reliably.
#
# The PowerShell & operator swallows SSH stdout when used with complex pipelines.
# This helper works around it by redirecting remote output to a temp file,
# then SCP-ing the file back and printing it locally.
#
# Usage (dot-source not required — invoke directly):
#   powershell -ExecutionPolicy Bypass -Command "& 'Setup\Run-OnMcp.ps1' -Command 'ls /srv/vpo_rag'"
#
# Or dot-source for use in other scripts:
#   . "Setup\Run-OnMcp.ps1"
#   Invoke-OnMcp "mysql -u jira_user -p... jira_db -e 'SELECT ...'"
#
# For Python scripts, use Invoke-PythonOnMcp which injects MYSQL_PASS automatically.

param([string]$Command = "")

# ── Load secrets ──────────────────────────────────────────────────────────────
$SecretsFile = "$PSScriptRoot\secrets.env"
if (-not (Test-Path $SecretsFile)) {
    Write-Error "secrets.env not found at $SecretsFile"
    exit 1
}
$script:secrets = @{}
Get-Content $SecretsFile | Where-Object { $_ -match '^\s*[^#]\S+=\S' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $script:secrets[$k.Trim()] = $v.Trim()
}
$script:KEY        = $script:secrets['MCP_SSH_KEY'].Replace('\', '/')
$script:REMOTE     = $script:secrets['MCP_USER'] + '@' + $script:secrets['MCP_HOST']
$script:SUDO_PASS  = $script:secrets['MCP_SUDO_PASS']
$script:MYSQL_PASS = $script:secrets['MYSQL_PASS']
$script:APP_ROOT   = $script:secrets['MCP_APP_ROOT']

# ── Core helper: run remote command, capture stdout via temp file ─────────────
function Invoke-OnMcp {
    param([string]$RemoteCmd, [switch]$UseSudo)

    $tmpOut  = "/tmp/mcp_out_$([System.IO.Path]::GetRandomFileName().Replace('.',''))"
    $tmpLocal = [System.IO.Path]::GetTempFileName()

    try {
        if ($UseSudo) {
            $fullCmd = "echo '$($script:SUDO_PASS)' | sudo -S sh -c '$RemoteCmd' > $tmpOut 2>&1"
        } else {
            $fullCmd = "$RemoteCmd > $tmpOut 2>&1"
        }

        # Run the command (stdout goes to remote temp file)
        & ssh -i $script:KEY -o BatchMode=yes -o ConnectTimeout=15 `
              -o ServerAliveInterval=5 -o ServerAliveCountMax=2 `
              $script:REMOTE $fullCmd | Out-Null

        # SCP the output file back
        & scp -i $script:KEY -o BatchMode=yes -o ConnectTimeout=10 `
              "${script:REMOTE}:${tmpOut}" $tmpLocal | Out-Null

        $output = Get-Content $tmpLocal -Raw -ErrorAction SilentlyContinue
        return $output
    } finally {
        Remove-Item $tmpLocal -ErrorAction SilentlyContinue
        # Clean up remote temp file
        & ssh -i $script:KEY -o BatchMode=yes -o ConnectTimeout=5 `
              $script:REMOTE "rm -f $tmpOut" | Out-Null
    }
}

# ── Python helper: runs a .py file on the server via the vporag venv ──────────
# Injects MYSQL_PASS automatically. Pass a local .py path; it gets SCP'd first.
function Invoke-PythonOnMcp {
    param([string]$LocalScript, [string]$Args = "")

    $leaf   = Split-Path $LocalScript -Leaf
    $remote = "/tmp/$leaf"

    # SCP the script
    & scp -i $script:KEY -o BatchMode=yes -o ConnectTimeout=10 `
          ($LocalScript -replace '\\', '/') "${script:REMOTE}:${remote}" | Out-Null

    $cmd = "MYSQL_PASS='$($script:MYSQL_PASS)' $($script:APP_ROOT)/venv/bin/python $remote $Args"
    return Invoke-OnMcp -RemoteCmd $cmd
}

# ── MySQL helper: run a SQL statement directly ────────────────────────────────
function Invoke-MySqlOnMcp {
    param([string]$Sql, [string]$Database = "jira_db")
    $mysqlUser = $script:secrets['MYSQL_USER']
    $mysqlPass = $script:secrets['MYSQL_PASS']
    $cmd = "mysql -u $mysqlUser -p'$mysqlPass' $Database -e `"$Sql`""
    return Invoke-OnMcp -RemoteCmd $cmd
}

# ── Direct invocation ─────────────────────────────────────────────────────────
if ($Command) {
    $result = Invoke-OnMcp -RemoteCmd $Command
    Write-Output $result
}
