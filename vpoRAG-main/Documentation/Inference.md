# Inference (Search)

## Overview

Amazon Q searches the KB and Jira tickets on every triage session. There are two modes — check `$SEARCH_MODE` in `Searches/config.ps1` to see which is active.

**MCP mode (default):** Amazon Q calls `search_kb` and `search_jira` directly as native tool calls via the MCP server at `192.168.1.29:8000`. No PowerShell scripts involved. Configure once in VS Code — see [Setup.md](Setup.md#4-connect-amazon-q-to-the-mcp-server).

**Local mode (fallback):** Amazon Q reads `JSON/Agents.md` and executes PowerShell scripts locally to filter chunks. Used when the MCP server is unreachable. Set `$SEARCH_MODE = "Local"` in `Searches/config.ps1`.

**Never use `@folder` to load JSON directly** — files exceed context limits at 75K+ tokens.

---

## MCP Search (default)

When `$SEARCH_MODE = "MCP"`, Amazon Q calls these tools natively — no `executeBash` needed:

```
search_kb(terms=[...], query="...", level="Standard")
search_jira(terms=[...], discovered=[...])
```

| Parameter | Notes |
|---|---|
| `level` | `Quick` / `Standard` / `Deep` / `Exhaustive` — controls search quality, not result count |
| `page` | Fetch pages 2+ until `has_more=false`; Standard=2 pages, Deep=3, Exhaustive=4 |

The server strips heavy fields and truncates `text` to 2000 chars per chunk before returning results (~2.4KB/chunk). 20 chunks per page, safely under Amazon Q's 100K output limit.

### Server-side performance

- **Startup warmup** — 33K chunks are preloaded into a module-level cache (keyed by file mtime) in a background thread when the server starts. First tool call after startup is instant rather than paying the 8s I/O cost.
- **Cache invalidation** — cache key includes mtime+size of every category file. After an index rebuild the next search automatically reloads from disk.
- **Warm search latency** — ~4.5s for Standard level (33K chunks, 6 phases).

---

## Local Search (fallback)

### Configuration

Two config files control search behavior:

**`Searches/config.ps1`** — PowerShell search settings (gitignored — copy from `Searches/config.example.ps1`):
```powershell
$SEARCH_MODE             = "Local"             # "MCP" or "Local"
$JSON_KB_DIR             = "C:\path\to\JSON"  # Absolute path to JSON output directory
$JSON_SEARCH_LEVEL       = "Standard"          # Quick / Standard / Deep / Exhaustive
$JSON_MAX_RESULTS        = 0                   # 0 = use level default
$JIRA_PRIMARY_SOURCE     = "sqlite"            # "sqlite", "csv", or "sql"
$JIRA_SEARCH_ALL_SOURCES = $false              # $true = merge all sources
$JIRA_LOCAL_DB           = "Searches\jira_local.db"
$JIRA_REMOTE_MYSQL_HOST  = "192.168.1.29"      # MCP server — used by sync_local_db.py
$JIRA_DPS_CSV_DIR        = "structuredData\JiraCSVexport\DPSTRIAGE"
$JIRA_RCA_CSV_DIR        = "structuredData\JiraCSVexport\POSTRCA"
```

**`Searches/config.py`** — Jira direct SQL connection settings for `jira_query.py` (`$JIRA_PRIMARY_SOURCE = "sql"` only):
```python
JIRA_SQL_SERVER   = r"VM0PWVPTSPL000"
JIRA_SQL_DATABASE = "VIDPROD_MAIN"
JIRA_SQL_DRIVER   = "ODBC Driver 17 for SQL Server"
```
Credentials stored in Windows Credential Manager — see [Setup.md](Setup.md).

---

## Search Scripts

```powershell
# KB search
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full query'"

# Jira search
powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms 'term1','term2'"
```

Run both simultaneously on every triage session. The KB search runs first — discovered terms from its Phase 2 output can be passed into the Jira search as `-DiscoveredTerms` to improve ticket matching. See [CSV-and-Jira.md](CSV-and-Jira.md) for full Jira search options including analytical modes (`count`, `oldest`).

---

## Search Levels

Configured via `$JSON_SEARCH_LEVEL` in `Searches/config.ps1`:

| Level | Phases | Max chunks | Time |
|-------|--------|------------|------|
| Quick | 4 | 75 | 10–20s |
| Standard | 6 | 185 | 20–50s |
| Deep | 8 | 460 | 50–90s |
| Exhaustive | 8 | 920 | 90s+ |

Start at Standard for most sessions. Expand to Deep or Exhaustive if fewer than 50 chunks are returned or the issue spans multiple systems. `$JSON_MAX_RESULTS = 0` uses the level default; set a positive integer to hard-cap results regardless of level.

---

## Domain-Aware Search Phases

`Search-DomainAware.ps1` runs searches in ordered phases, each targeting progressively broader scope:

| Phase | Label | Strategy |
|-------|-------|----------|
| 1 | Initial | Exact term match against `search_text` |
| 2 | Related | Expand via `related_chunks` IDs from Phase 1 hits |
| 3 | DeepDive | Tag overlap across all category files |
| 4 | Cluster | All chunks sharing `topic_cluster_id` with hits |
| 5 | Query | Dedicated `chunks.queries.jsonl` search |
| 6 | Fuzzy | Partial/stemmed term matching |
| 7 | Entity | Match against `nlp_entities` values |
| 8 | Keyword | Fallback against `search_keywords` field |

Phases 1–4 run at all levels. Phases 5–8 are added at Standard and above.

---

## PowerShell Search Patterns

```powershell
# Search specific category (fastest)
Get-Content "JSON\detail\chunks.troubleshooting.jsonl" | ConvertFrom-Json |
    Where-Object { $_.search_text -match "xumo" } | Select-Object -First 50

# Expand with related chunks
$matches = # ... initial results
$relatedIds = $matches.related_chunks | Select-Object -Unique
$related = Get-Content "JSON\detail\chunks.jsonl" | ConvertFrom-Json |
    Where-Object { $relatedIds -contains $_.id }
$allResults = ($matches + $related) | Sort-Object id -Unique

# Find all chunks in same topic cluster
Get-Content "JSON\detail\chunks.jsonl" | ConvertFrom-Json |
    Where-Object { $_.topic_cluster_id -eq $targetClusterId }
```

---

## Search Performance

Category-specific files are 2–15x faster than searching the unified file because each contains roughly 1/7th of all chunks:

| Index size | Category search | Unified search |
|------------|----------------|----------------|
| 1,000 chunks | ~0.5s | ~1s |
| 5,000 chunks | ~1s | ~7s |
| 10,000 chunks | ~2s | ~30s |

The search scripts target category files first and fall back to `chunks.jsonl` only when a category file doesn't exist.

### MCP search phase optimizations

Phase 4 (`DeepDive`) and Phase 6 (`Query`) previously scanned 22K+ chunks with per-term regex. Both now use `str.in` on the pre-built `_sl` field (lowercase text + search_text, built at load time). Phase 6 pre-filters on original search terms only before applying the full expanded term set for scoring. Combined with the startup chunk cache this brings Standard-level search from ~54s to ~4.5s on 33K chunks.

---

## Search Fields on Each Chunk

| Field | Contents |
|-------|----------|
| `search_text` | Flattened: text, breadcrumb, tags, key_phrases, all entity values |
| `search_keywords` | Expanded terms including auto-generated synonyms |
| `related_chunks` | IDs of semantically similar chunks from other documents |
| `topic_cluster_id` | Shared-tag cluster identifier |

These fields are populated by the indexer — see [BuildIndex.md](BuildIndex.md) for how they are generated.
