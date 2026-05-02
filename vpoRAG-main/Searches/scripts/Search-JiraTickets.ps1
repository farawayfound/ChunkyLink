param(
    [Parameter(Mandatory=$true)]
    [string[]]$Terms,
    [string[]]$DiscoveredTerms = @(),
    [ValidateSet("top","count","oldest","custom")]
    [string]$Mode = "top",
    [int]$Limit = 0,
    [int]$Since = 0,
    [ValidateSet("both","dpstriage","postrca")]
    [string]$TicketType = "both",
    [string[]]$Status = @(),
    [string]$Client = "",
    [string]$Question = "",   # Natural-language question — auto-sets Mode/Limit/Since/Status
    [string]$Sql = ""          # Raw SQL override (SELECT only) passed to jira_query.py
)

# ── NL → query intent parser ─────────────────────────────────────────────────
function Parse-Question {
    param([string]$q)
    $r = @{}
    if (-not $q) { return $r }

    # Ticket type
    if ($q -match '\b(dpstriage|postrca|post.?rca)\b') {
        $r['ticket_type'] = if ($Matches[1] -match 'postrca|post.?rca') { 'postrca' } else { 'dpstriage' }
    }

    # Since extraction
    if     ($q -match '(?:last|past) (\d+) years?')  { $r['since'] = [int]$Matches[1] * 12 }
    elseif ($q -match '(?:last|past) (\d+) months?') { $r['since'] = [int]$Matches[1] }
    elseif ($q -match '(?:last|past) (\d+) weeks?')  { $r['since'] = [math]::Max(1, [math]::Round([int]$Matches[1] / 4)) }
    elseif ($q -match '\bthis year\b')               { $r['since'] = 12 }
    elseif ($q -match '\bthis (week|month)\b')       { $r['since'] = 1 }

    # Top-N
    if ($q -match '\btop (\d+)\b') { $r['limit'] = [int]$Matches[1] }

    # Mode (first match wins)
    $mode = $null
    if     ($q -match '\bhow many\b|\btotal (number|count|tickets?)\b|\bcount\b|\bhow often\b|\bfrequency\b|\bnumber of (tickets?|issues?|cases?)\b') { $mode = 'count' }
    elseif ($q -match '\btrend\b|\bspike\b|\bincreasing\b|\bover (the )?(last|past) \d+ (month|week|day)')                                          { $mode = 'count'; if (-not $r['since']) { $r['since'] = 6 } }
    elseif ($q -match '\boldest\b|\bfirst (reported|seen|ticket|case)\b|\bwhen (did|was) .{0,30}(first|start)|\boriginated\b|\bgoing back\b')        { $mode = 'oldest' }
    elseif ($q -match '\ball (tickets?|issues?|cases?)\b|\bevery (ticket|issue|case)\b|\bfull list\b|\blist (all|every)\b')                          { $mode = 'custom'; if (-not $r['limit']) { $r['limit'] = 200 } }
    elseif ($q -match '\bmost common\b|\bmost frequent\b|\bbreakdown\b|\bby (root cause|category|team|client|status)\b|\bgroup(ed)? by\b|\bdistribution\b') { $mode = 'custom'; if (-not $r['limit']) { $r['limit'] = 100 } }
    if ($mode) { $r['mode'] = $mode }

    # Status hints
    # "active"/"in progress" → active preset (4 specific in-flight statuses)
    # "open" intentionally NOT mapped — means "not closed", which is the default behaviour
    if     ($q -match '\bactive\b|\bin progress\b') { $r['status'] = @('active') }
    elseif ($q -match '\bclosed\b|\bresolved\b|\bfixed\b')   { $r['status'] = @('resolved') }

    return $r
}

# Apply NL question overrides before any other processing
if ($Question) {
    $nlParsed = Parse-Question $Question
    if ($nlParsed['mode'])        { $Mode       = $nlParsed['mode'] }
    if ($nlParsed['limit'])       { $Limit      = $nlParsed['limit'] }
    if ($nlParsed['since'])       { $Since      = $nlParsed['since'] }
    if ($nlParsed['status'])      { $Status     = $nlParsed['status'] }
    if ($nlParsed['ticket_type']) { $TicketType = $nlParsed['ticket_type'] }
    Write-Host "[NL] Parsed question: mode=$Mode limit=$Limit since=$Since status=$($Status -join ',') type=$TicketType" -ForegroundColor Magenta
}

function Get-Synonyms {
    param([string]$term)
    $synonymMap = @{
        'error'     = @('error','fail','issue','problem','broken')
        'fail'      = @('error','fail','issue','problem','broken')
        'issue'     = @('error','fail','issue','problem','broken')
        'problem'   = @('error','fail','issue','problem','broken')
        'broken'    = @('error','fail','issue','problem','broken')
        'freeze'    = @('freeze','hang','stuck','unresponsive','lock')
        'hang'      = @('freeze','hang','stuck','unresponsive','lock')
        'stuck'     = @('freeze','hang','stuck','unresponsive','lock')
        'restart'   = @('restart','reboot','bounce','cycle')
        'reboot'    = @('restart','reboot','bounce','cycle')
        'playback'  = @('playback','play','watch','view','stream')
        'play'      = @('playback','play','watch','view','stream')
        'recording' = @('recording','record','dvr','schedule')
        'record'    = @('recording','record','dvr','schedule')
        'fix'       = @('fix','resolve','repair','correct','mitigate')
        'resolve'   = @('fix','resolve','repair','correct','mitigate')
    }
    $lower = $term.ToLower()
    if ($synonymMap.ContainsKey($lower)) { return $synonymMap[$lower] }
    return @($term)
}

$pyScript     = Join-Path $PSScriptRoot "..\Connectors\jira_query.py"
if (-not (Test-Path $pyScript)) { $pyScript = Join-Path (Split-Path $MyInvocation.MyCommand.Path) "..\Connectors\jira_query.py" }
$configScript = Join-Path $PSScriptRoot "..\config.ps1"
$syncScript   = Join-Path $PSScriptRoot "..\..\Setup\sync_local_db.py"
$localDb      = Join-Path $PSScriptRoot "..\jira_local.db"

$expandedTerms = ($Terms | ForEach-Object { Get-Synonyms $_ } | Select-Object -Unique) | Select-Object -First 5

#  Config defaults (overridden by config.ps1 below)
$primarySource    = "csv"
$searchAllSources = $false
$dpsCsvDir = Join-Path $PSScriptRoot "..\..\structuredData\JiraCSVexport\DPSTRIAGE"
$rcaCsvDir = Join-Path $PSScriptRoot "..\..\structuredData\JiraCSVexport\POSTRCA"

if (Test-Path $configScript) {
    . $configScript
    if ($SEARCH_MODE -eq "MCP") {
        Write-Host "[config] SEARCH_MODE=MCP - use MCP tools instead of this script." -ForegroundColor Yellow
        Write-Host "         Set SEARCH_MODE=Local in Searches/config.ps1 to use local PowerShell search." -ForegroundColor Yellow
        # Continue anyway as a fallback
    }
    if ($JIRA_PRIMARY_SOURCE)                  { $primarySource    = $JIRA_PRIMARY_SOURCE.ToLower() }
    if ($JIRA_SEARCH_ALL_SOURCES -ne $null)    { $searchAllSources = $JIRA_SEARCH_ALL_SOURCES }
    if ($JIRA_DPS_CSV_DIR)                     { $dpsCsvDir        = $JIRA_DPS_CSV_DIR }
    if ($JIRA_RCA_CSV_DIR)                     { $rcaCsvDir        = $JIRA_RCA_CSV_DIR }
    if ($JIRA_LOCAL_DB)                        { $localDb          = $JIRA_LOCAL_DB }
}

Write-Host "`n=== JIRA TICKET SEARCH ($($Mode.ToUpper())) ===" -ForegroundColor Cyan
Write-Host "Terms (expanded): $($expandedTerms -join ', ')" -ForegroundColor Yellow
if ($DiscoveredTerms.Count -gt 0) { Write-Host "Discovered terms: $($DiscoveredTerms -join ', ')" -ForegroundColor Magenta }
if ($Mode -ne "top") { Write-Host "Mode: $Mode | Limit: $(if($Limit -gt 0){$Limit}else{'default'}) | Since: $(if($Since -gt 0){$Since.ToString()+' months'}else{'all time'}) | Type: $TicketType" -ForegroundColor Yellow }

$statusPresets = @{
    'active'   = @('Triage In Progress','Pending Mitigation','More Info Needed','Blocked')
    'resolved' = @('Closed','Pending Verification','Routed to POST-RCA')
}
if ($Status.Count -eq 1 -and $statusPresets.ContainsKey($Status[0].ToLower())) {
    $Status = $statusPresets[$Status[0].ToLower()]
}

$pyArgs = @($expandedTerms) + @("--mode", $Mode) + @("--ticket-type", $TicketType)
if ($DiscoveredTerms.Count -gt 0) { $pyArgs += @("--discovered") + ($DiscoveredTerms | Select-Object -First 5) }
if ($Limit -gt 0)        { $pyArgs += @("--limit", $Limit) }
if ($Since -gt 0)        { $pyArgs += @("--since", $Since) }
if ($Status.Count -gt 0) { $pyArgs += @("--status") + $Status }
if ($Client -ne "")      { $pyArgs += @("--client", $Client) }
if ($Sql -ne "")         { $pyArgs += @("--sql", $Sql) }

#  MERGE HELPER 
function Merge-JiraResults {
    param($a, $b)
    if (-not $a) { return $b }
    if (-not $b) { return $a }
    $dpMerged = (@($a.dpstriage) + @($b.dpstriage)) | Where-Object { $_.Key } | Group-Object Key | ForEach-Object { $_.Group[0] }
    $rcMerged = (@($a.postrca)   + @($b.postrca))   | Where-Object { $_.Key } | Group-Object Key | ForEach-Object { $_.Group[0] }
    return [PSCustomObject]@{
        dpstriage = $dpMerged
        postrca   = $rcMerged
        mode      = $a.mode
        terms     = $a.terms
        source    = 'merged'
    }
}

#  CSV HELPERS 
$dps_SearchFields = @('Summary','Description','Custom field (Root Cause)',
                      'Custom field (Resolution / Mitigation Solution)',
                      'Custom field (Resolution Category)',
                      'Custom field (Vertical)','Custom field (Responsible Team)',
                      'Custom field (Last Comment)')
$rca_SearchFields = @('Summary','Custom field (Root cause (text))',
                      'Custom field (Resolution / Mitigation Solution)',
                      'Custom field (Vertical)','Custom field (Responsible Team)',
                      'Custom field (Client)')

function Csv-MatchRow($row, $terms, $fields) {
    foreach ($t in $terms) {
        $p = [regex]::Escape($t)
        foreach ($f in $fields) { if ($row.$f -match $p) { return $true } }
    }
    return $false
}

function Csv-ScoreRow($row, $terms, $fields) {
    $s = 0
    foreach ($t in $terms) {
        $p = [regex]::Escape($t)
        if ($row.'Summary' -match $p) { $s += 3 }
        foreach ($f in $fields | Where-Object { $_ -ne 'Summary' }) {
            if ($row.$f -match $p) { $s += 1 }
        }
    }
    # Subtle recency bonus — light tiebreaker, does not override term relevance
    try {
        $ageDays = ([datetime]::Now - [datetime]::Parse($row.'Created')).Days
        if     ($ageDays -le 30)  { $s += 3 }
        elseif ($ageDays -le 90)  { $s += 2 }
        elseif ($ageDays -le 180) { $s += 1 }
    } catch {}
    return $s
}

function Get-LatestCsv($dir) {
    Get-ChildItem $dir -Filter "*.csv" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Csv-ApplySinceFilter($rows, $since) {
    if ($since -le 0) { return $rows }
    $cutoff = (Get-Date).AddMonths(-$since)
    return $rows | Where-Object { try { [datetime]::Parse($_.'Created') -ge $cutoff } catch { $true } }
}

function Csv-ApplyStatusFilter($rows, $status, $excludeStatuses, $applyDefaults) {
    if ($status.Count -gt 0)                              { return $rows | Where-Object { $status -contains $_.Status } }
    elseif ($applyDefaults -and $excludeStatuses.Count -gt 0) { return $rows | Where-Object { $excludeStatuses -notcontains $_.Status } }
    return $rows
}

function Csv-SelectTop($matched, $top, $terms, $fields, $extraFields) {
    $matched | ForEach-Object {
        $obj = [ordered]@{ Key=$_.'Issue key'; Summary=$_.Summary; Status=$_.Status
                           Created=$_.Created; Updated=$_.Updated; RelevanceScore=(Csv-ScoreRow $_ $terms $fields) }
        foreach ($ef in $extraFields.GetEnumerator()) { $obj[$ef.Key] = $_.$($ef.Value) }
        [PSCustomObject]$obj
    } | Sort-Object RelevanceScore -Descending | Select-Object -First $top
}

function Search-JiraCSV {
    param([string[]]$Terms, [string]$TicketType="both", [string[]]$Status=@(),
          [string]$Client="", [string]$Mode="top", [int]$Limit=0, [int]$Since=0)

    $applyDefaults = ($Mode -in @('top','custom')) -and ($Status.Count -eq 0)
    $dpsExclude = @('Cancelled','Backlog')
    $rcaInclude = @('Open','In Progress','Closed','Approved','Blocked','Submitted',
                    'Pending Release','Template','Ready For Work','Pending Fix',
                    'Deployment Complete','Deployment In Progress','Deployment Pending')
    $topDps = if ($Limit -gt 0) { $Limit } else { 15 }
    $topRca = if ($Limit -gt 0) { $Limit } else { 5 }
    $dpFinal=@(); $rcFinal=@()

    if ($TicketType -in @('both','dpstriage')) {
        $f = Get-LatestCsv $dpsCsvDir
        if (-not $f) { Write-Host "  [CSV] No DPSTRIAGE CSV in $dpsCsvDir" -ForegroundColor Red }
        else {
            Write-Host "  [CSV] DPSTRIAGE: $($f.Name)" -ForegroundColor Yellow
            $rows = Import-Csv $f.FullName | Where-Object { $_.'Issue key' }
            $rows = Csv-ApplySinceFilter $rows $Since
            if ($Status.Count -gt 0) { $rows = Csv-ApplyStatusFilter $rows $Status @() $false }
            elseif ($applyDefaults)  { $rows = Csv-ApplyStatusFilter $rows @() $dpsExclude $true }
            if ($Client) { $rows = $rows | Where-Object { $_.'Custom field (Vertical)' -match [regex]::Escape($Client) -or $_.'Custom field (Responsible Team)' -match [regex]::Escape($Client) } }
            $matched = $rows | Where-Object { Csv-MatchRow $_ $Terms $dps_SearchFields }
            if ($Mode -eq 'count')  { $dpCount  = ($matched | Measure-Object).Count }
            elseif ($Mode -eq 'oldest') { $dpOldest = $matched | Sort-Object { try{[datetime]::Parse($_.'Created')}catch{[datetime]::MaxValue} } | Select-Object -First 1 }
            else { if ($matched) { $dpFinal = @(Csv-SelectTop ($matched | Where-Object { $_.'Issue key' }) $topDps $Terms $dps_SearchFields ([ordered]@{ RootCause='Custom field (Root Cause)'; Resolution='Custom field (Resolution / Mitigation Solution)'; ResolutionCategory='Custom field (Resolution Category)'; Vertical='Custom field (Vertical)'; LastComment='Custom field (Last Comment)' })) } }
        }
    }

    if ($TicketType -in @('both','postrca')) {
        $f = Get-LatestCsv $rcaCsvDir
        if (-not $f) { Write-Host "  [CSV] No POSTRCA CSV in $rcaCsvDir" -ForegroundColor Red }
        else {
            Write-Host "  [CSV] POSTRCA:   $($f.Name)" -ForegroundColor Yellow
            $rows = Import-Csv $f.FullName -Encoding UTF8 | Where-Object { $_.'Issue key' }
            $rows = Csv-ApplySinceFilter $rows $Since
            if ($Status.Count -gt 0) { $rows = Csv-ApplyStatusFilter $rows $Status @() $false }
            elseif ($applyDefaults)  { $rows = $rows | Where-Object { $rcaInclude -contains $_.Status } }
            if ($Client) { $rows = $rows | Where-Object { $_.'Custom field (Client)' -match [regex]::Escape($Client) -or $_.'Custom field (Vertical)' -match [regex]::Escape($Client) } }
            $matched = $rows | Where-Object { Csv-MatchRow $_ $Terms $rca_SearchFields }
            if ($Mode -eq 'count')  { $rcCount  = ($matched | Measure-Object).Count }
            elseif ($Mode -eq 'oldest') { $rcOldest = $matched | Sort-Object { try{[datetime]::Parse($_.'Created')}catch{[datetime]::MaxValue} } | Select-Object -First 1 }
            else { if ($matched) { $rcFinal = @(Csv-SelectTop ($matched | Where-Object { $_.'Issue key' }) $topRca $Terms $rca_SearchFields ([ordered]@{ RootCause='Custom field (Root cause (text))'; Resolution='Custom field (Resolution / Mitigation Solution)'; Client='Custom field (Client)'; Vertical='Custom field (Vertical)'; Priority='Priority' })) } }
        }
    }

    if ($Mode -eq 'count')  { return [PSCustomObject]@{ dpstriage_count=if($dpCount){$dpCount}else{0}; postrca_count=if($rcCount){$rcCount}else{0}; mode='count'; terms=$Terms } }
    if ($Mode -eq 'oldest') { return [PSCustomObject]@{
        dpstriage_oldest=if($dpOldest){[PSCustomObject]@{Key=$dpOldest.'Issue key';Summary=$dpOldest.Summary;Status=$dpOldest.Status;Created=$dpOldest.Created}}else{$null}
        postrca_oldest=if($rcOldest){[PSCustomObject]@{Key=$rcOldest.'Issue key';Summary=$rcOldest.Summary;Status=$rcOldest.Status;Created=$rcOldest.Created}}else{$null}
        mode='oldest'; terms=$Terms } }
    return [PSCustomObject]@{ dpstriage=$dpFinal; postrca=$rcFinal; mode=$Mode; terms=$Terms; source='csv' }
}

# -- LOCAL SQLITE SEARCH -----------------------------------------------------
function Search-LocalSQLite {
    param([string[]]$Terms, [string]$TicketType="both", [string[]]$Status=@(),
          [string]$Client="", [string]$Mode="top", [int]$Limit=0, [int]$Since=0)

    $dbPath   = if ($localDb) { $localDb } else { Join-Path $PSScriptRoot "..\..\structuredData\database\jira_local.db" }
    $pySearch = Join-Path $PSScriptRoot "query_local_db.py"

    if (-not (Test-Path $dbPath)) {
        Write-Host "  [LocalDB] Not found: $dbPath -- run: python Searches/sync_local_db.py" -ForegroundColor Red
        return $null
    }
    if (-not (Test-Path $pySearch)) {
        Write-Host "  [LocalDB] query_local_db.py not found" -ForegroundColor Red
        return $null
    }

    Write-Host "  [LocalDB] $dbPath" -ForegroundColor Yellow
    $dbArgs = @($Terms) + @("--mode", $Mode, "--ticket-type", $TicketType, "--db", $dbPath)
    if ($Limit -gt 0)        { $dbArgs += @("--limit", $Limit) }
    if ($Since -gt 0)        { $dbArgs += @("--since", $Since) }
    if ($Status.Count -gt 0) { $dbArgs += @("--status") + $Status }
    if ($Client -ne "")      { $dbArgs += @("--client", $Client) }

    $raw = python $pySearch $dbArgs 2>&1 | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [LocalDB] Query failed (exit $LASTEXITCODE)" -ForegroundColor Red
        return $null
    }
    return $raw | ConvertFrom-Json
}

#  REMOTE SSMS SEARCH 
function Search-RemoteSSMS {
    $raw = python $pyScript $pyArgs 2>&1 | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }
    if ($LASTEXITCODE -ne 0) { return $null }
    return $raw | ConvertFrom-Json
}

#  SOURCE DISPATCH 
$csvMode  = $Mode
$csvSince = if ($Mode -eq 'top' -and $Since -eq 0) { 6 } else { $Since }

$parsed = $null

switch ($primarySource) {
    "sqlite" {
        Write-Host "  Source: LocalDB/SQLite (primary)" -ForegroundColor Cyan
        $parsed = Search-LocalSQLite -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                     -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
        if (-not $parsed) {
            Write-Host "  LocalDB unavailable - falling back to CSV" -ForegroundColor Yellow
            $parsed = Search-JiraCSV -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                     -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
        }
    }
    "csv" {
        Write-Host "  Source: CSV (primary)" -ForegroundColor Cyan
        $parsed = Search-JiraCSV -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                 -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
    }
    default {
        Write-Host "  Source: SSMS/SQL (primary)" -ForegroundColor Cyan
        $parsed = Search-RemoteSSMS
        if (-not $parsed) {
            Write-Host "  SSMS unavailable  falling back to CSV" -ForegroundColor Yellow
            $parsed = Search-JiraCSV -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                     -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
        }
    }
}

if (-not $parsed) { return }

#  SEARCH ALL SOURCES AND MERGE 
if ($searchAllSources) {
    if ($primarySource -ne "csv") {
        Write-Host "  [AllSources] Also querying CSV..." -ForegroundColor Cyan
        $csvResult = Search-JiraCSV -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                    -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
        if ($csvResult) { $parsed = Merge-JiraResults $parsed $csvResult }
    }
    if ($primarySource -ne "sqlite") {
        Write-Host "  [AllSources] Also querying LocalDB..." -ForegroundColor Cyan
        $dbResult = Search-LocalSQLite -Terms $expandedTerms -TicketType $TicketType -Status $Status `
                                       -Client $Client -Mode $csvMode -Limit $Limit -Since $csvSince
        if ($dbResult) { $parsed = Merge-JiraResults $parsed $dbResult }
    }
    if ($primarySource -ne "sql") {
        Write-Host "  [AllSources] Also querying SSMS..." -ForegroundColor Cyan
        $ssmsResult = Search-RemoteSSMS
        if ($ssmsResult) { $parsed = Merge-JiraResults $parsed $ssmsResult }
    }
}

#  OUTPUT 
switch ($Mode) {
    "count" {
        if ($null -ne $parsed.dpstriage_count) { Write-Host "DPSTRIAGE count: $($parsed.dpstriage_count)" -ForegroundColor Green }
        if ($null -ne $parsed.postrca_count)   { Write-Host "POSTRCA count:   $($parsed.postrca_count)"   -ForegroundColor Green }
    }
    "oldest" {
        if ($parsed.dpstriage_oldest) { Write-Host "Oldest DPSTRIAGE: $($parsed.dpstriage_oldest.Key) ($($parsed.dpstriage_oldest.Created))" -ForegroundColor Green }
        if ($parsed.postrca_oldest)   { Write-Host "Oldest POSTRCA:   $($parsed.postrca_oldest.Key) ($($parsed.postrca_oldest.Created))"     -ForegroundColor Green }
    }
    default {
        Write-Host "DPSTRIAGE: $($parsed.dpstriage.Count) | POSTRCA: $($parsed.postrca.Count) | Total: $($parsed.dpstriage.Count + $parsed.postrca.Count)" -ForegroundColor Green
    }
}

$parsed | ConvertTo-Json -Depth 5
