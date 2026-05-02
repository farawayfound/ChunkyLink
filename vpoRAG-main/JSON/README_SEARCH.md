# Search Scripts - Quick Reference

## Overview

Two PowerShell scripts provide intelligent search across the knowledge base:

- **Search-DomainAware.ps1** - 8-phase exhaustive search with auto-domain detection
- **Search-QueryChunks.ps1** - Query-specific search for Splunk/diagnostic queries

## Usage

### Basic Search (Standard - 285 chunks)

```powershell
powershell -Command "& 'Searches\Search-DomainAware.ps1' -Terms 'term1','term2','term3' -Query 'full user query for domain detection'"
```

### Deep Search (570 chunks)

```powershell
powershell -Command "& 'Searches\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'user query' -Level 'Deep'"
```

### Exhaustive Search (1140+ chunks)

```powershell
powershell -Command "& 'Searches\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'user query' -Level 'Exhaustive'"
```

### Query Chunk Search

```powershell
powershell -Command "& 'LocalSearches\Search-QueryChunks.ps1' -Terms 'splunk','gdvr','ams' -MaxResults 40"
```

### Manual Domain Selection

```powershell
powershell -Command "& 'Searches\Search-DomainAware.ps1' -Terms 'term1','term2' -Domains 'troubleshooting','queries' -Level 'Standard'"
```

## Parameters

### Search-DomainAware.ps1

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| -Terms | Yes | Array of search terms | - |
| -Query | No | Full user query for auto-domain detection | "" |
| -Domains | No | Manual domain selection | Auto-detect |
| -Level | No | Standard/Deep/Exhaustive | Standard |
| -MaxResults | No | Override max results | Level-based |

### Search-QueryChunks.ps1

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| -Terms | Yes | Array of search terms | - |
| -MaxResults | No | Maximum results to return | 40 |

## Domain Auto-Detection

| Pattern in Query | Detected Domain |
|------------------|-----------------|
| error, issue, problem, fail, broken | troubleshooting |
| splunk, kibana, sql, query, index= | queries |
| how to, steps, procedure, configure | sop |
| documentation, manual, guide, feature | manual |
| contact, team, escalate, who, phone | reference |
| what does, mean, definition, acronym | glossary |

**Default (no match):** troubleshooting + queries + sop

## 8-Phase Search Process

1. **Initial Search** - Match terms in target domains
2. **Term Discovery** - Extract frequent tags, keywords, entities
3. **Related Chunks** - Follow cross-references (cross-domain)
4. **Deep Dive** - Search with discovered terms (2+ matches)
5. **Topic Clusters** - Find chunks in same semantic clusters
6. **Queries/SOPs** - Cross-domain search in queries/troubleshooting/sop
7. **Fuzzy Matching** - Prefix matching (4+ char terms)
8. **Entity Expansion** - Match by NLP entities (cross-domain)

## Output Format

Both scripts return JSON with chunk objects containing:

- `id` - Unique chunk identifier
- `text` - Full text with breadcrumb
- `tags` - NLP-generated tags
- `search_keywords` - Searchable keywords
- `metadata` - Document metadata, NLP category, entities
- `related_chunks` - Cross-references
- `MatchType` - Initial/Related/DeepDive/Cluster/Query/Fuzzy/Entity (Domain-Aware only)
- `RelevanceScore` - Scoring for ranking (Domain-Aware only)

## Performance

| Level | Chunks | Time | Use Case |
|-------|--------|------|----------|
| Standard | 285 | 15-30s | Fast triage (90% of cases) |
| Deep | 570 | 30-45s | Complex multi-system issues |
| Exhaustive | 1140+ | 45-60s | Root cause analysis, outages |

## Best Practices

1. **Always start with Standard** - Sufficient for 90% of cases
2. **Provide -Query parameter** - Enables auto-domain detection
3. **Use Search-QueryChunks.ps1** - Before generating Splunk/diagnostic queries
4. **Expand progressively** - Only go to Deep/Exhaustive when user requests more details
5. **Execute from JSON directory** - Scripts use $PSScriptRoot for paths

## Troubleshooting

**No results found:**
- Check if terms exist in KB (try broader terms)
- Verify domain files exist in `detail/` folder
- Try manual domain selection with `-Domains`

**Script errors:**
- Ensure PowerShell 5.1+ is installed
- Run from JSON directory as working directory
- Check file paths are correct

**Slow performance:**
- Standard level is optimized for speed
- Only use Deep/Exhaustive when necessary
- Consider reducing -MaxResults for faster response

## Documentation

See `Searches/SearchLibraryJSON.md` for complete protocol and examples.
