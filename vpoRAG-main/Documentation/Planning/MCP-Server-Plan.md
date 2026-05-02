# MCP Server — Multi-Host Infrastructure Plan

## Overview

Migrate vpoRAG from a per-engineer local setup to a shared Ubuntu server (Intel Xeon, 64GB RAM)
accessible over the local network via SSH. The server exposes an MCP-compatible HTTP API that
replaces local PowerShell execution, centralizes the JSONL knowledge base, and provides a
resilient Jira data store with automatic CSV fallback.

**Current pain points this solves:**

| Problem | Current | After |
|---|---|---|
| KB drift | Each engineer maintains a local copy | Single source of truth on server |
| Index build cost | Runs on engineer's Windows laptop | Runs on Xeon (faster, consistent) |
| PowerShell dependency | Required on every client machine | Runs server-side only |
| Jira CSV staleness | Manual copy into each repo clone | Centralized, cron-refreshed |
| Multi-tenant search | No concurrency — one session at a time | FastMCP handles concurrent requests |
| spaCy/Tesseract install | Every engineer installs locally | Server-only dependency |

---

## Goals and Acceptance Criteria

### Goal 1 — MCP HTTP Server operational on Ubuntu

**Acceptance criteria:**
- `mcp_server/server.py` starts cleanly on the Xeon and listens on port 8000
- Amazon Q in VS Code on a Windows client can call all three tools via the MCP plugin or `executeBash curl`
- Concurrent calls from two or more engineers do not block or corrupt each other
- Server survives a client disconnect mid-request without crashing

### Goal 2 — `search_kb` tool replaces `Search-DomainAware.ps1`

**Acceptance criteria:**
- Accepts the same logical inputs: `terms`, `query`, `level` (Quick/Standard/Deep/Exhaustive), `domains`, `max_results`
- Implements all 8 search phases with identical phase labels (Initial, Related, DeepDive, Cluster, Query, Fuzzy, Entity, Keyword) and per-level chunk caps matching the existing `$EXPANSION_LEVELS` table
- Returns JSON with `MatchType` and `RelevanceScore` fields on each chunk — same schema as the PowerShell output
- Domain auto-detection from `query` text matches the existing keyword patterns in `Get-DomainFromQuery`
- Falls back to `chunks.jsonl` when category files are absent
- Result for a Standard search on a 5,000-chunk KB completes in under 10 seconds

### Goal 3 — `search_jira` tool replaces `Search-JiraTickets.ps1` + `jira_query.py`

**Acceptance criteria:**
- Tries live SQL (VIDPROD_MAIN via pyodbc) first; falls back to centralized CSV automatically on any connection failure
- CSV fallback reads the most recently modified file in the server's `data/JiraCSVexport/` directory
- Supports all existing modes: `top`, `count`, `oldest`, `custom`
- Supports `--discovered`, `--limit`, `--since`, `--ticket-type`, `--status`, `--client` parameters
- Merged results deduplicate by `Key` field (same as `Merge-JiraResults` in the PowerShell script)
- Returns identical JSON shape to the existing `jira_query.py` output so no changes are needed in `TriageAssistant.md`

### Goal 4 — Centralized JSONL knowledge base

**Acceptance criteria:**
- Category JSONL files (`chunks.*.jsonl`) live in a single canonical location on the server
- A `git pull` + `python build_index.py` triggered via the MCP `build_index` tool (or cron) keeps the KB current
- Engineers' `Searches/config.ps1` `$JSON_KB_DIR` is replaced by the MCP server URL — no local JSONL copies required
- The server's JSONL directory is readable by the MCP process and writable only by the build process

### Goal 5 — Centralized Jira CSV store with auto-refresh

**Acceptance criteria:**
- Two separate directories on the server hold the authoritative CSV exports:
  - `/srv/samba/share/dpstriageCSV/` — DPSTRIAGE ticket exports
  - `/srv/samba/share/postrcaCSV/` — POSTRCA ticket exports
- A cron job watches each directory and rotates in the latest CSV automatically
- The `search_jira` tool always reads the most recently modified CSV from each directory
- Engineers drop new exports into the Samba share; no manual server-side steps required
- Old exports are archived (not deleted) so rollback is possible

### Goal 7 — MySQL auto-sync from CSV drops

**Acceptance criteria:**
- A MySQL database on the server has two tables: `dpstriage_tickets` and `postrca_tickets`
- A watcher process (cron or inotify) detects new CSV files dropped into `/srv/samba/share/dpstriageCSV/` or `/srv/samba/share/postrcaCSV/`
- On detection, the sync script upserts rows: inserts new keys, updates existing keys only when the incoming `Updated` timestamp is later than the stored value
- The `search_jira` tool queries MySQL first; falls back to CSV if the DB is unavailable
- No duplicate rows — `Issue key` is the primary key in both tables

### Goal 6 — `build_index` tool for remote index rebuilds

**Acceptance criteria:**
- Calling the tool triggers `python build_index.py` on the server in the correct working directory
- Streaming log output is returned to the caller (or stored and retrievable)
- Only one build can run at a time — concurrent build requests are queued or rejected with a clear message
- Full rebuild (state file deletion) is supported via a `force_full` parameter

---

## Architecture

```
Ubuntu Xeon (local network, e.g. 192.168.1.50)
├── /srv/vpo_rag/                        ← git clone of this repo
│   ├── indexers/                        ← unchanged indexing engine
│   ├── Searches/                        ← jira_query.py reused by search_jira tool
│   └── JSON/                            ← canonical JSONL KB output
│
└── mcp_server/
    ├── server.py                        ← FastMCP HTTP server (port 8000)
    ├── tools/
    │   ├── search_kb.py                 ← Python port of Search-DomainAware.ps1
    │   ├── search_jira.py               ← Wraps jira_query.py + CSV fallback
    │   └── build_index.py               ← Subprocess trigger for indexer
    ├── data/
    │   └── JiraCSVexport/               ← Centralized CSV store
    │       ├── current/                 ← Most recent export (tool reads here)
    │       └── archive/                 ← Previous exports
    ├── config.py                        ← Server-side paths and settings
    └── requirements.txt
```

**Client side (Windows, each engineer):**
- Amazon Q MCP plugin configured to point at `http://192.168.1.50:8000/mcp`
- OR: `executeBash curl` calls in `JSON/Agents.md` replaced with MCP tool calls
- `Searches/config.ps1` retained for any remaining local PowerShell use but `$JSON_KB_DIR` updated

---

## Implementation Steps

### Phase 1 — Server environment setup (prerequisite)

1. SSH into the Ubuntu machine and create the service user and directory:
   ```bash
   sudo useradd -m -s /bin/bash vporag
   sudo mkdir -p /srv/vpo_rag
   sudo chown vporag:vporag /srv/vpo_rag
   ```

2. Clone the repo and install Python dependencies:
   ```bash
   sudo -u vporag git clone <repo-url> /srv/vpo_rag
   cd /srv/vpo_rag
   pip install -r requirements.txt
   python -m spacy download en_core_web_md
   sudo apt-get install tesseract-ocr   # for OCR support
   ```

3. Install ODBC Driver 17 for SQL Server (for live Jira SQL):
   ```bash
   # Microsoft's official Ubuntu install instructions
   curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
   curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list \
     | sudo tee /etc/apt/sources.list.d/mssql-release.list
   sudo apt-get update
   sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17
   pip install pyodbc keyring
   ```

4. Store Jira credentials on the server (one-time):
   ```bash
   python Searches/Connectors/jira_query.py --store-credentials
   ```
   > **Note:** `keyring` on Linux requires a secret service backend. Install `python3-secretstorage`
   > or use `keyrings.alt` as a file-based fallback:
   > `pip install keyrings.alt` and set `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring`
   > in the server's environment. For production, use a proper secret manager or environment variables.

5. Copy and configure `indexers/config.py` on the server with Linux paths:
   ```python
   SRC_DIR = "/srv/vpo_rag/source_docs"
   OUT_DIR = "/srv/vpo_rag/JSON"
   ```

---

### Phase 2 — MCP server scaffold

Install the MCP Python SDK:
```bash
pip install mcp fastapi uvicorn
```

**`mcp_server/server.py`** — minimal scaffold:
```python
# -*- coding: utf-8 -*-
"""MCP HTTP server — exposes search_kb, search_jira, build_index tools."""
from mcp.server.fastmcp import FastMCP
from tools import search_kb, search_jira, build_index as build_tool

mcp = FastMCP("vpoRAG")
mcp.tool()(search_kb.run)
mcp.tool()(search_jira.run)
mcp.tool()(build_tool.run)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

**`mcp_server/config.py`**:
```python
JSON_KB_DIR      = "/srv/vpo_rag/JSON"
JIRA_CSV_DIR     = "/srv/vpo_rag/mcp_server/data/JiraCSVexport/current"
JIRA_CSV_ARCHIVE = "/srv/vpo_rag/mcp_server/data/JiraCSVexport/archive"
REPO_DIR         = "/srv/vpo_rag"
INDEXER_SCRIPT   = "/srv/vpo_rag/indexers/build_index.py"
AUTH_TOKEN       = ""   # Set to a shared secret for local-network auth
```

---

### Phase 3 — `search_kb` tool (Python port of Search-DomainAware.ps1)

This is the largest single work item. The PowerShell script's logic maps cleanly to Python:

**Phase mapping:**

| PS Phase | Label | Python equivalent |
|---|---|---|
| 1 | Initial | `search_text` contains ≥2 terms (case-insensitive) |
| 2 | (internal) | Tag frequency analysis → `top_tags`, `discovered_keywords`, `top_entities` |
| 3 | Related | Expand `related_chunks` IDs from Phase 1 hits, cross-category |
| 4 | DeepDive | `top_tags + discovered_keywords` match ≥2 fields, exclude prior hits |
| 5 | Cluster | `topic_cluster_id` overlap with Phase 1, `cluster_size ≥ 3` |
| 6 | Query | `chunks.queries/troubleshooting/sop.jsonl` single-term match |
| 7 | Fuzzy | 5-char prefix match on terms ≥5 chars, ≥2 hits |
| 8 | Entity | `nlp_entities` value match against `top_entities` |

**Scoring formula** (replicate exactly from PS script):
- Term frequency in `text` + `search_text`: min(40, count × 2)
- Tag overlap with `top_tags`: min(20, count × 4)
- Keyword overlap with `discovered_keywords`: min(15, count × 3)
- Phase bonus: Initial=25, Related=20, Query=15, DeepDive=10, others=5

**Key implementation notes:**
- Load all JSONL files into memory once per request (same as PS `$domainChunks` dict)
- At 5,000 chunks × ~2KB average = ~10MB per request — well within 64GB RAM
- Use `re.escape()` for term matching to handle special characters (same as PS `[regex]::Escape()`)
- Domain auto-detection keyword patterns must match `Get-DomainFromQuery` exactly

**`mcp_server/tools/search_kb.py`** signature:
```python
async def run(
    terms: list[str],
    query: str = "",
    level: str = "Standard",       # Quick | Standard | Deep | Exhaustive
    domains: list[str] = [],
    max_results: int = 0
) -> dict:
    ...
```

---

### Phase 4 — `search_jira` tool

Thin wrapper around the existing `jira_query.py` with server-side CSV path resolution:

```python
async def run(
    terms: list[str],
    discovered: list[str] = [],
    mode: str = "top",             # top | count | oldest | custom
    limit: int = 0,
    since: int = 0,
    ticket_type: str = "both",     # both | dpstriage | postrca
    status: list[str] = [],
    client: str = ""
) -> dict:
    # 1. Try jira_query.query_jira(terms, ...)
    # 2. On any exception, fall back to CSV search
    # 3. If JIRA_SEARCH_BOTH_SOURCES, merge both
```

The CSV search logic can be ported directly from `Search-JiraTickets.ps1`'s `Search-JiraCSV`
function — it's pure data filtering with no PowerShell-specific constructs.

---

### Phase 5 — `build_index` tool

```python
import asyncio, subprocess
from pathlib import Path

_build_lock = asyncio.Lock()

async def run(force_full: bool = False) -> dict:
    if _build_lock.locked():
        return {"status": "busy", "message": "A build is already running"}
    async with _build_lock:
        if force_full:
            state = Path(config.JSON_KB_DIR) / "state" / "processing_state.json"
            state.unlink(missing_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "python", config.INDEXER_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(Path(config.INDEXER_SCRIPT).parent)
        )
        stdout, _ = await proc.communicate()
        return {"status": "done", "exit_code": proc.returncode, "log": stdout.decode()}
```

> **Note:** For large KBs the build can take several minutes. Consider returning a job ID
> immediately and polling a `/status` endpoint rather than blocking the MCP call. This is a
> Phase 5 enhancement — the blocking version is acceptable for Phase 2.

---

### Phase 6 — Jira CSV auto-refresh from Samba share

CSV exports are dropped by engineers into two Samba-shared directories on the server:
- `/srv/samba/share/dpstriageCSV/` — DPSTRIAGE exports
- `/srv/samba/share/postrcaCSV/` — POSTRCA exports

The `Search-JiraTickets.ps1` script already reads the most recently modified CSV from each
directory, so no rotation is needed for the PowerShell path. For the MCP `search_jira` tool,
add a cron job that archives stale exports to keep the directories clean:

```cron
# /etc/cron.d/vporag-csv-archive
# Daily at 02:00 — archive all but the newest CSV in each share directory
0 2 * * * vporag /srv/vpo_rag/mcp_server/scripts/archive_old_csvs.sh
```

**`archive_old_csvs.sh`**:
```bash
#!/bin/bash
archive_dir() {
    local dir="$1"
    local archive="$dir/archive"
    mkdir -p "$archive"
    # Keep newest, move the rest to archive/
    ls -t "$dir"/*.csv 2>/dev/null | tail -n +2 | xargs -I{} mv {} "$archive/"
}
archive_dir /srv/samba/share/dpstriageCSV
archive_dir /srv/samba/share/postrcaCSV
```

The `search_jira` MCP tool config points directly at the share directories:
```python
JIRA_DPS_CSV_DIR = "/srv/samba/share/dpstriageCSV"
JIRA_RCA_CSV_DIR = "/srv/samba/share/postrcaCSV"
```

Update `Searches/config.ps1` to match:
```powershell
$JIRA_DPS_CSV_DIR = "/srv/samba/share/dpstriageCSV"   # or UNC path from Windows
$JIRA_RCA_CSV_DIR = "/srv/samba/share/postrcaCSV"
```

---

### Phase 7 — MySQL auto-sync from CSV drops

MySQL is already installed on the server. Two tables store the ticket data, one per type.

#### Schema

```sql
CREATE TABLE dpstriage_tickets (
    issue_key    VARCHAR(32)  PRIMARY KEY,
    summary      TEXT,
    description  TEXT,
    status       VARCHAR(64),
    created      DATETIME,
    updated      DATETIME,
    root_cause   TEXT,
    resolution   TEXT,
    last_comment TEXT,
    vertical     VARCHAR(128),
    responsible_team VARCHAR(128),
    imported_at  DATETIME
);

CREATE TABLE postrca_tickets (
    issue_key    VARCHAR(32)  PRIMARY KEY,
    summary      TEXT,
    description  TEXT,
    status       VARCHAR(64),
    priority     VARCHAR(32),
    created      DATETIME,
    updated      DATETIME,
    root_cause   TEXT,
    resolution   TEXT,
    client       VARCHAR(128),
    vertical     VARCHAR(128),
    responsible_team VARCHAR(128),
    imported_at  DATETIME
);

CREATE TABLE csv_imports (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    filename     VARCHAR(256),
    ticket_type  ENUM('dpstriage','postrca'),
    imported_at  DATETIME,
    rows_inserted INT,
    rows_updated  INT
);
```

#### Sync script: `mcp_server/scripts/sync_jira_csv.py`

```python
# -*- coding: utf-8 -*-
"""Upsert DPSTRIAGE and POSTRCA CSV exports into MySQL."""
import sys, csv, glob, os
from datetime import datetime
from pathlib import Path

try:
    import mysql.connector
except ImportError:
    raise SystemExit("pip install mysql-connector-python")

try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import config
except ImportError:
    raise SystemExit("mcp_server/config.py not found")

DB = mysql.connector.connect(
    host=config.MYSQL_HOST, user=config.MYSQL_USER,
    password=config.MYSQL_PASS, database=config.MYSQL_DB
)

DPS_FIELDS = {
    'issue_key': 'Issue key', 'summary': 'Summary', 'description': 'Description',
    'status': 'Status', 'created': 'Created', 'updated': 'Updated',
    'root_cause': 'Custom field (Root Cause)',
    'resolution': 'Custom field (Resolution / Mitigation Solution)',
    'last_comment': 'Custom field (Last Comment)',
    'vertical': 'Custom field (Vertical)',
    'responsible_team': 'Custom field (Responsible Team)'
}
RCA_FIELDS = {
    'issue_key': 'Issue key', 'summary': 'Summary', 'description': 'Description',
    'status': 'Status', 'priority': 'Priority', 'created': 'Created', 'updated': 'Updated',
    'root_cause': 'Custom field (Root cause (text))',
    'resolution': 'Custom field (Resolution / Mitigation Solution)',
    'client': 'Custom field (Client)',
    'vertical': 'Custom field (Vertical)',
    'responsible_team': 'Custom field (Responsible Team)'
}

def parse_dt(s):
    for fmt in ("%b %d, %Y %I:%M %p", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try: return datetime.strptime(s.strip(), fmt)
        except: pass
    return None

def upsert_csv(csv_path, table, field_map):
    cur = DB.cursor()
    inserted = updated = 0
    with open(csv_path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            key = row.get('Issue key', '').strip()
            if not key: continue
            vals = {col: (row.get(src_col) or '').strip() for col, src_col in field_map.items()}
            vals['imported_at'] = datetime.utcnow()
            incoming_updated = parse_dt(vals.get('updated', ''))

            cur.execute(f"SELECT updated FROM {table} WHERE issue_key=%s", (key,))
            existing = cur.fetchone()
            if existing is None:
                cols = ', '.join(vals.keys())
                placeholders = ', '.join(['%s'] * len(vals))
                cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(vals.values()))
                inserted += 1
            elif incoming_updated and existing[0] and incoming_updated > existing[0]:
                set_clause = ', '.join(f"{c}=%s" for c in vals if c != 'issue_key')
                update_vals = [v for c, v in vals.items() if c != 'issue_key'] + [key]
                cur.execute(f"UPDATE {table} SET {set_clause} WHERE issue_key=%s", update_vals)
                updated += 1
    DB.commit()
    cur.close()
    return inserted, updated

def sync_dir(csv_dir, table, field_map, ticket_type):
    files = sorted(glob.glob(os.path.join(csv_dir, '*.csv')), key=os.path.getmtime, reverse=True)
    if not files:
        print(f"No CSV found in {csv_dir}")
        return
    latest = files[0]
    print(f"Syncing {ticket_type}: {os.path.basename(latest)}")
    ins, upd = upsert_csv(latest, table, field_map)
    cur = DB.cursor()
    cur.execute(
        "INSERT INTO csv_imports (filename, ticket_type, imported_at, rows_inserted, rows_updated) VALUES (%s,%s,%s,%s,%s)",
        (os.path.basename(latest), ticket_type, datetime.utcnow(), ins, upd)
    )
    DB.commit(); cur.close()
    print(f"  inserted={ins} updated={upd}")

if __name__ == '__main__':
    sync_dir(config.JIRA_DPS_CSV_DIR, 'dpstriage_tickets', DPS_FIELDS, 'dpstriage')
    sync_dir(config.JIRA_RCA_CSV_DIR, 'postrca_tickets',   RCA_FIELDS, 'postrca')
    DB.close()
```

#### Cron trigger (inotify-based, runs immediately on file drop)

```bash
# Install: sudo apt-get install inotify-tools
# /etc/systemd/system/vporag-csv-sync.service
[Unit]
Description=vpoRAG CSV → MySQL sync watcher
After=network.target mysql.service

[Service]
User=vporag
ExecStart=/bin/bash -c '
  inotifywait -m -e close_write \
    /srv/samba/share/dpstriageCSV \
    /srv/samba/share/postrcaCSV \
  | while read dir event file; do
      [[ "$file" == *.csv ]] && python /srv/vpo_rag/mcp_server/scripts/sync_jira_csv.py
    done'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Fallback cron (if inotify is unavailable):
```cron
# /etc/cron.d/vporag-csv-sync
# Every 30 minutes
*/30 * * * * vporag python /srv/vpo_rag/mcp_server/scripts/sync_jira_csv.py
```

#### `mcp_server/config.py` additions

```python
JIRA_DPS_CSV_DIR = "/srv/samba/share/dpstriageCSV"
JIRA_RCA_CSV_DIR = "/srv/samba/share/postrcaCSV"
MYSQL_HOST       = "localhost"
MYSQL_USER       = "vporag"
MYSQL_PASS       = ""   # set via environment variable MYSQL_PASS
MYSQL_DB         = "vporag_jira"
```

#### `search_jira` tool MySQL path (addition to Phase 4)

Before falling back to CSV, the `search_jira` tool queries MySQL:
```python
import mysql.connector

def query_mysql(terms, ticket_type, limit_dps=10, limit_rca=5):
    db = mysql.connector.connect(...)
    cur = db.cursor(dictionary=True)
    like_clauses = " OR ".join(
        f"(summary LIKE %s OR description LIKE %s OR root_cause LIKE %s OR resolution LIKE %s)"
        for _ in terms
    )
    params = [f"%{t}%" for t in terms for _ in range(4)]
    results = {}
    for table, limit, key in [('dpstriage_tickets', limit_dps, 'dpstriage'),
                               ('postrca_tickets',   limit_rca, 'postrca')]:
        if ticket_type not in ('both', key): continue
        cur.execute(f"SELECT * FROM {table} WHERE {like_clauses} ORDER BY updated DESC LIMIT %s",
                    params + [limit])
        results[key] = cur.fetchall()
    cur.close(); db.close()
    return results
```

This also unblocks the Jira Stage 2 roadmap item from `Advanced.md` (indexing ticket data for
cross-referencing with KB chunks).

---

### Phase 8 — Client configuration update

Each engineer updates two files:

**`Searches/config.ps1`** — add server URL, keep local path as fallback:
```powershell
$MCP_SERVER_URL  = "http://192.168.1.50:8000"
$MCP_AUTH_TOKEN  = "<shared-token>"
$JSON_KB_DIR     = "C:\local\fallback\JSON"   # kept for offline use
```

**`JSON/Agents.md`** — add MCP tool calls alongside existing PowerShell commands:
```
## MCP Search (preferred — server-side, no local deps)
Use the search_kb MCP tool with terms and query parameters.
Use the search_jira MCP tool for Jira ticket lookup.

## Local PowerShell fallback (when MCP server unreachable)
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' ..."
```

The Amazon Q MCP plugin is configured in VS Code settings:
```json
{
  "amazonQ.mcp.servers": [
    {
      "name": "vpoRAG",
      "url": "http://192.168.1.50:8000/mcp",
      "headers": { "Authorization": "Bearer <shared-token>" }
    }
  ]
}
```

---

## Additional Requirements

### Authentication
- Local network only — a shared bearer token in the `Authorization` header is sufficient
- Token is set in `mcp_server/config.py` (gitignored) and distributed to engineers out-of-band
- FastMCP supports middleware for token validation; add a simple check before tool dispatch
- Do NOT expose port 8000 outside the local network segment

### Systemd service (keep the server running)
```ini
# /etc/systemd/system/vporag-mcp.service
[Unit]
Description=vpoRAG MCP Server
After=network.target

[Service]
User=vporag
WorkingDirectory=/srv/vpo_rag/mcp_server
ExecStart=/usr/bin/python server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable vporag-mcp
sudo systemctl start vporag-mcp
```

### JSONL file locking
The build process writes to JSONL files while the search tool reads them. On Linux this is safe
for concurrent reads, but a build mid-write can serve a partial file. Mitigate by:
- Writing to a temp file and atomically renaming (`os.replace()`) — already the pattern in
  `IncrementalIndexer`; verify this holds on Linux paths
- The `build_index` tool's lock (`_build_lock`) prevents concurrent builds

### Offline / fallback behavior
Engineers should retain a local copy of the JSONL files (via `git pull`) for offline use.
The existing PowerShell scripts remain functional as a fallback when the MCP server is
unreachable. No changes to the indexer or PowerShell scripts are required for this.

### spaCy model on the server
The `en_core_web_md` model is only needed for index building — not for search. The `search_kb`
tool does pure string/regex matching against pre-computed `search_text` and `search_keywords`
fields. No spaCy dependency at search time.

### Windows Credential Manager vs Linux keyring
`jira_query.py` uses `keyring` which on Windows reads from Credential Manager. On Linux,
`keyring` requires a D-Bus secret service. For a headless server, use `keyrings.alt` with a
file-based store, or refactor `jira_query.py` to accept credentials via environment variables
(`JIRA_USER`, `JIRA_PASS`) as an alternative path. Environment variables are the simpler
production approach for a server process.

### Network path for source documents
If source documents (PDFs, PPTX, etc.) live on a Windows share, mount it on the Ubuntu server:
```bash
sudo mount -t cifs //windowsserver/share /mnt/vpo_docs -o username=...,password=...
```
Set `SRC_DIR = "/mnt/vpo_docs"` in the server's `indexers/config.py`. Add to `/etc/fstab` for
persistence across reboots.

---

## Dependency Summary (server-side additions)

| Package | Purpose |
|---|---|
| `mcp` | MCP Python SDK (FastMCP HTTP transport) |
| `fastapi` | HTTP layer used by FastMCP |
| `uvicorn` | ASGI server |
| `keyrings.alt` | File-based keyring backend for headless Linux |
| `msodbcsql17` | System package — ODBC Driver 17 for SQL Server |

All existing `requirements.txt` packages remain unchanged.

---

## Implementation Order (recommended)

| Step | Deliverable | Effort |
|---|---|---|
| 1 | Server env setup + repo clone + deps | 2–4 hours |
| 2 | MCP scaffold + `build_index` tool | 2–3 hours |
| 3 | `search_kb` tool (Phase 1–3 only) | 1 day |
| 4 | `search_kb` tool (Phase 4–8 + scoring) | 1 day |
| 5 | `search_jira` tool + CSV fallback port | 4–6 hours |
| 6 | Systemd service + auth middleware | 2 hours |
| 7 | Client config update + Agents.md update | 1 hour |
| 8 | Samba share dirs + CSV archive cron | 1–2 hours |
| 9 | MySQL schema + `sync_jira_csv.py` + inotify watcher | 4–6 hours |
| 10 | MySQL query path in `search_jira` tool | 2–3 hours |

Steps 1–7 are the MVP. Steps 8–9 are enhancements that can follow independently.

---

## Open Questions

| Question | Impact |
|---|---|
| What IP/hostname is the Xeon on the local network? | Needed for client config and Agents.md |
| Is the Jira SQL server (`VM0PWVPTSPL000`) reachable from the Ubuntu machine's network segment? | Determines whether live SQL works server-side or CSV-only is needed initially |
| Where do source documents live — local disk, Windows share, or git? | Determines `SRC_DIR` and mount strategy |
| Is there a preferred secret management approach (env vars, vault, keyring)? | Affects Jira credential storage on the server |
| Should the MCP server be accessible only on the local LAN or also via VPN? | Affects firewall rules and whether TLS is needed |
| Will engineers keep local JSONL copies (git pull) or go fully server-dependent? | Determines whether offline fallback needs to be documented |
