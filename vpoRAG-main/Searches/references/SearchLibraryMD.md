# Search Library - Markdown Edition

## Purpose
Search Markdown knowledge base files using PowerShell `Select-String` for AI context retrieval.

> **Domain auto-detection rules and expansion levels:** See `SearchLibraryJSON.md` in this directory.

## Knowledge Domains

```
MD/detail/
├── chunks.troubleshooting.md  # Problem-solving, error fixes
├── chunks.queries.md           # SQL/Splunk queries, code
├── chunks.sop.md               # Step-by-step procedures
├── chunks.manual.md            # Product documentation
├── chunks.reference.md         # Contacts, specs, org info
├── chunks.glossary.md          # Term definitions
├── chunks.general.md           # Uncategorized
└── chunks.md                   # Unified fallback
```

## Function: Search-MarkdownChunks

**Search Markdown files and return relevant chunks with context**

```powershell
function Search-MarkdownChunks {
    param(
        [string[]]$searchTerms,
        [string[]]$targetDomains = @(),
        [int]$contextLines = 5,
        [int]$maxResults = 50
    )
    
    $configPath = Join-Path $PSScriptRoot "..\\..\\indexers\\config.py"
    $outDir = (Select-String -Path $configPath -Pattern 'OUT_DIR\s*=\s*r?"(.+?)"').Matches.Groups[1].Value
    
    $searchFiles = @()
    if ($targetDomains.Count -eq 0) {
        $searchFiles = @("$outDir\detail\chunks.md")
    } else {
        foreach ($domain in $targetDomains) {
            $file = "$outDir\detail\chunks.$domain.md"
            if (Test-Path $file) { $searchFiles += $file }
        }
    }
    
    Write-Host "`n=== MARKDOWN SEARCH ===" -ForegroundColor Cyan
    Write-Host "Terms: $($searchTerms -join ', ')" -ForegroundColor Yellow
    Write-Host "Domains: $($targetDomains -join ', ')" -ForegroundColor Yellow
    
    $results = @()
    foreach ($file in $searchFiles) {
        foreach ($term in $searchTerms) {
            $matches = Select-String -Path $file -Pattern $term -Context $contextLines
            foreach ($match in $matches) {
                $results += @{
                    File = (Split-Path $file -Leaf)
                    Line = $match.LineNumber
                    Term = $term
                    Context = $match.Context
                    Text = $match.Line
                }
            }
        }
    }
    
    $results = $results | Sort-Object File, Line -Unique | Select-Object -First $maxResults
    Write-Host "Found: $($results.Count) matches" -ForegroundColor Green
    return $results
}
```

## Function: Get-MarkdownChunkById

**Retrieve specific chunk by ID**

```powershell
function Get-MarkdownChunkById {
    param([string]$chunkId)
    
    $configPath = Join-Path $PSScriptRoot "..\\..\\indexers\\config.py"
    $outDir = (Select-String -Path $configPath -Pattern 'OUT_DIR\s*=\s*r?"(.+?)"').Matches.Groups[1].Value
    $content = Get-Content "$outDir\detail\chunks.md" -Raw
    $pattern = "(?s)## $([regex]::Escape($chunkId))\s+(.+?)(?=\n## |\z)"
    
    if ($content -match $pattern) { return $matches[0] }
    return $null
}
```

## Function: Search-DomainAware-MD

**Domain-aware search — uses same domain detection rules as `SearchLibraryJSON.md`**

```powershell
function Search-DomainAware-MD {
    param(
        [string[]]$initialTerms,
        [string]$userQuery = "",
        [string[]]$targetDomains = @(),
        [int]$maxResults = 100
    )
    
    if ($targetDomains.Count -eq 0 -and $userQuery) {
        $query = $userQuery.ToLower()
        $domains = @()
        if ($query -match '\b(error|issue|problem|fail|not work|broken|stuck|timeout|crash|debug|fix|resolve)\b') { $domains += "troubleshooting" }
        if ($query -match '\b(splunk|kibana|sql|query|search|index=|sourcetype=|select|where|elasticsearch)\b') { $domains += "queries" }
        if ($query -match '\b(how to|steps|procedure|process|configure|setup|install|create|workflow)\b') { $domains += "sop" }
        if ($query -match '\b(documentation|manual|guide|feature|capability|specification|about|what is)\b') { $domains += "manual" }
        if ($query -match '\b(contact|team|escalate|who|phone|email|org|department)\b') { $domains += "reference" }
        if ($query -match '\b(what does|mean|definition|acronym|stands for|abbreviation)\b') { $domains += "glossary" }
        if ($domains.Count -eq 0) { $domains = @("troubleshooting", "queries", "sop") }
        $targetDomains = $domains | Select-Object -Unique
        Write-Host "Auto-detected domains: $($targetDomains -join ', ')" -ForegroundColor Magenta
    }
    
    $results = Search-MarkdownChunks -searchTerms $initialTerms -targetDomains $targetDomains -maxResults $maxResults
    return @{ Results = $results; SearchedDomains = $targetDomains; TotalMatches = $results.Count }
}
```

## Usage Examples

```powershell
# Search troubleshooting domain
$results = Search-MarkdownChunks -searchTerms @("xumo", "authentication") -targetDomains @("troubleshooting")
foreach ($r in $results) {
    Write-Host "`n[$($r.File):$($r.Line)] Match: $($r.Term)" -ForegroundColor Cyan
    Write-Host $r.Text
}

# Auto-detect domains from query
$result = Search-DomainAware-MD -initialTerms @("xumo", "error") -userQuery "Xumo device authentication error"

# Retrieve chunk by ID
$chunk = Get-MarkdownChunkById -chunkId "doc.pdf::ch01::p10-12::para::abc123"
```

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Search single domain | <1s | Fast text search |
| Search all domains | 1-2s | Parallel file search |
| Get chunk by ID | <0.5s | Regex match |
