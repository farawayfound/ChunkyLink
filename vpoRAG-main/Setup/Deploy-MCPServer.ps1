# Setup/Deploy-MCPServer.ps1
# Deploys updated MCP server tool files to 192.168.1.29 and restarts vporag-mcp.
#
# Sudo password is read from Windows Credential Manager (never stored in the repo).
# Store once with:  cmdkey /add:vporag_deploy /user:vpomac /pass:<password>
#
# Usage:
#   powershell -File Setup\Deploy-MCPServer.ps1
#   powershell -File Setup\Deploy-MCPServer.ps1 -Files search_kb,search_jira
#   powershell -File Setup\Deploy-MCPServer.ps1 -Files search_kb -MaxResults 50

param(
    [string[]]$Files      = @("search_kb", "search_jira"),
    [int]     $MaxResults = 0   # 0 = don't update MCP_MAX_RESULTS
)

$SSH_KEY  = "$HOME\.ssh\vporag_key"
$SSH_HOST = "vpomac@192.168.1.29"
$LOCAL    = "mcp_server\tools"
$LOCAL_CONNECTORS = "Searches\Connectors"

# ── Read sudo password from Windows Credential Manager ───────────────────────
# No extra modules needed — pure .NET P/Invoke against advapi32.
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinCred {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct CREDENTIAL {
        public uint Flags; public uint Type; public string TargetName;
        public string Comment;
        public long LastWritten;
        public uint CredentialBlobSize; public IntPtr CredentialBlob;
        public uint Persist; public uint AttributeCount; public IntPtr Attributes;
        public string TargetAlias; public string UserName;
    }
    [DllImport("advapi32", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool CredRead(string target, uint type, uint flags, out IntPtr credential);
    [DllImport("advapi32")] public static extern void CredFree(IntPtr buffer);
    public static string GetPassword(string target) {
        IntPtr ptr;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        var c = Marshal.PtrToStructure<CREDENTIAL>(ptr);
        string pass = "";
        if (c.CredentialBlobSize > 0) {
            byte[] buf = new byte[c.CredentialBlobSize];
            Marshal.Copy(c.CredentialBlob, buf, 0, (int)c.CredentialBlobSize);
            pass = Encoding.Unicode.GetString(buf);
        }
        CredFree(ptr);
        return pass;
    }
}
"@ -ErrorAction SilentlyContinue

# Simpler fallback: read via cmdkey + SecureString prompt if Add-Type fails
function Get-DeployPassword {
    try {
        $pass = [WinCred]::GetPassword("vporag_deploy")
        if ($pass) { return $pass }
    } catch {}
    # Fallback: prompt (only happens if credential not stored)
    $c = Get-Credential -UserName "vpomac" -Message "Enter vpomac sudo password. To avoid this prompt run: cmdkey /add:vporag_deploy /user:vpomac /pass:<password>"
    return $c.GetNetworkCredential().Password
}

$SUDO_PASS = Get-DeployPassword
if (-not $SUDO_PASS) {
    Write-Error "Could not retrieve sudo password. Run: cmdkey /add:vporag_deploy /user:vpomac /pass:<password>"
    exit 1
}

# ── SCP tool files to /tmp ────────────────────────────────────────────────────
$errors  = 0
$targets = @()

foreach ($name in $Files) {
    # jira_query lives in Searches/Connectors, not mcp_server/tools
    $local_path = if ($name -eq "jira_query") { "$LOCAL_CONNECTORS\$name.py" } else { "$LOCAL\$name.py" }
    if (-not (Test-Path $local_path)) {
        Write-Warning "Not found: $local_path - skipping"
        continue
    }
    Write-Host "Uploading $name.py ..."
    scp -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 $local_path "${SSH_HOST}:/tmp/${name}.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "scp failed for $name.py"
        $errors++
        continue
    }
    $targets += $name
}

if ($errors -gt 0) {
    Write-Warning "$errors file(s) failed to upload - aborting"
    exit 1
}

# ── Build vporag-deploy argument list ────────────────────────────────────────
$deployArgs = $targets -join " "
if ($MaxResults -gt 0) { $deployArgs += " config_max_results=$MaxResults" }

if (-not $deployArgs.Trim()) {
    Write-Warning "Nothing to deploy"
    exit 0
}

# ── Run deploy wrapper via passwordless sudo ──────────────────────────────────
$SSH_OPTS = "-n -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2"

# If jira_query is in targets, run the staged patch script first (idempotent)
# patch_deploy_wrapper.sh must already be staged at /tmp/ via:
#   scp Setup\patch_deploy_wrapper.sh vpomac@192.168.1.29:/tmp/
if ($targets -contains "jira_query") {
    Write-Host "Patching vporag-deploy wrapper for jira_query support..."
    $patchCmd = "echo '$SUDO_PASS' | sudo -S bash /tmp/patch_deploy_wrapper.sh"
    Invoke-Expression "ssh $SSH_OPTS $SSH_HOST '$patchCmd'"
}
Write-Host "Running: sudo vporag-deploy $deployArgs"
$cmd = "sudo vporag-deploy $deployArgs"
Invoke-Expression "ssh $SSH_OPTS $SSH_HOST '$cmd'"
if ($LASTEXITCODE -ne 0) {
    # Passwordless sudo not yet set up — fall back to password via -S
    Write-Warning "Passwordless sudo failed, retrying with stored password ..."
    $cmd = "echo '$SUDO_PASS' | sudo -S vporag-deploy $deployArgs"
    Invoke-Expression "ssh $SSH_OPTS $SSH_HOST '$cmd'"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Deploy failed"
        exit 1
    }
}
