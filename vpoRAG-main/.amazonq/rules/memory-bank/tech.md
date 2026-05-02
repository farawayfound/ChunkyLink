# vpoRAG â€” Technology Stack

## Languages
- **Python 3.x** â€” indexing engine, Jira connector, UI backend
- **PowerShell 5.1+** â€” search scripts (Search-DomainAware.ps1, Search-JiraTickets.ps1)
- **JavaScript / HTML / CSS** â€” UI frontend (vanilla, no framework)

## Python Dependencies (`requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| pymupdf | >=1.26.0 | PDF text/block extraction, image extraction |
| pdfplumber | >=0.11.4 | PDF table extraction (line-based strategy) |
| pillow | >=10.4.0 | Image processing for OCR pipeline |
| python-pptx | >=0.6.23 | PPTX slide/shape text extraction |
| python-docx | >=1.1.2 | DOCX paragraph/heading extraction |
| rapidfuzz | >=3.9.6 | Fuzzy deduplication (token_set_ratio) |
| spacy | >=3.8.0 | NLP: classification, tagging, entity extraction, word vectors |
| pytesseract | >=0.3.10 | OCR wrapper for Tesseract |
| pyodbc | latest | Jira SQL Server connection (ODBC Driver 17/18) |
| keyring | latest | Windows Credential Manager for Jira credentials |
| camelot-py[cv] | optional | Advanced table extraction (disabled by default, requires Ghostscript â€” not in requirements.txt) |

## UI Dependencies (`UI/requirements.txt`)
- flask, flask-socketio â€” web server + real-time log streaming

## NLP Model
`en_core_web_md` (spaCy, ~40MB) â€” required for word vectors used in cross-reference similarity scoring. Install: `python -m spacy download en_core_web_md`

## External Tools (Optional)
- **Tesseract OCR**: Windows install to `C:\Program Files\Tesseract-OCR\` or user AppData path configured in `TESSERACT_PATH`
- **Ghostscript**: Required only if `ENABLE_CAMELOT = True`
- **ODBC Driver 17 for SQL Server**: Required for live Jira SQL queries

## Configuration Files

### `indexers/config.py` (gitignored â€” copy from config.example.py)
```python
SRC_DIR = r"C:\path\to\documents"      # Source documents
OUT_DIR = r"C:\path\to\JSON"           # Output JSONL files
PARA_TARGET_TOKENS = 512               # Chunk size (~4 chars/token)
PARA_OVERLAP_TOKENS = 128              # Chunk overlap
MIN_CHUNK_TOKENS = 16                  # Minimum chunk size
CHUNK_QUALITY_MIN_WORDS = 10           # Quality filter threshold
MAX_ROUTER_SUMMARY_CHARS = 3000        # Router summary length cap
MAX_HIERARCHY_DEPTH = 6                # PDF TOC depth limit
DEDUPLICATION_INTENSITY = 1            # 0=off, 1=exact, 2-9=fuzzy (97%â†’76%)
ENABLE_CROSS_FILE_DEDUP = False        # Cross-file/cross-run dedup (adds O(n*m) comparisons)
ENABLE_AUTO_CLASSIFICATION = True      # NLP vs filename-based classification
ENABLE_AUTO_TAGGING = True             # Hybrid: NLP auto-tags + CONTENT_TAGS phrase matches always merged
MAX_TAGS_PER_CHUNK = 25                # Tag limit per chunk (cap applied after NLP category promotion)
ENABLE_CROSS_REFERENCES = True         # Semantic linking
ENABLE_OCR = True                      # Image text extraction
ENABLE_CAMELOT = False                 # Advanced table extraction (slow)
MAX_RELATED_CHUNKS = 5                 # Cross-refs per chunk
MIN_SIMILARITY_THRESHOLD = 0.65        # spaCy similarity cutoff (lowered from 0.7 for denser clusters)
TAG_STOPLIST = { ... }                 # NLP noise tags excluded from Phase 2/4 search scoring
PARALLEL_OCR_WORKERS = 4              # ThreadPoolExecutor workers for OCR
TESSERACT_PATH = r"C:\Users\...\Tesseract-OCR"
TERM_ALIASES = {}                      # Empty = auto-generate from corpus
DOC_PROFILES = { ... }                 # Filename-pattern â†’ category (used when auto-classify=False)
CONTENT_TAGS = { ... }                 # 80+ VPO domain keywordâ†’tag mappings; always applied regardless of ENABLE_AUTO_TAGGING
```

### `Searches/config.ps1` (gitignored)
```powershell
# PRIMARY SWITCH
$SEARCH_MODE = "MCP"                   # "MCP" or "Local"

# MCP mode settings
$MCP_SERVER_URL = "http://192.168.1.29:8000"
$MCP_SSH_USER = "vpomac"
$MCP_SSH_KEY  = "$HOME\.ssh\vporag_key"
$MCP_SEARCH_LEVEL = "Quick"            # default level for search_kb
$MCP_JIRA_SOURCE = "mysql"             # informational â€” actual setting in mcp_server/config.py

# Local mode settings
$JSON_KB_DIR = "C:\...\JSON"           # Absolute path to JSON output dir
$JSON_SEARCH_LEVEL = "Standard"        # Quick/Standard/Deep/Exhaustive
$JSON_MAX_RESULTS = 0                  # 0 = use level default
$JIRA_PRIMARY_SOURCE = "sqlite"        # "sqlite", "csv", or "sql"
$JIRA_SEARCH_ALL_SOURCES = $false      # Merge all sources and dedup by Key
$JIRA_LOCAL_DB = "Setup\Local\jira_local.db"
$JIRA_REMOTE_MYSQL_HOST = "192.168.1.29"
$JIRA_REMOTE_MYSQL_PORT = 3306
$JIRA_REMOTE_MYSQL_USER = "jira_user"
$JIRA_REMOTE_MYSQL_PASS = ""
$JIRA_REMOTE_MYSQL_DB   = "jira_db"
$JIRA_DPS_CSV_DIR = "structuredData\JiraCSVexport\DPSTRIAGE"
$JIRA_RCA_CSV_DIR = "structuredData\JiraCSVexport\POSTRCA"
```

### `Searches/config.py`
```python
JIRA_SQL_SERVER   = r"VM0PWVPTSPL000"
JIRA_SQL_DATABASE = "VIDPROD_MAIN"
JIRA_SQL_DRIVER   = "ODBC Driver 17 for SQL Server"
```
Credentials stored in Windows Credential Manager under service key `vpoRAG_Jira`.

## Search Level Profiles (Search-DomainAware.ps1 / search_kb)
| Level | Phases | Scored pool | Pages (MCP) | Chunks delivered | Time |
|---|---|---|---|---|---|
| Quick | 4 | 20 | 1 | 20 | 10â€“20s |
| Standard | 6 | 185 | 2 | 40 | 20â€“50s |
| Deep | 8 | 460 | 3 | 60 | 50â€“90s |
| Exhaustive | 8 | 920 | 4 | 80 | 90s+ |

Each MCP page is 20 chunks (~60â€“75K chars), safely under the 100K limit. Pages 2+ are served from a server-side result cache (~2ms vs ~25s for page 1).

## Development Commands
```bash
# Install
pip install -r requirements.txt
python -m spacy download en_core_web_md
python Setup/Local/check_deps.py

# Build index (incremental, with cross-refs)
cd indexers
python build_index.py

# Full rebuild (use run_build.sh on server, or delete state locally)
del JSON\state\processing_state.json
python build_index.py

# Full rebuild on MCP server (via run_build.sh â€” --user is required)
# ssh in and run: /srv/vpo_rag/mcp_server/scripts/run_build.sh --full --user=P3315113

# Two-stage build
python scripts/build_index_incremental.py
python scripts/build_cross_references.py

# Store Jira credentials (one-time)
python Searches/Connectors/jira_query.py --store-credentials

# Launch Web UIs
UI/Indexer/RUN_UI.bat              # Index builder      â†’ http://localhost:5000
UI/MCPdashboard/RUN_DASHBOARD.bat  # MCP Dashboard (local/SSH) â†’ http://localhost:5001
# MCP Dashboard (always-on server deployment) â†’ http://192.168.1.29:5001

# Run tests
cd indexers
python tests/test_json_indexer.py
```

## Output Format
JSONL (one JSON object per line) â€” chosen for streaming reads, incremental appends, and line-by-line parsing without loading full files into memory.

## CI/CD
`.gitlab-ci.yml` present â€” GitLab CI pipeline configured for the project.

## MCP Server

| Property | Value |
|---|---|
| Host | `192.168.1.29` (Ubuntu 24.04, iMac Pro) |
| Port | `8000` |
| Endpoint | `http://192.168.1.29:8000/mcp` |
| Service | `vporag-mcp` (systemd, auto-start) |
| App root | `/srv/vpo_rag/` |
| Venv | `/srv/vpo_rag/venv/` |
| JSON index | `/srv/vpo_rag/JSON/detail/` |
| Source docs | `/srv/vpo_rag/source_docs/` |
| Jira CSV dirs | `/srv/samba/share/dpstriageCSV/` Â· `/srv/samba/share/postrcaCSV/` |
| Jira DB | MySQL 8.0 `jira_db` â€” tables `dpstriage_tickets`, `postrca_tickets` |
| Credentials file | `/etc/vporag/mcp.env` (root:vporag, 640) |
| Access log | `/srv/vpo_rag/JSON/logs/mcp_access.log` (JSONL, daily rotation, 30 days) |

**SSH access (for maintenance only â€” never for search):**
```
Host: vpomac@192.168.1.29
Key:  C:\Users\P3315113\.ssh\vporag_key  (permissions: owner-only â€” CHTR\P3315113:(F))
```
```powershell
ssh -i C:\Users\P3315113\.ssh\vporag_key -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 vpomac@192.168.1.29
```

**Deploying files to the MCP server â€” ALWAYS use Deploy-ToMCP tooling:**
- Credentials are stored in `Setup/secrets.env` (gitignored â€” never committed)
- Never use raw `scp` or `ssh sudo` commands directly â€” always go through the deploy tooling
- `Setup/secrets.env` holds: `MCP_HOST`, `MCP_USER`, `MCP_SSH_KEY`, `MCP_SUDO_PASS`, `MCP_APP_ROOT`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASS`, `MYSQL_DB`
- `Setup/Deploy-ToMCP.ps1` â€” PowerShell helper; dot-sourceable; exposes `Invoke-McpScp`, `Invoke-McpSsh`, `Deploy-Files`, `Restart-McpService`
- `Setup/Run-OnMcp.ps1` â€” PowerShell helper for **running commands and capturing output**; dot-sourceable; exposes `Invoke-OnMcp`, `Invoke-PythonOnMcp`, `Invoke-MySqlOnMcp`
- `Setup/Deploy-ToMCP.bat` â€” cmd.exe launcher

```
# Deploy one or more files and restart both services
Setup\Deploy-ToMCP.bat mcp_server/tools/search_jira.py Searches/Connectors/jira_query.py

# Restart services only (no file upload)
Setup\Deploy-ToMCP.bat
```

**Preferred invocation from `executeBash` (avoids cmd.exe argument parsing issues):**
```
powershell -ExecutionPolicy Bypass -Command "& 'Setup\Deploy-ToMCP.ps1' -Files @('UI/MCPdashboard/templates/index.html','UI/MCPdashboard/static/app.js') -RestartService"
```

**Critical path requirements for scp/ssh to work correctly:**
- All Windows paths passed to `scp`/`ssh` must use forward slashes (backslashes cause "filename syntax incorrect")
- `Deploy-ToMCP.ps1` normalizes paths automatically via `-replace '\\', '/'`
- Script-scope variables (`$MCP_SSH_KEY`, `$REMOTE`, etc.) must be accessed as `$script:VAR` inside functions when the script is invoked via `&` (not dot-sourced)
- Always invoke via `Deploy-ToMCP.bat` or `powershell -Command "& 'Setup\Deploy-ToMCP.ps1' ..."` â€” never via `powershell -File` (breaks array param passing from cmd.exe)
- sudo password is injected via stdin (`echo $pass | sudo -S ...`) â€” no interactive terminal needed
- `Deploy-Files` runs `sudo sh -c 'mv $tmp $remote && chown vporag:vporag $remote'` in a **single SSH call per file** â€” never split mv and chown into separate SSH calls (causes hangs and leaves files owned by root)
- `Restart-McpService` restarts **both** `vporag-mcp` and `vporag-dashboard` in a **single SSH call** â€” never restart them in separate SSH connections (causes hangs)
- Deployed files are automatically `chown vporag:vporag` â€” files owned by root are unreadable by the `vporag` service user, causing stale content to be served
- If the deploy hangs, retry the identical command once â€” transient SSH hangs are normal; the consolidated single-call design minimises this risk

**MCP tools** (`search_kb`, `search_jira`, `build_index`) are native Amazon Q tool calls registered in `C:\Users\<you>\.aws\amazonq\agents\default.json`. They are NOT invoked via SSH or executeBash.

**User identity:** Each engineer adds a personal Bearer token to the `headers` block of the `vpoMac` entry in `default.json`:
```json
"headers": { "Authorization": "Bearer vporag-P3315113" }
```
In the Amazon Q UI: **Configure MCP** â†’ select `vpoMac` â†’ add header Key: `Authorization`, Value: `Bearer vporag-P<7digits>`. Tokens matching `vporag-P<7digits>` are **auto-registered on first use** â€” no admin action required. The server derives the display name from the token, persists it to `mcp_server/auth_tokens.json`, and logs a `user_registered` event. Requests without a valid token receive a **401 Unauthorized** (`REQUIRE_AUTH = True` â€” enforced).

## Learn Tool (Persistent KB)

`mcp_server/tools/learn_engine.py` -- abstract `LearnEngine` base class. Pure functions: `sha8`, `normalize`, `gate1_quality`, `nlp_enrich`, `build_chunk`. `process()` is the unified pipeline. `_scan()` does 3-pass dedup:
1. Exact content hash match -> reject duplicate
2. Semantic scan of learned file -- same-ticket: reject if >=0.92 (no tag gate needed); cross-ticket: reject if >=0.92 AND >=2 shared domain tags confirmed
3. Semantic scan of static KB -- reject if >=0.92 AND >=2 shared domain tags confirmed; hard ceiling >=0.98 always rejects regardless of tags

No merge window -- below 0.92 is always a new chunk. `_persist()` takes no `is_merge` parameter.

`mcp_server/tools/learn.py` -- `McpLearnEngine(LearnEngine)`: server paths from `config.JSON_KB_DIR`, git commit per write, `log_event()` for access log. Registered in `server.py` as `mcp.tool(name="learn")(learn_tool.run)`.

`mcp_server/tools/learn_local.py` -- `LocalLearnEngine(LearnEngine)`: local repo paths, no git, `source="local"` marker. CLI via argparse.

`mcp_server/scripts/learn_sync_batch.py` -- server-side batch runner. Reads JSONL of chunks, runs each through `LocalLearnEngine.process()` as `vporag`, prints JSON results array to stdout. Used by `Sync-LearnedChunks.ps1`.

**Learned chunk schema** (extends base chunk schema):
```python
{
    "id":           "learned::<ticket_key>::<sha8(text)>",
    "text":         "[What was discovered]: ...\n[Evidence]: ...\n[Context]: ...\n[Ticket]: DPS-XXXX",
    "text_raw":     text,
    "element_type": "learned",
    "metadata": {
        "doc_id":     "chunks.learned.jsonl",
        "ticket_key": "DPS-XXXX",
        "user_id":    "P3315113",
        "session_ts": "2025-...",
        "title":      "Short title",
        "source":     "local"   # omitted for MCP-originated; "synced" after push
    },
    "tags": [...]
}
```

**Similarity thresholds:**
- >=0.98 = hard duplicate -> always reject (lexical ceiling, no tag gate)
- >=0.92 = duplicate -> reject if tag overlap confirmed (>=2 shared domain tags) for cross-ticket/static KB; always reject for same-ticket
- <0.92 = new chunk -> always saved (no merge window)

**Server git repo:** Initialised at `/srv/vpo_rag/JSON/detail/` tracking only `chunks.learned.jsonl`. Branch is `master`. Commit created per `learn` call. No GitLab remote yet.

**Nightly cron** (`mcp_server/scripts/nightly_build.sh`): runs `build_index.py` at 3am MT as `vporag`. Cron installed via `crontab -u vporag`.

**Manual builds** (`mcp_server/scripts/run_build.sh`): use `run_build.sh` for manual execution. `--user=P<7digits>` is **required** -- the script exits with an error if omitted. Supports `-f`/`--full` flag to delete `processing_state.json` and force a full rebuild. Default (no flag) is incremental. Detects full rebuild automatically if state file is absent at start.

**Build event logging**: all three trigger paths (MCP tool, `run_build.sh`, `nightly_build.sh`) write a `build_index` event to `mcp_access.log` on completion. Fields: `trigger` (mcp/manual/cron), `force_full` (bool), `exit_code`, `duration_ms`, `files_processed`, `chunks_by_category` (dict of category -> chunk count). Visible in dashboard Event Log tab with expand button for full detail. Note: `run_build.sh` uses a heredoc temp file for the Python log write -- do NOT use `-c` inline with f-strings as bash expands curly braces before Python sees them.

**Search integration:** Phase 3.5 in `search_kb.py` and `Search-DomainAware.ps1` loads `chunks.learned.jsonl` independently. Caps: Standard=15, Deep=30, Exhaustive=60. `MatchType="Learned"`, phase bonus=8. Skipped in Quick mode.

**Pagination:** `search_kb` returns results in pages of 20 chunks each (~60-75K chars per page). Pages 2+ served from server-side LRU cache (50 entries). Response fields: `page`, `page_size`, `total_pages`, `max_pages`, `has_more`, `total`. Recommended page counts: Quick=1, Standard=2, Deep=3, Exhaustive=4.

**Sync workflow:**
```
powershell -ExecutionPolicy Bypass -File Setup\Sync-LearnedChunks.ps1 -Push
```
`Sync-LearnedChunks.ps1` identifies `source=local` chunks, SCPs `learn_sync_batch.py` + JSONL to `/tmp/`, runs as `vporag` via sudo, marks `source=synced` for ok outcomes.

