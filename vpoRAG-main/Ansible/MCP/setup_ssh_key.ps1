# setup_ssh_key.ps1
# Run this ONCE from a PowerShell terminal before executing the Ansible playbook.
# Fixes the two SSH hiccups from the chat session:
#   1. %USERPROFILE% does not expand in PowerShell — use $env:USERPROFILE explicitly
#   2. SSH password prompt hangs non-interactive tools — key auth eliminates it

param(
    [string]$ServerUser = "vpomac",
    [string]$ServerHost = "192.168.1.29",
    [string]$KeyPath    = "$env:USERPROFILE\.ssh\vporag_key"
)

$KeyDir = Split-Path $KeyPath

if (-not (Test-Path $KeyDir)) {
    New-Item -ItemType Directory -Path $KeyDir | Out-Null
}

if (-not (Test-Path $KeyPath)) {
    Write-Host "Generating ed25519 key pair at $KeyPath ..."
    ssh-keygen -t ed25519 -f $KeyPath -N '""'
} else {
    Write-Host "Key already exists at $KeyPath — skipping generation."
}

$PubKey = Get-Content "$KeyPath.pub"
Write-Host "Copying public key to ${ServerUser}@${ServerHost} ..."
Write-Host "(You will be prompted for the SSH password once — this is the last time.)"

$RemoteCmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$PubKey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
ssh -o StrictHostKeyChecking=no "${ServerUser}@${ServerHost}" $RemoteCmd

Write-Host ""
Write-Host "Done. Verify with:"
Write-Host "  ssh -i $KeyPath ${ServerUser}@${ServerHost} 'echo key-auth-ok'"
