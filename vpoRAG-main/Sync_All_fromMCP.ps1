# Sync_All_fromMCP.ps1
# Syncs both the JSON knowledge base and the local Jira SQLite DB from the MCP server.
# Output: reports which (if any) were updated, or confirms everything is already current.

$root = $PSScriptRoot

# ── JSON index sync ───────────────────────────────────────────────────────────
Write-Host "=== JSON Index ===" -ForegroundColor Cyan
$jsonOut = & powershell -NonInteractive -File "$root\Setup\Sync-JSONIndex.ps1" 2>&1
$jsonExit = $LASTEXITCODE
$jsonOut | ForEach-Object { Write-Host "  $_" }

$jsonUpdated = $jsonExit -eq 0 -and ($jsonOut -match "Sync complete")
$jsonCurrent = $jsonExit -eq 0 -and ($jsonOut -match "up to date")
$jsonError   = $jsonExit -ne 0

# ── Jira SQLite sync ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Jira SQLite DB ===" -ForegroundColor Cyan
$dbOut = & python "$root\Setup\sync_local_db.py" 2>&1
$dbExit = $LASTEXITCODE
$dbOut | ForEach-Object { Write-Host "  $_" }

$dbUpdated = $dbExit -eq 2
$dbCurrent = $dbExit -eq 0
$dbError   = $dbExit -eq 1

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Result ===" -ForegroundColor Cyan

if ($jsonError -or $dbError) {
    if ($jsonError) { Write-Warning "JSON index sync failed (exit $jsonExit)." }
    if ($dbError)   { Write-Warning "Jira DB sync failed (exit $dbExit)." }
    exit 1
}

$updated = @()
if ($jsonUpdated) { $updated += "JSON index" }
if ($dbUpdated)   { $updated += "Jira SQLite DB" }

if ($updated.Count -gt 0) {
    Write-Host "Updated: $($updated -join ', ')" -ForegroundColor Green
} else {
    Write-Host "Latest versions already locally present." -ForegroundColor Green
}
