# CSV and Jira Integration

## CSV Processing

### Overview

Any CSV file placed in `SRC_DIR` is automatically detected and indexed alongside PDFs and other documents. No configuration required.

**Auto-detection:**
- Jira ticket exports (detected by headers: Summary, Resolution, Vertical, Root Cause, Status)
- Generic tabular data (any CSV with text columns)

**No additional dependencies** — uses Python standard library only.

### Usage

Place CSV in `SRC_DIR` and run the indexer:

```bash
cd indexers
python build_index.py
```

Each row becomes one searchable chunk with NLP enrichment and cross-references to other documents.

### What gets extracted

- Ticket/case IDs: `SCI000012531490`, `DPSTRIAGE-12345`
- Error codes: `STBH-3802`, `GDVR-1004`, `RLC-1002`
- INC references: `INC000034658518`
- Known issue refs: `POSTRCA-31478`, `CEITEAM-6709`
- Resolution type classification (10 types: `inc_created`, `box_swap`, `billing_hits`, `known_issue`, `self_resolved`, `not_reproducible`, `working_as_designed`, `customer_fix`, `vsc_provider_fix`, `third_party_fix`)

### Chunk metadata

```json
{
  "metadata": {
    "source_type": "csv_data",
    "csv_type": "jira_tickets",
    "row_number": 2,
    "primary_column": "Summary",
    "technical_codes": ["SCI000012531490", "STBH-3802"],
    "nlp_category": "troubleshooting",
    "nlp_entities": {"ORG": ["Spectrum"], "PRODUCT": ["STVA"]},
    "key_phrases": ["black screen", "channel 2"]
  }
}
```

### Search examples

```powershell
# Find by resolution type
Get-Content chunks.jsonl | ConvertFrom-Json |
    Where-Object { $_.metadata.resolution_type -eq 'box_swap' }

# Find by error code
Get-Content chunks.jsonl | ConvertFrom-Json |
    Where-Object { $_.tags -contains 'stbh-3802' }

# Filter CSV vs documents
$csv  = Get-Content chunks.jsonl | ConvertFrom-Json | Where-Object { $_.metadata.source_type -eq 'csv_data' }
$docs = Get-Content chunks.jsonl | ConvertFrom-Json | Where-Object { $_.metadata.source_type -ne 'csv_data' }
```

### Limitations

- Excel (`.xlsx`) not supported — export to CSV first
- Row-level chunking only (no hierarchical routing)
- Works best with substantial text columns

---

## Jira Integration

### Architecture

Two-tier setup: a MySQL database on the MCP server (`192.168.1.29`) is the authoritative source; a local SQLite mirror on the Windows client is the default search target.

| Tier | Location | Used by |
|------|----------|---------|
| Remote MySQL | MCP server `jira_db` | MCP mode (`search_jira` tool) |
| Local SQLite | `Searches/jira_local.db` | Local mode (`Search-JiraTickets.ps1`) |
| CSV exports | `structuredData/JiraCSVexport/` | Offline fallback |
| VIDPROD_MAIN SQL | `VM0PWVPTSPL000` (intranet) | Optional direct query |

### Ticket types searched

| Type | Purpose |
|------|---------|
| `DPSTRIAGE` | Recent single-customer issues — find similar symptoms |
| `POSTRCA` | Documented known problems — find known root causes |

### Syncing the local SQLite mirror

The SQLite mirror is populated by pulling from the remote MySQL on the MCP server:

```bash
python Setup/sync_local_db.py
```

Reads connection settings (`$JIRA_REMOTE_MYSQL_*`) from `Searches/config.ps1`. Syncs both `dpstriage` and `postrca` tables using an `Updated`-guard upsert — only new/changed rows are written. Run periodically (e.g. weekly) to keep the mirror current.

### JSON KB sync

To sync the 7 category JSONL files from the MCP server:

```powershell
powershell -Command "& 'Setup\Sync-JSONIndex.ps1'"
powershell -Command "& 'Setup\Sync-JSONIndex.ps1' -Force"  # force regardless of timestamps
```

### Query flow (Local mode)

```
Search-JiraTickets.ps1
  ├── $JIRA_PRIMARY_SOURCE = "sqlite" → query_local_db.py --db jira_local.db
  │     Pass 1: TOP 10 DPSTRIAGE + TOP 5 POSTRCA (original terms)
  │     Pass 2: TOP 5 DPSTRIAGE + TOP 3 POSTRCA (discovered terms, exclude Pass 1 IDs)
  │     Total cap: ~23 rows
  │
  ├── $JIRA_PRIMARY_SOURCE = "csv"    → CSV files in $JIRA_DPS_CSV_DIR / $JIRA_RCA_CSV_DIR
  │     Single-pass, no Pass 2 discovered terms
  │
  └── $JIRA_PRIMARY_SOURCE = "sql"    → jira_query.py (pyodbc, intranet only)
        Pass 1 + Pass 2, same caps as sqlite
```

Set `$JIRA_SEARCH_ALL_SOURCES = $true` to query all three sources and merge by `Key`.

### Relevance scoring

Summary matches weighted 2x vs Description (applies to both SQLite and SQL modes):

```sql
(CASE WHEN Summary     LIKE ? THEN 2 ELSE 0 END +
 CASE WHEN Description LIKE ? THEN 1 ELSE 0 END) AS RelevanceScore
```

### Keeping CSV exports current

Used when `$JIRA_PRIMARY_SOURCE = "csv"` or `$JIRA_SEARCH_ALL_SOURCES = $true`:

1. Run this JQL in Jira:
   ```
   project IN ("Digital Platforms Support Triage", "Post RCA")
   AND created >= startOfMonth(-2)
   AND Status != Cancelled
   AND NOT (project = "Digital Platforms Support Triage" AND Status = Backlog)
   ORDER BY updated DESC
   ```
2. Export → CSV (max 1000 rows), drop into `structuredData/JiraCSVexport/DPSTRIAGE/` or `POSTRCA/`

### Usage from Amazon Q

```powershell
# Run both searches simultaneously — every session
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full query'"
powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms 'term1','term2'"
```

### Analytical queries

Use `--mode` for volume/trend questions — never answer "how many" from TOP 10:

```bash
python Searches/Connectors/jira_query.py --mode count term1 term2
python Searches/Connectors/jira_query.py --mode oldest term1 term2
```

(Requires `$JIRA_PRIMARY_SOURCE = "sql"` and intranet access.)

### Configuration

`Searches/config.ps1` (Local mode):
```powershell
$JIRA_PRIMARY_SOURCE     = "sqlite"              # "sqlite", "csv", or "sql"
$JIRA_SEARCH_ALL_SOURCES = $false                # $true = merge all sources
$JIRA_LOCAL_DB           = "Searches\jira_local.db"
$JIRA_REMOTE_MYSQL_HOST  = "192.168.1.29"        # MCP server — used by sync_local_db.py
$JIRA_REMOTE_MYSQL_PORT  = 3306
$JIRA_REMOTE_MYSQL_USER  = "jira_user"
$JIRA_REMOTE_MYSQL_PASS  = ""                    # Set your password
$JIRA_REMOTE_MYSQL_DB    = "jira_db"
$JIRA_DPS_CSV_DIR        = "structuredData\JiraCSVexport\DPSTRIAGE"
$JIRA_RCA_CSV_DIR        = "structuredData\JiraCSVexport\POSTRCA"
```

`Searches/config.py` (direct SQL only):
```python
JIRA_SQL_SERVER   = r"VM0PWVPTSPL000"
JIRA_SQL_DATABASE = "VIDPROD_MAIN"
JIRA_SQL_DRIVER   = "ODBC Driver 17 for SQL Server"
```
