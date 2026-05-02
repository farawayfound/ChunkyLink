param([string[]]$Terms, [string]$Query="", [string]$Level="Standard")

$LEVELS = @{
    "Quick"      = @{ Phase1=12;  Phase3=5;   Phase6=3;   Total=20  }
    "Standard"   = @{ Phase1=45;  Phase3=55;  Phase35=15; Phase4=25; Phase5=20; Phase6=40; Total=185 }
    "Deep"       = @{ Phase1=90;  Phase3=110; Phase35=30; Phase4=50; Phase5=40; Phase6=80; Phase7=20; Phase8=70; Total=460 }
    "Exhaustive" = @{ Phase1=180; Phase3=220; Phase35=60; Phase4=100; Phase5=80; Phase6=160; Phase7=40; Phase8=140; Total=920 }
}
$TAG_STOPLIST = @("vpo","post","address","report","communications","client","lob","functiona",
    "functiona-client","clos","issue","spectrum","action-provide","action-select","action-enter",
    "action-configure","action-check","action-verify","action-review","action-update","select",
    "select-research","your","home","experience","usage","task","escalations-usage-task","role","mso","pid")
$QUERY_SYNTAX_RE = [regex]"index=|sourcetype=|[|] stats|[|] eval|[|] rex|[|] table|[|] dedup|[|] timechart|[|] transaction|\b\w+[.]\w+\s*:[^/]|OV-TUNE-FAIL|ov-tune-fail"

$outDir = (Resolve-Path 'JSON').Path
$limits = $LEVELS[$Level]
$quickSearch = ($Level -eq "Quick")
$deepSearch  = ($Level -eq "Deep" -or $Level -eq "Exhaustive")
$totalPhases = if ($deepSearch) { 8 } elseif ($quickSearch) { 4 } else { 6 }
$MaxResults  = $limits.Total

# Domain detection
$q = $Query.ToLower()
$domains = @("troubleshooting","queries","sop")
if ($q -match '\b(documentation|manual|guide|feature|what is)\b') { $domains += "manual" }
if ($q -match '\b(contact|team|escalate|who|phone|email|org)\b') { $domains += "reference" }
if ($q -match '\b(what does|mean|definition|acronym|stands for)\b') { $domains += "glossary" }
$domains = $domains | Select-Object -Unique

$searchFiles = @()
foreach ($d in $domains) {
    $f = "$outDir\detail\chunks.$d.jsonl"
    if (Test-Path $f) { $searchFiles += $f }
}
if ($searchFiles.Count -eq 0) { $searchFiles = @("$outDir\detail\chunks.jsonl") }

Write-Host "`n=== KB SEARCH: $totalPhases PHASES ($Level) ===" -ForegroundColor Cyan
Write-Host "Terms: $($Terms -join ', ')" -ForegroundColor Yellow

$domainChunks = @{}
foreach ($f in $searchFiles) { $domainChunks[$f] = Get-Content $f | ConvertFrom-Json }

$allCategoryFiles = Get-ChildItem "$outDir\detail\chunks.*.jsonl" | Where-Object { $_.Name -ne "chunks.jsonl" }
$allChunksFlat = @()
foreach ($af in $allCategoryFiles) { $allChunksFlat += Get-Content $af.FullName | ConvertFrom-Json }
$allChunksById = @{}
foreach ($c in $allChunksFlat) { $allChunksById[$c.id] = $c }

# Phase 1
Write-Host "`n[1/$totalPhases] Initial search..." -ForegroundColor Cyan
$phase1 = @()
foreach ($f in $searchFiles) {
    foreach ($chunk in $domainChunks[$f]) {
        $combined = "$($chunk.text) $($chunk.search_text -join ' ')".ToLower()
        $hits = ($Terms | Where-Object { $combined -like "*$($_.ToLower())*" }).Count
        if ($hits -ge 2) { $phase1 += $chunk }
    }
}
if ($phase1.Count -eq 0) {
    foreach ($f in $searchFiles) {
        foreach ($chunk in $domainChunks[$f]) {
            $combined = "$($chunk.text) $($chunk.search_text -join ' ')".ToLower()
            if (($Terms | Where-Object { $combined -like "*$($_.ToLower())*" }).Count -ge 1) { $phase1 += $chunk }
        }
    }
}
if ($phase1.Count -eq 0) { Write-Host "No results." -ForegroundColor Red; return }
Write-Host "  Found: $($phase1.Count)" -ForegroundColor Green

# Phase 2 — discover terms
$tagFreq = @{}
$phase1 | ForEach-Object { $_.tags | Where-Object { $TAG_STOPLIST -notcontains $_ } | ForEach-Object { if ($tagFreq[$_]) { $tagFreq[$_]++ } else { $tagFreq[$_] = 1 } } }
$minFreq = [Math]::Max(2, [Math]::Floor($phase1.Count * 0.2))
$topTags = ($tagFreq.GetEnumerator() | Where-Object { $_.Value -ge $minFreq } | Sort-Object Value -Descending | Select-Object -First 15).Name
$discoveredKeywords = $phase1 | ForEach-Object { $_.search_keywords } | Where-Object { $_ -and $_.Length -ge 3 } | Group-Object | Where-Object { $_.Count -ge 2 } | Select-Object -ExpandProperty Name -First 20
$entities = @{}
$phase1 | ForEach-Object { if ($_.metadata.nlp_entities) { $_.metadata.nlp_entities.PSObject.Properties | ForEach-Object { $k = "$($_.Name)::$($_.Value)"; if ($entities[$k]) { $entities[$k]++ } else { $entities[$k] = 1 } } } }
$topEntities = ($entities.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10).Name
Write-Host "  TopTags: $($topTags -join ', ')" -ForegroundColor DarkGray
Write-Host "  Discovered: $($discoveredKeywords -join ', ')" -ForegroundColor DarkGray

# Phase 3 — related chunks
Write-Host "`n[3/$totalPhases] Related chunks (max: $($limits.Phase3))..." -ForegroundColor Cyan
$refFreq = @{}
$phase1 | ForEach-Object { $_.related_chunks } | Where-Object { $_ } | ForEach-Object { if ($refFreq[$_]) { $refFreq[$_]++ } else { $refFreq[$_] = 1 } }
$relatedIds = ($refFreq.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First ($limits.Phase3 * 3)).Name
$phase3 = @()
if ($relatedIds) {
    foreach ($rid in $relatedIds) { if ($allChunksById.ContainsKey($rid)) { $phase3 += $allChunksById[$rid] } }
    $phase3 = @($phase3 | Sort-Object { $refFreq[$_.id] } -Descending | Select-Object -First $limits.Phase3)
}
Write-Host "  Found: $($phase3.Count)" -ForegroundColor Green

# Phase 3.5 — learned KB
$phase35 = @()
if (-not $quickSearch -and $limits.ContainsKey('Phase35')) {
    $learnedFile = "$outDir\detail\chunks.learned.jsonl"
    if (Test-Path $learnedFile) {
        Write-Host "`n[3.5/$totalPhases] Learned KB (max: $($limits.Phase35))..." -ForegroundColor Cyan
        $excludeIds35 = ($phase1 + $phase3).id
        $phase35 = @(Get-Content $learnedFile | ConvertFrom-Json | Where-Object {
            $c = $_; $excludeIds35 -notcontains $c.id -and ($Terms | Where-Object { $c.text -match [regex]::Escape($_) }).Count -ge 1
        } | Sort-Object { $c = $_; ($Terms | Where-Object { $c.text -match [regex]::Escape($_) }).Count } -Descending | Select-Object -First $limits.Phase35)
        Write-Host "  Found: $($phase35.Count)" -ForegroundColor Green
    }
}

if ($quickSearch) {
    $excludeIds = ($phase1 + $phase3).id
    $phase6 = @()
    foreach ($d in @("queries","troubleshooting","sop")) {
        $f = "$outDir\detail\chunks.$d.jsonl"
        if (Test-Path $f) {
            $phase6 += Get-Content $f | ConvertFrom-Json | Where-Object {
                $c = $_; ($Terms | Where-Object { $c.text -match [regex]::Escape($_) -or ($c.search_text -and $c.search_text -match [regex]::Escape($_)) }).Count -ge 1 -and $excludeIds -notcontains $c.id
            }
        }
    }
    $phase6 = @($phase6 | Sort-Object { $c = $_; ($Terms | Where-Object { $c.text -match [regex]::Escape($_) }).Count + (if ($QUERY_SYNTAX_RE.IsMatch($c.text)) { 3 } else { 0 }) } -Descending | Select-Object -First $limits.Phase6)
    $phase4 = @(); $phase5 = @(); $phase7 = @(); $phase8 = @()
    $allResults = $phase1 + $phase3 + $phase35 + $phase6
} else {
    # Phase 4 — deep dive (updated: HashSet for O(1) lookup)
    Write-Host "`n[4/$totalPhases] Deep dive..." -ForegroundColor Cyan
    $deepDiveTerms = ($topTags + $discoveredKeywords) | Select-Object -Unique
    $deepDiveSet   = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $deepDiveTerms | ForEach-Object { $null = $deepDiveSet.Add($_) }
    $excludeIds = ($phase1 + $phase3).id
    $phase4 = @()
    foreach ($f in $searchFiles) {
        $phase4 += $domainChunks[$f] | Where-Object {
            $c = $_
            $tagHits = ($c.tags | Where-Object { $deepDiveSet.Contains($_) }).Count
            $kwHits  = ($c.search_keywords | Where-Object { $deepDiveSet.Contains($_) }).Count
            $slHits  = ($deepDiveTerms | Where-Object { ($c.text + " " + $c.search_text) -match [regex]::Escape($_) }).Count
            ($tagHits + $kwHits + $slHits) -ge 2 -and $excludeIds -notcontains $c.id
        }
    }
    $phase4 = @($phase4 | Sort-Object { $c = $_; ($c.tags + $c.search_keywords | Where-Object { $deepDiveSet.Contains($_) }).Count } -Descending | Select-Object -First $limits.Phase4)
    Write-Host "  Found: $($phase4.Count)" -ForegroundColor Green

    # Phase 5 — clusters
    Write-Host "`n[5/$totalPhases] Topic clusters..." -ForegroundColor Cyan
    $clusterIds = $phase1.topic_cluster_id | Select-Object -Unique | Where-Object { $_ }
    $excludeIds = ($phase1 + $phase3 + $phase4).id
    $phase5 = @()
    if ($clusterIds) {
        foreach ($f in $searchFiles) {
            $phase5 += $domainChunks[$f] | Where-Object { $clusterIds -contains $_.topic_cluster_id -and $excludeIds -notcontains $_.id -and $_.cluster_size -ge 3 }
        }
    }
    $phase5 = @($phase5 | Sort-Object { $_.cluster_size } -Descending | Select-Object -First $limits.Phase5)
    Write-Host "  Found: $($phase5.Count)" -ForegroundColor Green

    # Phase 6 — queries/procedures (updated: pre-filter on original terms + top 5 discovered)
    Write-Host "`n[6/$totalPhases] Queries/procedures..." -ForegroundColor Cyan
    $excludeIds = ($phase1 + $phase3 + $phase4 + $phase5).id
    $allTerms = ($Terms + $deepDiveTerms) | Select-Object -Unique
    $p6FilterTerms = ($Terms + @($discoveredKeywords | Select-Object -First 5)) | Select-Object -Unique
    $phase6 = @()
    foreach ($d in @("queries","troubleshooting","sop")) {
        $f = "$outDir\detail\chunks.$d.jsonl"
        if (Test-Path $f) {
            $phase6 += Get-Content $f | ConvertFrom-Json | Where-Object {
                $c = $_
                $combined = "$($c.text) $($c.search_text)".ToLower()
                ($p6FilterTerms | Where-Object { $combined -like "*$($_.ToLower())*" }).Count -ge 1 -and $excludeIds -notcontains $c.id
            }
        }
    }
    $phase6 = @($phase6 | Sort-Object { $c = $_; $txt = $c.text.ToLower(); ($allTerms | Where-Object { $txt -like "*$($_.ToLower())*" }).Count + (if ($QUERY_SYNTAX_RE.IsMatch($c.text)) { 3 } else { 0 }) } -Descending | Select-Object -First $limits.Phase6)
    Write-Host "  Found: $($phase6.Count)" -ForegroundColor Green

    $phase7 = @(); $phase8 = @()
    $allResults = $phase1 + $phase3 + $phase35 + $phase4 + $phase5 + $phase6 + $phase7 + $phase8
}

# Score and label
$allResults | ForEach-Object {
    $c = $_
    $matchType = if     ($phase1.id -contains $c.id)  { "Initial" }
                 elseif ($phase3.id -contains $c.id)  { "Related" }
                 elseif ($phase35.id -contains $c.id) { "Learned" }
                 elseif ($phase4.id -contains $c.id)  { "DeepDive" }
                 elseif ($phase5.id -contains $c.id)  { "Cluster" }
                 elseif ($phase6.id -contains $c.id)  { "Query" }
                 elseif ($phase7.id -contains $c.id)  { "Fuzzy" }
                 else                                  { "Entity" }
    $tl = $c.text.ToLower()
    $score = [Math]::Min(40, ($Terms | ForEach-Object { [Math]::Min(10, (([regex]::Matches($tl,[regex]::Escape($_))).Count * 2)) } | Measure-Object -Sum).Sum)
    if ($topTags) { $score += [Math]::Min(20, ($c.tags | Where-Object { $topTags -contains $_ }).Count * 4) }
    if ($discoveredKeywords -and $c.search_keywords) { $score += [Math]::Min(15, ($c.search_keywords | Where-Object { $discoveredKeywords -contains $_ }).Count * 3) }
    $score += switch ($matchType) { "Initial" {10} "Related" {7} "Learned" {8} "Query" {5} "DeepDive" {3} default {2} }
    $c | Add-Member -NotePropertyName 'MatchType'      -NotePropertyValue $matchType              -Force
    $c | Add-Member -NotePropertyName 'RelevanceScore' -NotePropertyValue ([Math]::Round($score,2)) -Force
}

$STRIP_TOP   = @('search_text','search_keywords','related_chunks','raw_markdown','topic_cluster_id','cluster_size','text_raw','element_type','_sl')
$TEXT_LIMIT  = 3800
$QUERY_FLOOR = 4
$phase6Ids   = @($phase6.id)
$guaranteed  = @($allResults | Where-Object { $phase6Ids -contains $_.id } | Sort-Object RelevanceScore -Descending | Select-Object -First $QUERY_FLOOR)
$guaranteedIds = @($guaranteed.id)
$remaining   = @($allResults | Where-Object { $guaranteedIds -notcontains $_.id } | Sort-Object RelevanceScore -Descending | Select-Object -First ([Math]::Max(0, $MaxResults - $guaranteed.Count)))
$finalResults = ($guaranteed + $remaining) | Sort-Object RelevanceScore -Descending | ForEach-Object {
    $c = $_
    foreach ($f in $STRIP_TOP) { $c.PSObject.Properties.Remove($f) }
    if ($c.text -and $c.text.Length -gt $TEXT_LIMIT) { $c.text = $c.text.Substring(0,$TEXT_LIMIT) + "..." }
    if ($c.metadata) { $c | Add-Member -NotePropertyName 'metadata' -NotePropertyValue ([PSCustomObject]@{ doc_id = $c.metadata.doc_id }) -Force }
    $c
}

Write-Host "`n=== COMPLETE: $($finalResults.Count) chunks ===" -ForegroundColor Green
Write-Host "Phases: Initial=$(@($phase1).Count) Related=$(@($phase3).Count) Learned=$(@($phase35).Count) DeepDive=$(@($phase4).Count) Cluster=$(@($phase5).Count) Query=$(@($phase6).Count)" -ForegroundColor DarkGray
$finalResults | Select-Object id, MatchType, RelevanceScore, @{N='text_preview';E={$_.text.Substring(0,[Math]::Min(120,$_.text.Length))}} | Format-Table -AutoSize -Wrap
