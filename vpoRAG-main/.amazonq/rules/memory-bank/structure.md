# vpoRAG — Project Structure

## Directory Layout

```
vpo_rag/
├── indexers/                            # Core indexing engine
│   ├── build_index.py                   # Main entry point — incremental + inline cross-refs
│   ├── build_index_with_cross_refs.py   # Alias for build_index.py (same logic)
│   ├── config.py                        # Active config (gitignored — copy from config.example.py)
│   ├── config.example.py                # Template with all options and inline docs
│   ├── config.server.py                 # Server-side config template (for MCP server deployment)
│   ├── core/
│   │   └── incremental_indexer.py       # Hash-based state tracking, append/remove records
│   ├── processors/                      # Format-specific document handlers
│   │   ├── pdf_processor.py             # PyMuPDF block extraction, hierarchy, chunking
│   │   ├── text_processor.py            # TXT, DOCX (heading-aware), PPTX (slide-aware)
│   │   ├── csv_processor.py             # Auto-detects Jira vs tabular, extracts tech codes
│   │   └── table_extractor.py           # pdfplumber + optional Camelot → markdown tables
│   ├── utils/                           # Shared utilities
│   │   ├── nlp_classifier.py            # spaCy classification, auto-tagging, entity extraction
│   │   ├── cross_reference.py           # Semantic linking, topic clusters, alias expansion
│   │   ├── text_processing.py           # Normalization, chunking, hierarchy, breadcrumbs
│   │   ├── topic_metadata.py            # Path-based topic tagging from DOC_PROFILES
│   │   ├── ocr_processor.py             # Parallel Tesseract OCR for PDF/DOCX/PPTX images
│   │   ├── quality_assurance.py         # Chunk quality filter, QA report generation
│   │   └── cpni_sanitizer.py            # CPNI redaction — emails, phones, account numbers, addresses, names
│   ├── scripts/                         # Alternative/specialized build scripts
│   │   ├── build_index_incremental.py   # Two-stage: index only (no cross-refs)
│   │   ├── build_cross_references.py    # Two-stage: cross-refs only (post-index)
│   │   ├── build_cross_references_incremental.py  # Cross-refs for new chunks only
│   │   ├── build_index_high_retention.py  # High-retention variant
│   │   ├── build_index_md.py            # Markdown output variant
│   │   └── verify_optimizations.py      # Performance verification tool
│   ├── tests/
│   │   ├── test_json_indexer.py         # Full integration test suite (8 tests)
│   │   ├── test_md_indexer.py           # Markdown indexer tests
│   │   ├── test_content.py              # Shared VPO test content fixtures
│   │   └── Agents.md                    # Test-specific Amazon Q instructions
│   ├── __init__.py
│   ├── Agents.md                        # Amazon Q instructions for indexer context
│   └── README.md
│
├── Searches/                            # Search infrastructure (Amazon Q runtime)
│   ├── Scripts/
│   │   ├── Search-DomainAware.ps1       # Multi-phase KB search (4–8 phases, 75–920 chunks)
│   │   └── Search-JiraTickets.ps1       # Jira search: SQLite primary, CSV/SQL fallback, merge
│   ├── Connectors/
│   │   └── jira_query.py                # Python Jira SQL engine (pyodbc + keyring)
│   ├── References/                      # Query catalogs and protocol docs
│   │   ├── SPL_Reference.md             # Splunk query catalog by domain
│   │   ├── Kibana_Reference.md          # VO Kibana query catalog
│   │   ├── DQL_Reference.md             # OpenSearch DQL catalog
│   │   ├── SearchLibraryJSON.md         # JSON search protocol documentation
│   │   ├── SearchLibraryMD.md           # Markdown search protocol documentation
│   │   └── Jira_Schema.md               # VIDPROD_MAIN schema, status values, field names
│   ├── config.ps1                       # PowerShell config: SEARCH_MODE, paths, search level, Jira source
│   ├── config.py                        # Jira SQL connection settings (server, DB, driver)
│   └── query_local_db.py                # SQLite query engine called by Search-JiraTickets.ps1
│
├── JSON/                                # Output directory (mostly gitignored)
│   ├── detail/
│   │   ├── chunks.troubleshooting.jsonl # Tracked in git
│   │   ├── chunks.queries.jsonl         # Tracked in git
│   │   ├── chunks.sop.jsonl             # Tracked in git
│   │   ├── chunks.manual.jsonl          # Tracked in git
│   │   ├── chunks.reference.jsonl       # Tracked in git
│   │   ├── chunks.glossary.jsonl        # Tracked in git
│   │   ├── chunks.general.jsonl         # Tracked in git
│   │   ├── chunks.learned.jsonl         # Tracked in git (server git repo at JSON/detail/)
│   │   └── chunks.jsonl                 # Unified (local only, gitignored)
│   ├── router/
│   │   ├── router.docs.jsonl            # Document-level routing (gitignored)
│   │   └── router.chapters.jsonl        # Chapter-level routing (gitignored)
│   ├── logs/                            # Build logs + mcp_access.log (gitignored)
│   ├── manifests/                       # run_manifest.json (gitignored)
│   ├── state/                           # processing_state.json (gitignored)
│   ├── Agents.md                        # Amazon Q search instructions (primary entry point)
│   └── README_SEARCH.md
│
├── UI/                                  # Web UIs
│   ├── Agents.md                        # Overview of both sub-UIs
│   ├── Indexer/                         # Local index builder control panel (port 5000)
│   │   ├── app.py                       # Flask + SocketIO server
│   │   ├── templates/index.html
│   │   ├── static/app.js, style.css
│   │   ├── requirements.txt             # flask, flask-socketio
│   │   ├── Agents.md
│   │   ├── RUN_UI.bat                   # Windows launcher
│   │   └── run.sh
│   └── MCPdashboard/                    # MCP server observability dashboard (port 5001)
│       ├── base/
│       │   ├── log_reader.py            # Abstract LogReader interface
│       │   └── app_factory.py           # create_app(reader) — all Flask routes
│       ├── local/
│       │   ├── log_reader.py            # SshLogReader — reads log via SSH (Windows)
│       │   └── run.py                   # Windows entry point → localhost:5001
│       ├── remote/
│       │   ├── log_reader.py            # LocalLogReader — reads log directly (server)
│       │   ├── run.py                   # Server entry point → 0.0.0.0:5001
│       │   └── vporag-dashboard.service # systemd unit (deployed to /etc/systemd/system/)
│       ├── templates/
│       │   ├── base.html                # Shared chrome: <head>, header, KPI bar, nav tabs, <script> tags
│       │   ├── index.html               # Extends base.html — assembles tabs via {% include %}
│       │   └── tabs/                    # One partial per tab (Jinja2 {% include %})
│       │       ├── overview.html        # Overview tab: daily chart, tool pie, level/source/duration bars
│       │       ├── events.html          # Event Log tab: filterable table with expand rows
│       │       ├── errors.html          # Errors tab: warnings + tool errors table
│       │       ├── jiradb.html          # Jira Database tab: ingest history, CSV file manager, ingest modal
│       │       ├── jsonindex.html       # JSON Index tab: category stats, build history, source docs, trigger
│       │       └── learned.html         # Learned KB tab: chunks table, edit/delete panels, history, rollback modal
│       ├── static/
│       │   ├── style.css                # All styles (unchanged)
│       │   ├── app.js                   # Entry point: shared utils (fmt, fmtBytes, showTab) + refreshAll()
│       │   └── modules/                 # One module per domain area — loaded before app.js
│       │       ├── pager.js             # makePager, _pagerRegistry, toolbar helpers
│       │       ├── overview.js          # loadStats, renderOverview, resetDateRange, _applyRange, _barList
│       │       ├── events.js            # loadEvents, renderEventPage, sort/filter, toggleEvDetail
│       │       ├── errors.js            # _errorPager, loadErrors
│       │       ├── jiradb.js            # _jiradbPager, loadJiraDb, uploadJiraCsv, _validateCsv
│       │       ├── jsonindex.js         # _buildPager, _srcPager, loadIndexTab, triggerBuild, uploadSourceFiles
│       │       └── learned.js           # loadLearned, _historyPager, edit/delete/rollback
│       ├── README.md                    # Architecture, access, and redeploy instructions
│       ├── requirements.txt             # flask only
│       └── RUN_DASHBOARD.bat            # Windows launcher → local/run.py
│
├── structuredData/
│   └── JiraCSVexport/                   # Jira CSV exports for offline ticket search
│
├── Setup/                               # Setup and maintenance scripts
│   ├── sync_local_db.py                 # Pull Jira MySQL (MCP server) → local SQLite mirror
│   ├── Sync-JSONIndex.ps1               # Sync JSON/detail category files from MCP server via SCP
│   ├── Sync-LearnedChunks.ps1           # Push local chunks.learned.jsonl to server via learn_sync_batch.py
│   ├── Sync_CSV_toMCP.ps1               # Push local Jira CSV exports to MCP server Samba share
│   ├── Deploy-ToMCP.ps1                 # Deploy files to MCP server + restart services
│   ├── Deploy-ToMCP.bat                 # cmd.exe launcher for Deploy-ToMCP.ps1
│   ├── Deploy-MCPServer.ps1             # Full server provisioning deploy script
│   ├── Run-OnMcp.ps1                    # Run commands on MCP server and capture stdout reliably
│   ├── Local/
│   │   ├── check_deps.py                # Dependency checker (reads requirements.txt)
│   │   ├── setup_local.py               # Local environment setup helper
│   │   └── jira_local.db                # Local SQLite mirror (gitignored — synced via sync_local_db.py)
│   ├── Remote/                          # Scripts for Linux MCP server
│   │   ├── bootstrap_server.py          # One-time server bootstrap
│   │   ├── write_service_file.py        # Generate systemd service + env file
│   │   ├── fix_env_file.py              # Rewrite /etc/vporag/mcp.env safely
│   │   ├── setup_deploy_sudo.py         # Configure sudoers for deploy user
│   │   ├── setup_mysql_creds.py         # Reset MySQL jira_user password
│   │   ├── test_jira_connection.py      # Validate MySQL jira_db connection
│   │   ├── vpomac-deploy.sudoers        # sudoers fragment for deploy permissions
│   │   └── vporag-deploy.sh             # Server-side deploy helper script
│   ├── Unimplemented/                   # PLACEHOLDER ONLY — not functional
│   │   ├── chat_rag.py
│   │   ├── create_collections.py
│   │   └── ingest_json.py
│   └── Agents.md
│
├── mcp_server/                          # MCP server (runs on Linux host 192.168.1.29)
│   ├── scripts/
│   │   ├── setup_remote_mysql_schema.sql  # Run once in MySQL Workbench to create jira_db + tables
│   │   ├── csv_watcher.py               # inotify watcher — auto-ingests dropped CSV exports
│   │   ├── ingest_jira_csv.py           # Upsert DPSTRIAGE CSV rows into MySQL
│   │   ├── ingest_postrca_csv.py        # Upsert POSTRCA CSV rows into MySQL
│   │   ├── run_build.sh                 # Trigger KB rebuild on server (--user required)
│   │   ├── nightly_build.sh             # Cron: run build_index.py nightly + git push (3am MT)
│   │   ├── init_learned_repo.sh         # One-time: git init JSON/detail/, track only chunks.learned.jsonl
│   │   ├── learn_sync_batch.py          # Server-side batch runner for Sync-LearnedChunks.ps1
│   │   └── vporag-csv-sync.service      # systemd unit for csv_watcher
│   ├── tests/
│   │   ├── test_mcp.py                  # MCP connectivity test
│   │   ├── test_mcp_search_quality.py   # Search quality regression tests
│   │   └── test_search_jira_nl.py       # NL query parser tests
│   ├── tools/
│   │   ├── build_index.py               # MCP tool: trigger index rebuild
│   │   ├── search_jira.py               # MCP tool: search Jira MySQL
│   │   ├── search_kb.py                 # MCP tool: search JSONL KB
│   │   ├── learn.py                     # MCP tool: save session-discovered knowledge (McpLearnEngine)
│   │   ├── learn_engine.py              # Abstract LearnEngine base class — shared pipeline for learn/learn_local
│   │   ├── learn_local.py               # CLI equivalent of learn.py for offline/Local mode (LocalLearnEngine)
│   │   └── __init__.py
│   ├── server.py                        # FastAPI + MCP endpoint (port 8000) + AccessLogMiddleware
│   ├── stdio_proxy.py                   # stdio transport proxy for local MCP testing
│   ├── logger.py                        # Structured JSONL access logging (TimedRotatingFileHandler, 30 days)
│   ├── auth_tokens.json                 # Auto-registered user tokens (gitignored — written at runtime)
│   ├── config.example.py                # Template — copy to config.py on server
│   ├── config.py                        # Active server config (gitignored)
│   ├── requirements.txt
│   ├── vporag-mcp.service               # systemd unit for MCP server
│   └── README.md                        # Client setup + tool reference
│
├── Ansible/                             # Ansible playbooks for server provisioning
│   ├── Local/                           # Local workstation setup playbook
│   └── MCP/                             # MCP server provisioning playbook
│
├── Documentation/                       # Detailed guides
│   └── Old_Rules/                       # Archived Amazon Q rule files
│
├── .amazonq/rules/                      # Amazon Q context rules (auto-loaded)
│   ├── memory-bank/                     # This memory bank
│   └── TriageAssistant.md               # Triage workflow rules
│
├── .env.example
├── .gitattributes
├── .gitignore
├── .gitlab-ci.yml
├── Agents.md
├── QuickStart.md
├── README.md
├── requirements.txt
└── Sync_All_fromMCP.ps1                 # Pull all artifacts from MCP server in one shot
```

## Architectural Patterns

### Two-Layer Output
- **Router layer** (`router/`): Document and chapter summaries for high-level routing decisions
- **Detail layer** (`detail/`): Chunked content split by NLP category for targeted search

### Dual Import Strategy
Every indexer module supports both package-level and direct execution via try/except:
```python
try:
    from indexers import config          # python -m indexers.build_index
except ImportError:
    sys.path.insert(0, ...)
    import config                        # cd indexers && python build_index.py
```

### Processing Pipeline (per file)
```
File → processor (build_for_*) → raw chunks
     → _enrich() / sanitize_cpni() → CPNI redaction
     → add_topic_metadata()    → path-based tags
     → enrich_record_with_nlp() → NLP category, entities, key_phrases
     → _promote_nlp_category() → NLP category as first tag
     → is_quality_chunk()      → filter low-quality
     → enrich_chunk_with_cross_refs() → search_keywords, search_text, related_chunks, cluster
     → write_chunks_by_category() → category JSONL files + unified
```

### Search Pipeline (Amazon Q runtime)
```
Amazon Q reads JSON/Agents.md
→ executeBash: Search-DomainAware.ps1 -Terms ... -Query ...
→ executeBash: Search-JiraTickets.ps1 -Terms ...
→ PowerShell filters 75–920 chunks locally
→ Returns scored JSON to Amazon Q
→ Amazon Q analyzes filtered results only
```

### State Management
`JSON/state/processing_state.json` tracks file hashes and timestamps per absolute path. Delete this file to force a full rebuild. The `IncrementalIndexer` class manages all state I/O.

### Git Strategy
Category JSONL files (`chunks.*.jsonl`) are tracked in git for sharing the KB. `chunks.learned.jsonl` is tracked in a separate git repo initialised at `JSON/detail/` on the server (commit per learn call). The unified `chunks.jsonl`, router files, logs, manifests, state, and `config.py` are gitignored.

### Learned KB
`chunks.learned.jsonl` stores session-discovered knowledge written by the `learn` MCP tool or `learn_local.py`. Chunks use `element_type="learned"` and carry a `source` marker: no field = MCP-originated, `source="local"` = pending sync, `source="synced"` = pushed to server. The `LearnEngine` pipeline applies quality gating, NLP enrichment, and 3-pass dedup (exact hash → same-ticket semantic reject at ≥0.92 → static KB duplicate reject at ≥0.92 with tag overlap gate; hard ceiling at ≥0.98) before writing. No merge window — below 0.92 is always a new chunk.
