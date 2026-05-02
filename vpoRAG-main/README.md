# vpoRAG — Developer Reference

vpoRAG converts enterprise documents (PDF, PPTX, DOCX, TXT, CSV) into structured JSONL knowledge bases consumed by Amazon Q Developer for RAG-like triage assistance — without vector databases or embeddings.

**For setup and usage:** see [QuickStart.md](QuickStart.md) and the [Documentation/](Documentation/) directory.

---

## Purpose and Context

The system serves VPO (Video Product Operations) triage engineers. Engineers describe issues in Amazon Q, which searches the indexed KB and live Jira tickets to generate hypotheses, diagnostic queries (Splunk SPL, VO Kibana, OpenSearch DQL), and recommended next steps.

It is not a general-purpose RAG system. It is optimized for a specific workflow: local PowerShell search → filtered chunk set → Amazon Q analysis. The absence of a vector database is intentional — the PowerShell search pipeline is fast enough at this scale and avoids infrastructure dependencies.

---

## Architecture

### Two subsystems

**Indexer** (`indexers/`) — run offline by engineers to build the KB from source documents. Produces JSONL files in `JSON/`.

**Search** (`Searches/`) — run at Amazon Q runtime via `executeBash`. Filters the KB to a relevant chunk set before Amazon Q analyzes it.

These are deliberately decoupled. The indexer has no knowledge of the search scripts, and the search scripts only read the JSONL output.

### Processing pipeline (per document)

```
File → processor (build_for_*) → raw chunks
     → _enrich() / sanitize_cpni() → CPNI redaction (emails, phones, account numbers, addresses, names)
     → add_topic_metadata()     → path-based tags
     → enrich_record_with_nlp() → NLP category, entities, key_phrases
     → _promote_nlp_category()  → NLP category as first tag
     → is_quality_chunk()       → filter low-quality chunks
     → enrich_chunk_with_cross_refs() → search_keywords, search_text, related_chunks, cluster
     → write_chunks_by_category() → category JSONL files + unified
```

### Search pipeline (Amazon Q runtime)

```
Amazon Q reads JSON/Agents.md
→ executeBash: Search-DomainAware.ps1 -Terms ... -Query ...
→ executeBash: Search-JiraTickets.ps1 -Terms ...
→ PowerShell filters 75–920 chunks locally
→ Returns scored JSON to Amazon Q
→ Amazon Q analyzes filtered results only
```

### Two-layer output

- **Router layer** (`JSON/router/`) — document and chapter summaries for high-level routing
- **Detail layer** (`JSON/detail/`) — chunked content split by NLP category for targeted search

Category JSONL files (`chunks.*.jsonl`) are tracked in git for KB sharing. The unified `chunks.jsonl`, router files, logs, and state are gitignored and compiled locally.

---

## Module Map

```
indexers/
├── build_index.py                   # Main entry point — incremental + inline cross-refs
├── config.example.py                # All config options with inline docs
├── config.server.py                 # Server-side config template (for MCP server deployment)
├── core/
│   └── incremental_indexer.py       # Hash-based state tracking, append/remove records
├── processors/
│   ├── pdf_processor.py             # PyMuPDF block extraction, hierarchy, chunking
│   ├── text_processor.py            # TXT, DOCX (heading-aware), PPTX (slide-aware)
│   ├── csv_processor.py             # Auto-detects Jira vs tabular, extracts tech codes
│   └── table_extractor.py           # pdfplumber + optional Camelot → markdown tables
├── utils/
│   ├── nlp_classifier.py            # spaCy classification, auto-tagging, entity extraction
│   ├── cross_reference.py           # Semantic linking, topic clusters, alias expansion
│   ├── text_processing.py           # Normalization, chunking, hierarchy, breadcrumbs
│   ├── topic_metadata.py            # Path-based topic tagging from DOC_PROFILES
│   ├── ocr_processor.py             # Parallel Tesseract OCR for PDF/DOCX/PPTX images
│   ├── quality_assurance.py         # Chunk quality filter, QA report generation
│   └── cpni_sanitizer.py            # CPNI redaction — emails, phones, account numbers, addresses, names
└── scripts/
    ├── build_index_incremental.py   # Two-stage: index only (no cross-refs)
    ├── build_cross_references.py    # Two-stage: cross-refs only (post-index)
    ├── build_index_md.py            # Markdown output variant
    └── verify_optimizations.py      # Sanity-check tag normalization, dedup, cross-refs

Searches/
├── Scripts/
│   ├── Search-DomainAware.ps1       # Multi-phase KB search (4–8 phases, 75–920 chunks)
│   └── Search-JiraTickets.ps1       # Jira search: SQLite primary, CSV/SQL fallback, merge
├── Connectors/
│   └── jira_query.py                # pyodbc SQL engine + keyring credentials
├── References/                      # Query catalogs (SPL, Kibana, DQL) and schema docs
├── config.example.ps1               # Template — copy to config.ps1
└── config.py                        # Jira SQL connection settings

mcp_server/
├── tools/
│   ├── search_kb.py                 # MCP tool: search JSONL KB
│   ├── search_jira.py               # MCP tool: search Jira MySQL
│   ├── build_index.py               # MCP tool: trigger index rebuild
│   ├── learn.py                     # MCP tool: save session-discovered knowledge (McpLearnEngine)
│   ├── learn_engine.py              # Abstract LearnEngine — shared pipeline (learn + learn_local)
│   └── learn_local.py               # CLI equivalent of learn.py for Local mode
├── scripts/
│   ├── learn_sync_batch.py          # Server-side batch runner for Sync-LearnedChunks.ps1
│   ├── run_build.sh                 # Manual KB rebuild (requires --user=P<7digits>)
│   ├── nightly_build.sh             # Cron: run build_index.py nightly (3am MT)
│   └── csv_watcher.py               # inotify watcher — auto-ingests dropped Jira CSV exports
├── tests/
│   ├── test_mcp.py                  # MCP connectivity test
│   ├── test_mcp_search_quality.py   # Search quality regression tests
│   └── test_search_jira_nl.py       # NL query parser tests
├── stdio_proxy.py                   # stdio transport proxy for local MCP testing
└── server.py                        # FastAPI + MCP endpoint (port 8000)

UI/MCPdashboard/
├── base/
│   ├── log_reader.py                # Abstract LogReader interface
│   └── app_factory.py               # create_app(reader) — all Flask routes
├── local/
│   ├── log_reader.py                # SshLogReader — reads log via SSH (Windows)
│   └── run.py                       # Windows entry point → localhost:5001
├── remote/
│   ├── log_reader.py                # LocalLogReader — reads log directly (server)
│   └── run.py                       # Server entry point → 0.0.0.0:5001
├── templates/
│   ├── base.html                    # Shared chrome: <head>, header, KPI bar, nav tabs, <script> tags
│   ├── index.html                   # Extends base — assembles tabs via {% include %}
│   └── tabs/                        # One partial per tab
│       ├── overview.html            # Daily chart, tool pie, level/source/duration bars, client table
│       ├── events.html              # Filterable event log table with expand rows
│       ├── errors.html              # Warnings + tool errors table
│       ├── jiradb.html              # Ingest history, CSV file manager, ingest modal
│       ├── jsonindex.html           # Category stats, build history, source docs, rebuild trigger
│       └── learned.html             # Chunks table, edit/delete panels, version history, rollback modal
└── static/
    ├── style.css                    # All styles (unchanged)
    ├── app.js                       # Entry point: shared utils (fmt, fmtBytes, showTab) + refreshAll()
    └── modules/                     # Domain JS modules — loaded before app.js
        ├── pager.js                 # makePager, _pagerRegistry, toolbar filter/search helpers
        ├── overview.js              # loadStats, renderOverview, resetDateRange, _applyRange, _barList
        ├── events.js                # loadEvents, renderEventPage, sort/filter, toggleEvDetail
        ├── errors.js                # _errorPager, loadErrors
        ├── jiradb.js                # _jiradbPager, loadJiraDb, uploadJiraCsv, _validateCsv
        ├── jsonindex.js             # _buildPager, _srcPager, loadIndexTab, triggerBuild, uploadSourceFiles
        └── learned.js               # loadLearned, _historyPager, edit/delete/rollback
```

---

## Key Design Decisions

**No vector database.** spaCy word vectors (`en_core_web_md`) provide semantic similarity for cross-reference linking at index time. At search time, PowerShell string matching against pre-computed `search_text` and `search_keywords` fields is fast enough for this scale (<10K chunks).

**Hybrid tagging.** `enrich_record_with_nlp()` runs two passes on every chunk regardless of `ENABLE_AUTO_TAGGING`: NLP auto-tags (acronyms, nouns, entities, verbs) followed by `CONTENT_TAGS` phrase matching which is always enforced on top. `CONTENT_TAGS` has 80+ VPO domain entries covering tools, STB command namespaces, hardware platforms, infrastructure components, client apps, and error code families. `TERM_ALIASES` has 55 synonym groups for search expansion. `MAX_TAGS_PER_CHUNK = 25`, cap applied after NLP category promotion. Full rebuild required after changes to either config.

**Category routing.** Chunks are written to 7 category-specific JSONL files based on NLP classification. This gives 2–15x faster search vs a unified file and lets Amazon Q target the relevant domain. Cross-references span all categories — a troubleshooting chunk can reference a queries chunk.

**Incremental processing.** State is tracked in `JSON/state/processing_state.json` via MD5 hashes of file size + mtime. Only changed files are reprocessed. Bidirectional cross-references require re-enriching existing chunks when new ones are added — this is the main cost of incremental updates.

**Dual import pattern.** Every module supports both `python -m indexers.build_index` (package-style) and `cd indexers && python build_index.py` (direct). Achieved via try/except on imports. Not all scripts in `scripts/` have been updated yet — see [Documentation/Advanced.md](Documentation/Advanced.md).

**Jira: live query, not indexed.** Stage 1 queries `VIDPROD_MAIN` directly at triage time (no local storage). Stage 2 (indexing ticket data for cross-referencing) is planned but not implemented. See [Documentation/CSV-and-Jira.md](Documentation/CSV-and-Jira.md) for the Stage 2 roadmap.

**CPNI sanitization.** All text passes through `utils/cpni_sanitizer.py` before being written to the KB — both during document indexing (via `_enrich()` in `build_index.py`) and during `learn` tool execution (via `LearnEngine.process()`). Redacted categories: email addresses, phone numbers, account numbers, passwords/credentials, street addresses, and customer names (spaCy NER). Query-aware mode preserves SPL/Kibana/DQL syntax while still redacting account numbers (UUID and hex trace IDs are protected from false-positive redaction).

**Persistent learned KB.** Session-discovered knowledge is saved to `chunks.learned.jsonl` via the `learn` MCP tool or `learn_local.py` CLI. The `LearnEngine` base class provides a shared pipeline: CPNI sanitization → quality gate → 3-pass dedup (exact hash → same-ticket semantic reject at ≥0.92 → cross-ticket/static KB duplicate reject at ≥0.92 with tag overlap gate + hard ceiling at ≥0.98) → NLP enrichment → persist. No merge window — below 0.92 is always a new chunk. Searched in Phase 3.5 of `Search-DomainAware.ps1`.

---

## MCP Server

The MCP server runs on a dedicated Linux host (`192.168.1.29`, Ubuntu 24.04) and exposes four tools to Amazon Q Developer via the Model Context Protocol:

| Tool | Function |
|------|----------|
| `search_kb` | Multi-phase JSONL KB search with domain detection and relevance scoring |
| `search_jira` | Live MySQL query against `jira_db` (DPSTRIAGE + POSTRCA tables) |
| `build_index` | Trigger incremental KB rebuild on the server |
| `learn` | Save session-discovered knowledge to `chunks.learned.jsonl` |

Tools are registered in `C:\Users\<you>\.aws\amazonq\agents\default.json`. Each engineer authenticates with a personal Bearer token (`vporag-P<7digits>`) — auto-registered on first use, no admin action required.

**Deployment:** all file changes go through `Setup/Deploy-ToMCP.bat` or `Setup/Deploy-ToMCP.ps1`. Never use raw `scp`/`ssh sudo` directly.

**Search mode:** `Searches/config.ps1` sets `$SEARCH_MODE = "MCP"` (use MCP tools natively) or `$SEARCH_MODE = "Local"` (use PowerShell scripts). MCP mode is preferred; Local is the fallback when the server is unreachable.

---

## Persistent Learned KB

Engineers can save triage discoveries directly to the KB during a session:

```
# MCP mode (preferred)
learn(text="[What was discovered]: ...\n[Evidence]: ...\n[Context]: ...\n[Ticket]: DPS-XXXX",
      ticket_key="DPS-XXXX", category="auto", title="Short title")

# Local mode / MCP unreachable
python mcp_server/tools/learn_local.py --text "..." --ticket_key DPS-XXXX --title "..."
```

Chunks are written to `JSON/detail/chunks.learned.jsonl` and searched in Phase 3.5 of `Search-DomainAware.ps1`. Local chunks (marked `source=local`) can be pushed to the server with `Setup/Sync-LearnedChunks.ps1 -Push`.

The `LearnEngine` pipeline applies before any chunk is written:
1. **CPNI sanitization** — redacts customer data
2. **Quality gate** — minimum 15 words, sufficient alpha ratio
3. **3-pass dedup** — exact hash → same-ticket semantic reject (≥0.92, no tag gate) → cross-ticket/static KB reject (≥0.92 with ≥2 shared domain tags; hard ceiling ≥0.98 regardless of tags)
4. **NLP enrichment** — category, tags, entities

---

## CPNI Sanitization

All text is sanitized before being written to the KB — both during document indexing and `learn` tool execution. Implemented in `indexers/utils/cpni_sanitizer.py`.

| CPNI type | Placeholder |
|-----------|-------------|
| Email addresses | `<EMAIL>` |
| Phone numbers | `<PHONE>` |
| Account numbers (8–16 digits) | `<ACCOUNT_NUMBER>` |
| Passwords / credentials / tokens | `<CREDENTIAL>` |
| Street addresses | `<ADDRESS>` |
| Customer names (spaCy NER) | `<CUSTOMER_NAME>` |

**Query-aware mode:** when text is detected as SPL/Kibana/DQL (via `index=`, `| stats`, `field.path:`, etc.), only email and bearer token redaction applies. Account numbers are still redacted in query context, but UUID trace IDs and hex request IDs are protected from false-positive matches.

**Integration points:**
- `indexers/build_index.py` — `_enrich()` sanitizes both `text` and `text_raw` for every chunk from every processor (PDF, DOCX, PPTX, TXT, CSV)
- `mcp_server/tools/learn_engine.py` — `LearnEngine.process()` sanitizes before Gate 1

---

## NLP Classification

7 categories detected by weighted keyword scoring in `utils/nlp_classifier.py`:

| Category | Primary signals |
|----------|----------------|
| `queries` | Code syntax, pipe characters, technical symbols |
| `troubleshooting` | Error verbs, problem-solving patterns |
| `sop` | Imperative verbs (×3), numbered steps (×5) |
| `manual` | Descriptive content, product mentions |
| `reference` | High entity density (contacts, orgs) |
| `glossary` | Colon-definition patterns |
| `general` | Fallback — score below threshold of 3 |

NLP category is always promoted to the first tag position after enrichment.

**Hybrid tagging:** every chunk receives two tag passes — NLP auto-tags (acronyms, nouns, entities, verbs) merged with `CONTENT_TAGS` phrase matches. `CONTENT_TAGS` is always enforced regardless of `ENABLE_AUTO_TAGGING`. Cap of 25 tags applied after category promotion.

---

## Cross-Reference System

Built in `utils/cross_reference.py` as a post-processing step over all chunks:

1. spaCy word vector similarity (≥0.65) identifies related chunks across documents
2. Tag overlap (≥3 shared tags) gates similarity computation (reduces comparisons by ~30%)
3. Topic clusters group chunks by shared tags — stored as `topic_cluster_id`
4. Domain synonyms auto-generated from corpus (top 20 tags, ≥0.75 similarity, max 3 per term)
5. Bidirectional: both new→existing and existing→new refs are written in one pass

spaCy doc objects are cached by chunk ID (`_doc_cache` dict) to avoid recomputation. Text truncated to 500 chars for similarity.

---

## Chunk ID Format

Deterministic, double-colon delimited:

```
doc.pdf::ch01::p10-12::para::abc123
         │      │       │     └── sha256[:8] of text
         │      │       └── element type
         │      └── page range
         └── chapter ID
```

SHA-8 is used throughout for collision-resistant IDs: `hashlib.sha256(s.encode()).hexdigest()[:8]`.

---

## Git Strategy

| Tracked | Gitignored |
|---------|-----------|
| `JSON/detail/chunks.*.jsonl` (category files) | `JSON/detail/chunks.jsonl` (unified) |
| `JSON/detail/chunks.learned.jsonl` (server git repo) | `Searches/config.ps1` (contains absolute path) |
| `Searches/config.example.ps1` | `indexers/config.py` (contains local paths) |
| `indexers/config.example.py` | `JSON/router/`, `JSON/logs/`, `JSON/state/`, `JSON/manifests/` |
| All source code | `mcp_server/config.py`, `mcp_server/auth_tokens.json` |

---

## What Is Not Implemented

- **`Setup/Unimplemented/`** — placeholder only. Contains stub files for a vector DB approach that was never built and is not planned.
- **Jira Stage 2 indexing** — `jira_processor.py`, `sync_jira.py`, nightly sync job. Blocked pending resolution notes field availability and data governance approval.
- **FAISS / approximate nearest neighbors** — relevant only if chunk count exceeds ~50K. Current scale doesn't warrant it.
- **Multi-language NLP** — `en_core_web_md` only. Different spaCy models would be needed for other languages.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pymupdf` | PDF text/block extraction |
| `pdfplumber` | PDF table extraction |
| `spacy` + `en_core_web_md` | NLP classification, tagging, word vectors, CPNI NER |
| `python-pptx`, `python-docx` | PPTX and DOCX extraction |
| `rapidfuzz` | Fuzzy deduplication |
| `pytesseract` | OCR wrapper (requires Tesseract binary) |
| `pyodbc` + `keyring` | Jira SQL connection + credential storage |
| `flask`, `flask-socketio` | Web UI (UI/ only) |
| `fastapi`, `mcp` | MCP server endpoint (mcp_server/ only) |

CI/CD: `.gitlab-ci.yml` present. Tests: `indexers/tests/` — run with `python tests/test_json_indexer.py`.

---

## Documentation Index

| Document | Audience / Content |
|----------|--------------------|
| [QuickStart.md](QuickStart.md) | New users — get running in 15 minutes |
| [Documentation/Setup.md](Documentation/Setup.md) | Full install, all config options, OCR, Jira SQL |
| [Documentation/BuildIndex.md](Documentation/BuildIndex.md) | Pipeline, output schema, NLP, cross-references |
| [Documentation/Inference.md](Documentation/Inference.md) | Search scripts, config, phases, PowerShell patterns |
| [Documentation/CSV-and-Jira.md](Documentation/CSV-and-Jira.md) | CSV processing, Jira SQL, Stage 2 roadmap |
| [Documentation/Advanced.md](Documentation/Advanced.md) | Optimization internals, implementation details |
| [Documentation/Tests.md](Documentation/Tests.md) | Test suite structure and how to extend |
| [Documentation/Troubleshooting.md](Documentation/Troubleshooting.md) | Common errors and fixes |
