# Sync_CSV_toMCP.ps1
# Finds the latest CSV in each structuredData subfolder and SCPs it to the MCP server drop folders.

$RepoRoot   = Split-Path $PSScriptRoot -Parent
$SshKey     = "C:\Users\P3315113\.ssh\vporag_key"
$RemoteHost = "vpomac@192.168.1.29"

$Mappings = @(
    @{ Local = "$RepoRoot\structuredData\JiraCSVexport\DPSTRIAGE"; Remote = "/srv/samba/share/dpstriageCSV/" },
    @{ Local = "$RepoRoot\structuredData\JiraCSVexport\POSTRCA";   Remote = "/srv/samba/share/postrcaCSV/" }
)

foreach ($m in $Mappings) {
    $latest = Get-ChildItem -Path $m.Local -Filter "*.csv" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Warning "No CSV found in $($m.Local) -- skipping."
        continue
    }
    Write-Host "Syncing: $($latest.Name) -> $($m.Remote)"
    scp -i $SshKey $latest.FullName "${RemoteHost}:$($m.Remote)"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK"
    } else {
        Write-Error "  SCP failed for $($latest.Name)"
    }
}
