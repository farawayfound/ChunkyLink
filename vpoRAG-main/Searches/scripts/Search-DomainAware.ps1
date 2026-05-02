param(
    [Parameter(Mandatory=$true)]
    [string[]]$Terms,
    [string]$Query = "",
    [string[]]$Domains = @(),
    [string]$Level = "",
    [int]$MaxResults = 0
)

$EXPANSION_LEVELS = @{
    "Quick"      = @{ Phase1=12;  Phase3=5;   Phase6=3;   Total=20  }
    "Standard"   = @{ Phase1=45; Phase3=55; Phase35=15; Phase4=25; Phase5=20; Phase6=40; Total=185 }
    "Deep"       = @{ Phase1=90; Phase3=110; Phase35=30; Phase4=50; Phase5=40; Phase6=80; Phase7=20; Phase8=70; Total=460 }
    "Exhaustive" = @{ Phase1=180; Phase3=220; Phase35=60; Phase4=100; Phase5=80; Phase6=160; Phase7=40; Phase8=140; Total=920 }
}

# NLP noise tags excluded from Phase 2 discovery and Phase 4 scoring.
$TAG_STOPLIST = @(
    "vpo","post","address","report","communications","client",
    "lob","functiona","functiona-client","clos","issue","spectrum",
    "action-provide","action-select","action-enter","action-configure",
    "action-check","action-verify","action-review","action-update",
    "select","select-research","your","home","experience","usage",
    "task","escalations-usage-task","role","mso","pid"
)

# Regex to detect actual query syntax (SPL / DQL / Kibana) in a chunk.
# Requires trailing space on pipe commands and \w after index= to avoid
# matching markdown table pipes (| Status |) or bare index= in prose.
$QUERY_SYNTAX_RE = [regex]"index=\w|sourcetype=\w|[|] stats |[|] eval |[|] rex |[|] dedup |[|] timechart |[|] transaction |[|] spath |\b\w+[.]\w+\s*:[^/]|OV-TUNE-FAIL|ov-tune-fail"

function Get-DomainFromQuery {
    param([string]$userQuery)
    $q = $userQuery.ToLower()
    $d = @("troubleshooting","queries","sop")
    if ($q -match '\b(documentation|manual|guide|feature|specification|what is)\b') { $d += "manual" }
    if ($q -match '\b(contact|team|escalate|who|phone|email|org|department)\b') { $d += "reference" }
    if ($q -match '\b(what does|mean|definition|acronym|stands for)\b') { $d += "glossary" }
    return $d | Select-Object -Unique
}

# Apply config defaults when caller didn't override
$configScript = Join-Path $PSScriptRoot "..\config.ps1"
if (Test-Path $configScript) { . $configScript }

# Guard: if SEARCH_MODE is MCP, this script should not be called directly
if ($SEARCH_MODE -eq "MCP") {
    Write-Host "[config] SEARCH_MODE=MCP - use MCP tools instead of this script." -ForegroundColor Yellow
    Write-Host "         Set SEARCH_MODE=Local in Searches/config.ps1 to use local PowerShell search." -ForegroundColor Yellow
    # Continue anyway as a fallback
}

if (-not $Level -and $JSON_SEARCH_LEVEL) { $Level = $JSON_SEARCH_LEVEL }
elseif (-not $Level) { $Level = "Standard" }
if ($MaxResults -eq 0 -and $JSON_MAX_RESULTS)       { $MaxResults = $JSON_MAX_RESULTS }

$limits = $EXPANSION_LEVELS[$Level]
if ($MaxResults -eq 0) { $MaxResults = $limits.Total }
$outDir      = if ($JSON_KB_DIR) { $JSON_KB_DIR } else { Join-Path $PSScriptRoot "..\..\JSON" }
$quickSearch = ($Level -eq "Quick")
$deepSearch  = ($Level -eq "Deep" -or $Level -eq "Exhaustive")
$totalPhases = if ($deepSearch) { 8 } elseif ($quickSearch) { 4 } else { 6 }

if ($Domains.Count -eq 0 -and $Query) {
    $Domains = Get-DomainFromQuery -userQuery $Query
    Write-Host "Auto-detected domains: $($Domains -join ', ')" -ForegroundColor Magenta
}

$searchFiles = @()
foreach ($domain in $Domains) {
    $f = "$outDir\detail\chunks.$domain.jsonl"
    if (Test-Path $f) { $searchFiles += $f }
}
if ($searchFiles.Count -eq 0) {
    $searchFiles = @("$outDir\detail\chunks.jsonl")
    Write-Host "Using unified chunks.jsonl (fallback)" -ForegroundColor Yellow
}

Write-Host "`n=== DOMAIN-AWARE SEARCH: $totalPhases PHASES ($Level) ===" -ForegroundColor Cyan
Write-Host "Domains: $($Domains -join ', ')" -ForegroundColor Yellow
Write-Host "Terms: $($Terms -join ', ')" -ForegroundColor Yellow

# Load domain files once
$domainChunks = @{}
foreach ($f in $searchFiles) {
    $domainChunks[$f] = Get-Content $f | ConvertFrom-Json
}

# Pre-load ALL category files once for cross-domain phases (3, 6, 8).
# Avoids repeated disk reads inside phase loops.
$allCategoryFiles = Get-ChildItem "$outDir\detail\chunks.*.jsonl" | Where-Object { $_.Name -ne "chunks.jsonl" }
$allChunksFlat = @()
foreach ($af in $allCategoryFiles) {
    $allChunksFlat += Get-Content $af.FullName | ConvertFrom-Json
}
$allChunksById = @{}
foreach ($c in $allChunksFlat) { $allChunksById[$c.id] = $c }

# PHASE 1: Initial domain search
Write-Host "`n[1/$totalPhases] Initial domain search..." -ForegroundColor Cyan
$phase1 = @()
foreach ($f in $searchFiles) {
    foreach ($chunk in $domainChunks[$f]) {
        $combined = "$($chunk.text) $($chunk.search_text -join ' ')".ToLower()
        $hits = ($Terms | Where-Object { $combined -like "*$($_.ToLower())*" }).Count
        if ($hits -ge 2) { $phase1 += $chunk }
    }
}
Write-Host "  Found: $($phase1.Count)" -ForegroundColor Green

if ($phase1.Count -eq 0) {
    Write-Host "  Phase1 fallback: retrying with min_hits=1..." -ForegroundColor Yellow
    foreach ($f in $searchFiles) {
        foreach ($chunk in $domainChunks[$f]) {
            $combined = "$($chunk.text) $($chunk.search_text -join ' ')".ToLower()
            $hits = ($Terms | Where-Object { $combined -like "*$($_.ToLower())*" }).Count
            if ($hits -ge 1) { $phase1 += $chunk }
        }
    }
    Write-Host "  Fallback found: $($phase1.Count)" -ForegroundColor Yellow
}
if ($phase1.Count -eq 0) { Write-Host "No results found" -ForegroundColor Red; return }

# PHASE 2: Discover terms
Write-Host "`n[2/$totalPhases] Analyzing for domain terms..." -ForegroundColor Cyan
$tagFreq = @{}
$phase1 | ForEach-Object { $_.tags | Where-Object { $TAG_STOPLIST -notcontains $_ } | ForEach-Object { if ($tagFreq[$_]) { $tagFreq[$_]++ } else { $tagFreq[$_] = 1 } } }
$minFreq = [Math]::Max(2, [Math]::Floor($phase1.Count * 0.2))
$topTags = ($tagFreq.GetEnumerator() | Where-Object { $_.Value -ge $minFreq } |
    Sort-Object Value -Descending | Select-Object -First 15).Name

$discoveredKeywords = $phase1 | ForEach-Object { $_.search_keywords } | Where-Object { $_ -and $_.Length -ge 3 } | Group-Object |
    Where-Object { $_.Count -ge 2 } | Select-Object -ExpandProperty Name -First 20

$entities = @{}
$phase1 | ForEach-Object {
    if ($_.metadata.nlp_entities) {
        $_.metadata.nlp_entities.PSObject.Properties | ForEach-Object {
            $k = "$($_.Name)::$($_.Value)"
            if ($entities[$k]) { $entities[$k]++ } else { $entities[$k] = 1 }
        }
    }
}
$topEntities = ($entities.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10).Name

Write-Host "  Tags: $($topTags -join ', ')" -ForegroundColor Magenta
Write-Host "  Keywords: $($discoveredKeywords -join ', ')" -ForegroundColor Magenta

# PHASE 3: Related chunks (cross-domain)
Write-Host "`n[3/$totalPhases] Related chunks (cross-domain, max: $($limits.Phase3))..." -ForegroundColor Cyan
$refFreq = @{}
$phase1 | ForEach-Object { $_.related_chunks } | Where-Object { $_ } | ForEach-Object { if ($refFreq[$_]) { $refFreq[$_]++ } else { $refFreq[$_] = 1 } }
$relatedIds = ($refFreq.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First ($limits.Phase3 * 3)).Name
$phase3 = @()
if ($relatedIds) {
    foreach ($rid in $relatedIds) {
        if ($allChunksById.ContainsKey($rid)) { $phase3 += $allChunksById[$rid] }
    }
    $phase3 = @($phase3 | Sort-Object { $refFreq[$_.id] } -Descending | Select-Object -First $limits.Phase3)
}
Write-Host "  Found: $($phase3.Count)" -ForegroundColor Green

# PHASE 3.5: Learned KB (Standard / Deep / Exhaustive only)
$phase35 = @()
if (-not $quickSearch -and $limits.ContainsKey('Phase35')) {
    $learnedFile = "$outDir\detail\chunks.learned.jsonl"
    if (Test-Path $learnedFile) {
        Write-Host "`n[3.5/$totalPhases] Learned KB (max: $($limits.Phase35))..." -ForegroundColor Cyan
        $excludeIds35 = ($phase1 + $phase3).id
        $learnedChunks = Get-Content $learnedFile | ConvertFrom-Json
        $phase35 = @($learnedChunks | Where-Object {
            $chunk = $_
            $excludeIds35 -notcontains $chunk.id -and
            ($Terms | Where-Object { $chunk.text -match [regex]::Escape($_) }).Count -ge 1
        } | Sort-Object {
            $c = $_; ($Terms | Where-Object { $c.text -match [regex]::Escape($_) }).Count
        } -Descending | Select-Object -First $limits.Phase35)
        Write-Host "  Found: $($phase35.Count)" -ForegroundColor Green
    }
}
if ($quickSearch) {
    Write-Host "`n[4/$totalPhases] Queries/procedures (cross-domain, max: $($limits.Phase6))..." -ForegroundColor Cyan
    $excludeIds = ($phase1 + $phase3).id
    $phase6 = @()
    foreach ($domain in @("queries","troubleshooting","sop")) {
        $f = "$outDir\detail\chunks.$domain.jsonl"
        if (Test-Path $f) {
            $phase6 += Get-Content $f | ConvertFrom-Json | Where-Object {
                $chunk = $_
                ($Terms | Where-Object {
                    $chunk.text -match [regex]::Escape($_) -or ($chunk.search_text -and $chunk.search_text -match [regex]::Escape($_))
                }).Count -ge 1 -and $excludeIds -notcontains $chunk.id
            }
        }
    }
    $phase6 = @($phase6 | Sort-Object {
        $c = $_
        $termHits = ($Terms | Where-Object { $c.text -match [regex]::Escape($_) }).Count
        $syntaxBonus = if ($QUERY_SYNTAX_RE.IsMatch($c.text)) { 3 } else { 0 }
        $termHits + $syntaxBonus
    } -Descending | Select-Object -First $limits.Phase6)
    Write-Host "  Found: $($phase6.Count)" -ForegroundColor Green
    $allResults = $phase1 + $phase3 + $phase35 + $phase6
} else {

# PHASE 4: Deep dive with discovered terms
Write-Host "`n[4/$totalPhases] Deep dive with discovered terms (max: $($limits.Phase4))..." -ForegroundColor Cyan
$deepDiveTerms = ($topTags + $discoveredKeywords) | Select-Object -Unique
$excludeIds = ($phase1 + $phase3).id
$phase4 = @()
foreach ($f in $searchFiles) {
    $phase4 += $domainChunks[$f] | Where-Object {
        $chunk = $_
        $hits = ($deepDiveTerms | Where-Object {
            ($chunk.text -match [regex]::Escape($_)) -or
            ($chunk.search_text -and $chunk.search_text -match [regex]::Escape($_)) -or
            ($chunk.search_keywords -and $chunk.search_keywords -contains $_) -or
            ($chunk.tags -contains $_)
        }).Count
        $hits -ge 2 -and $excludeIds -notcontains $chunk.id
    }
}
$phase4 = @($phase4 | Sort-Object {
    $c = $_; ($deepDiveTerms | Where-Object { $c.tags -contains $_ -or ($c.search_keywords -and $c.search_keywords -contains $_) }).Count
} -Descending | Select-Object -First $limits.Phase4)
Write-Host "  Found: $($phase4.Count)" -ForegroundColor Green

# PHASE 5: Topic clusters
Write-Host "`n[5/$totalPhases] Topic clusters (max: $($limits.Phase5))..." -ForegroundColor Cyan
$clusterIds = $phase1.topic_cluster_id | Select-Object -Unique | Where-Object { $_ }
$excludeIds = ($phase1 + $phase3 + $phase4).id
$phase5 = @()
if ($clusterIds) {
    foreach ($f in $searchFiles) {
        $phase5 += $domainChunks[$f] | Where-Object {
            $clusterIds -contains $_.topic_cluster_id -and
            $excludeIds -notcontains $_.id -and
            $_.cluster_size -ge 3
        }
    }
}
$phase5 = @($phase5 | Sort-Object { $_.cluster_size } -Descending | Select-Object -First $limits.Phase5)
Write-Host "  Found: $($phase5.Count)" -ForegroundColor Green

# PHASE 6: Queries/procedures (cross-domain)
Write-Host "`n[6/$totalPhases] Queries/procedures (cross-domain, max: $($limits.Phase6))..." -ForegroundColor Cyan
$excludeIds = ($phase1 + $phase3 + $phase4 + $phase5).id
$allTerms = ($Terms + $deepDiveTerms) | Select-Object -Unique
$phase6 = @()
foreach ($domain in @("queries","troubleshooting","sop")) {
    $f = "$outDir\detail\chunks.$domain.jsonl"
    if (Test-Path $f) {
        $phase6 += Get-Content $f | ConvertFrom-Json | Where-Object {
            $chunk = $_
            ($allTerms | Where-Object {
                $chunk.text -match [regex]::Escape($_) -or ($chunk.search_text -and $chunk.search_text -match [regex]::Escape($_))
            }).Count -ge 1 -and $excludeIds -notcontains $chunk.id
        }
    }
}
$phase6 = @($phase6 | Sort-Object {
    $c = $_
    $termHits = ($allTerms | Where-Object { $c.text -match [regex]::Escape($_) }).Count
    $syntaxBonus = if ($QUERY_SYNTAX_RE.IsMatch($c.text)) { 3 } else { 0 }
    $termHits + $syntaxBonus
} -Descending | Select-Object -First $limits.Phase6)
Write-Host "  Found: $($phase6.Count)" -ForegroundColor Green

$phase7 = @(); $phase8 = @()

} # end non-Quick block

if ($deepSearch) {
    # PHASE 7: Fuzzy matching
    Write-Host "`n[7/$totalPhases] Fuzzy matching (max: $($limits.Phase7))..." -ForegroundColor Cyan
    $excludeIds = ($phase1 + $phase3 + $phase4 + $phase5 + $phase6).id
    $longTerms = $Terms | Where-Object { $_.Length -ge 5 }
    if ($longTerms) {
        foreach ($f in $searchFiles) {
            $phase7 += $domainChunks[$f] | Where-Object {
                $chunk = $_
                $hits = ($longTerms | Where-Object {
                    $prefix = $_.Substring(0, [Math]::Min(5, $_.Length))
                    ($chunk.search_text -and $chunk.search_text -match [regex]::Escape($prefix)) -or $chunk.text -match [regex]::Escape($prefix)
                }).Count
                $hits -ge 2 -and $excludeIds -notcontains $chunk.id
            }
        }
    }
    $phase7 = @($phase7 | Sort-Object {
        $c = $_; ($longTerms | Where-Object { ($c.search_text -and $c.search_text -match [regex]::Escape($_.Substring(0, [Math]::Min(5, $_.Length)))) -or $c.text -match [regex]::Escape($_.Substring(0, [Math]::Min(5, $_.Length))) }).Count
    } -Descending | Select-Object -First $limits.Phase7)
    Write-Host "  Found: $($phase7.Count)" -ForegroundColor Green

    # PHASE 8: Entity expansion (cross-domain)
    Write-Host "`n[8/$totalPhases] Entity expansion (cross-domain, max: $($limits.Phase8))..." -ForegroundColor Cyan
    $excludeIds = ($phase1 + $phase3 + $phase4 + $phase5 + $phase6 + $phase7).id
    if ($topEntities) {
        $seen8 = @{}; $phase8 = @()
                foreach ($c in $allChunksFlat) {
                    if ($excludeIds -notcontains $c.id -and -not $seen8.ContainsKey($c.id) -and $c.metadata.nlp_entities) {
                        $matched8 = ($topEntities | Where-Object {
                            $parts = $_ -split '::'
                            $c.metadata.nlp_entities.($parts[0]) -contains $parts[1]
                        }).Count -ge 1
                        if ($matched8) { $phase8 += $c; $seen8[$c.id] = 1 }
                    }
                }
                $phase8 = @($phase8 | Select-Object -First $limits.Phase8)
    }
    Write-Host "  Found: $($phase8.Count)" -ForegroundColor Green
}

# COMBINE & SCORE
if (-not $quickSearch) { $allResults = $phase1 + $phase3 + $phase35 + $phase4 + $phase5 + $phase6 + $phase7 + $phase8 }

$allResults | ForEach-Object {
    $chunk = $_
    $matchType = if ($phase1.id -contains $chunk.id) { "Initial" }
                 elseif ($phase3.id -contains $chunk.id) { "Related" }
                 elseif ($phase35.id -contains $chunk.id) { "Learned" }
                 elseif ($phase4.id -contains $chunk.id) { "DeepDive" }
                 elseif ($phase5.id -contains $chunk.id) { "Cluster" }
                 elseif ($phase6.id -contains $chunk.id) { "Query" }
                 elseif ($phase7.id -contains $chunk.id) { "Fuzzy" }
                 else { "Entity" }

    $score = 0.0
    $textLower = $chunk.text.ToLower()
    $searchLower = if ($chunk.search_text) { $chunk.search_text.ToLower() } else { $textLower }

    $termScore = 0
    foreach ($term in $Terms) {
        $t = $term.ToLower()
        $termScore += [Math]::Min(10, (([regex]::Matches($textLower, [regex]::Escape($t))).Count + ([regex]::Matches($searchLower, [regex]::Escape($t))).Count) * 2)
    }
    $score += [Math]::Min(40, $termScore)
    if ($topTags)           { $score += [Math]::Min(20, ($chunk.tags | Where-Object { $topTags -contains $_ }).Count * 4) }
    if ($discoveredKeywords -and $chunk.search_keywords){ $score += [Math]::Min(15, ($chunk.search_keywords | Where-Object { $discoveredKeywords -contains $_ }).Count * 3) }
    $score += switch ($matchType) { "Initial" {10} "Related" {7} "Learned" {8} "Query" {5} "DeepDive" {3} default {2} }

    $chunk | Add-Member -NotePropertyName 'MatchType' -NotePropertyValue $matchType -Force
    $chunk | Add-Member -NotePropertyName 'RelevanceScore' -NotePropertyValue ([Math]::Round($score, 2)) -Force
}

$STRIP_TOP   = @('search_text','search_keywords','related_chunks','raw_markdown','topic_cluster_id','cluster_size','text_raw','element_type')
$STRIP_META  = @('key_phrases','nlp_entities','file_path','chapter_id','page_start','page_end','topic','nlp_category')

# Reserve guaranteed slots for query/sop/troubleshooting chunks (Phase6)
$QUERY_FLOOR = 4
$phase6Ids   = @($phase6.id)
$guaranteed  = @($allResults | Where-Object { $phase6Ids -contains $_.id } |
    Sort-Object RelevanceScore -Descending | Select-Object -First $QUERY_FLOOR)
$guaranteedIds = @($guaranteed.id)
$remaining = @($allResults | Where-Object { $guaranteedIds -notcontains $_.id } |
    Sort-Object RelevanceScore -Descending | Select-Object -First ([Math]::Max(0, $MaxResults - $guaranteed.Count)))
$orderedResults = $guaranteed + $remaining

$finalResults = $orderedResults | ForEach-Object {
    $chunk = $_
    # Remove top-level extraneous fields
    foreach ($f in $STRIP_TOP) { $chunk.PSObject.Properties.Remove($f) }
    # Slim metadata — keep only doc_id
    if ($chunk.metadata) {
        $slim = [PSCustomObject]@{ doc_id = $chunk.metadata.doc_id }
        $chunk | Add-Member -NotePropertyName 'metadata' -NotePropertyValue $slim -Force
    }
    $chunk
}

Write-Host "`n=== COMPLETE ===" -ForegroundColor Green
Write-Host "Level: $Level | Total: $($finalResults.Count) chunks" -ForegroundColor Magenta
@("Initial","Related","Learned","DeepDive","Cluster","Query","Fuzzy","Entity") | ForEach-Object {
    $t = $_; $c = ($finalResults | Where-Object { $_.MatchType -eq $t }).Count
    if ($c -gt 0) { Write-Host "  $t`: $c" -ForegroundColor White }
}

$finalResults | ConvertTo-Json -Depth 5
