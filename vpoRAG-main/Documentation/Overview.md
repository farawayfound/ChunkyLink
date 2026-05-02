# vpoRAG — Overview

vpoRAG converts enterprise documents into a structured JSONL knowledge base for Amazon Q Developer triage assistance. No vector database — local PowerShell search filters relevant chunks before Amazon Q analyzes them.

---

## Core Subsystems

| Subsystem | Location | Purpose |
|-----------|----------|---------|
| Indexer | `indexers/` | Offline — builds KB from source documents |
| Search | `Searches/` | Runtime — filters KB chunks for Amazon Q |
| MCP Server | `mcp_server/` | Remote — exposes tools to Amazon Q via Model Context Protocol |
| Web UI | `UI/` | Local — index builder control panel + MCP observability dashboard |
| Setup | `Setup/` | Deploy, sync, and maintenance scripts |

---

## Indexer (`indexers/`)

**Entry point:** `build_index.py` — incremental, hash-based change detection (only reprocesses changed files).

**Document processors:**
- `pdf_processor.py` — PyMuPDF block extraction, hierarchy, chunking
- `text_processor.py` — TXT, DOCX (heading-aware), PPTX (slide-aware)
- `csv_processor.py` — auto-detects Jira vs tabular; extracts tech codes
- `table_extractor.py` — pdfplumber → markdown tables; optional Camelot

**Processing pipeline (per file):**
```
File → processor → raw chunks
     → CPNI sanitization (emails, phones, account numbers, addresses, names)
     → path-based topic tags
     → NLP enrichment (category, entities, key_phrases, auto-tags)
     → NLP category promoted to tag[0]
     → quality filter (min 10 words, alpha ratio)
     → cross-reference enrichment (search_keywords, search_text, related_chunks, cluster)
     → written to category JSONL files
```

**NLP classification** (`utils/nlp_classifier.py`) — 7 categories via weighted keyword scoring:
`queries` · `troubleshooting` · `sop` · `manual` · `reference` · `glossary` · `general`

**Hybrid tagging** — two passes per chunk regardless of `ENABLE_AUTO_TAGGING`:
1. NLP auto-tags (acronyms, nouns, entities, verbs)
2. `CONTENT_TAGS` phrase matching (80+ VPO domain entries) — always enforced

**Cross-references** (`utils/cross_reference.py`) — post-processing step:
- spaCy word vector similarity (≥0.65) links related chunks across documents
- Tag overlap gate (≥3 shared tags) reduces comparisons ~30%
- Topic clusters group chunks by shared tags (`topic_cluster_id`)
- Bidirectional: new→existing and existing→new refs written in one pass

**CPNI sanitization** (`utils/cpni_sanitizer.py`) — redacts emails, phones, account numbers, passwords, addresses, customer names (spaCy NER). Query-aware mode preserves SPL/Kibana/DQL syntax.

**Output:** 7 category JSONL files in `JSON/detail/` + unified `chunks.jsonl` + router summaries in `JSON/router/`.

---

## Search (`Searches/`)

**`Search-DomainAware.ps1`** — multi-phase KB search (4–8 phases, 75–920 chunks):

| Phase | Description |
|-------|-------------|
| 1 — Initial | Term match against `search_text` / `search_keywords` in domain-targeted category files |
| 2 — Related | Expand via `related_chunks` IDs from Phase 1 hits |
| 3 — DeepDive | Cluster-based expansion via `topic_cluster_id` |
| 3.5 — Learned | Search `chunks.learned.jsonl` independently (skipped in Quick mode) |
| 4 — Cluster | Broader cluster scoring |
| 5 — Query | Phase 6 KB chunk queries (SPL/DQL lifted from KB) |
| 6 — Fuzzy | Fuzzy fallback for low-match sessions |
| 7 — Entity | Entity-based expansion |

**Search levels:**
| Level | Phases | Chunks delivered |
|-------|--------|-----------------|
| Quick | 4 | 20 |
| Standard | 6 | 40 |
| Deep | 8 | 60 |
| Exhaustive | 8 | 80 |

**`Search-JiraTickets.ps1`** — searches DPSTRIAGE and POSTRCA tickets. Source priority: SQLite mirror → CSV export → live SQL. Results merged and deduplicated by `Key`.

**`Searches/References/`** — query catalogs:
- `SPL_Reference.md` — Splunk SPL catalog by domain (auth, lineup, DVR, DTC, TVE, streaming)
- `Kibana_Reference.md` — VO Kibana queries for STB/AMS health metrics
- `DQL_Reference.md` — OpenSearch DQL for Quantum client-side events
- `Jira_Schema.md` — VIDPROD_MAIN schema, status values, field names

---

## MCP Server (`mcp_server/`)

Runs on `192.168.1.29:8000` (Ubuntu 24.04). Exposes four tools to Amazon Q via Model Context Protocol:

| Tool | Function |
|------|----------|
| `search_kb` | Multi-phase JSONL KB search with domain detection, relevance scoring, pagination (20 chunks/page, server-side LRU cache for pages 2+) |
| `search_jira` | Live MySQL query against `jira_db` (DPSTRIAGE + POSTRCA tables) with NL query parsing |
| `build_index` | Trigger incremental KB rebuild on the server |
| `learn` | Save session-discovered knowledge to `chunks.learned.jsonl` |

**Authentication:** personal Bearer tokens (`vporag-P<7digits>`) — auto-registered on first use.

**Access logging:** structured JSONL to `JSON/logs/mcp_access.log` (daily rotation, 30 days).

**Nightly build:** `nightly_build.sh` runs `build_index.py` at 3am MT as `vporag`.

---

## Persistent Learned KB

Session discoveries saved to `JSON/detail/chunks.learned.jsonl` via `learn` MCP tool or `learn_local.py` CLI.

**LearnEngine pipeline** (shared by MCP and Local modes):
1. CPNI sanitization
2. Quality gate (≥15 words, sufficient alpha ratio)
3. 3-pass dedup: exact hash → same-ticket semantic reject (≥0.92) → cross-ticket/static KB reject (≥0.92 + ≥2 shared domain tags; hard ceiling ≥0.98 always rejects)
4. NLP enrichment (category, tags, entities)
5. Persist to JSONL; git commit per write (server)

**Sync:** `Setup/Sync-LearnedChunks.ps1 -Push` — pushes `source=local` chunks to server via `learn_sync_batch.py`; marks `source=synced` on success.

---

## Web UIs (`UI/`)

**Index Builder** (`UI/Indexer/`, port 5000) — Flask + SocketIO control panel: edit config, trigger builds, stream live log output.

**MCP Dashboard** (`UI/MCPdashboard/`, port 5001) — observability dashboard: live access log stream, event log with build detail, tool usage stats. Two deployment modes: local (reads log via SSH) and remote (reads log directly on server).

---

## Setup & Deployment (`Setup/`)

| Script | Purpose |
|--------|---------|
| `Deploy-ToMCP.bat` / `Deploy-ToMCP.ps1` | Deploy files to MCP server + restart both services |
| `Run-OnMcp.ps1` | Run remote commands and reliably capture stdout |
| `Sync-JSONIndex.ps1` | Pull category JSONL files from MCP server via SCP |
| `Sync-LearnedChunks.ps1` | Push learned chunks to server |
| `Sync_CSV_toMCP.ps1` | Push Jira CSV exports to server Samba share |
| `sync_local_db.py` | Pull Jira MySQL → local SQLite mirror |
| `Sync_All_fromMCP.ps1` | Pull all artifacts from MCP server in one shot |

---

## Query Systems

Three completely separate diagnostic systems — syntax does NOT transfer between them:

| System | Target | Syntax signature |
|--------|--------|-----------------|
| Splunk SPL | Microservice API logs (STVA, LRM, Effie, cDVR, TVE, auth) | `index=aws-*` · `\| stats` · `\| rex` |
| VO Kibana | STB/AMS health metrics (tune failures, EPG, reboots) | Plain text + field filters, no pipes |
| OpenSearch DQL | Quantum client-side events (STVA/OneApp/Roku playback) | `field.path: value AND field2: (v1 OR v2)` |

---

## Key Configuration

| File | Purpose |
|------|---------|
| `indexers/config.py` | Source/output paths, chunk sizes, NLP flags, `CONTENT_TAGS`, `TERM_ALIASES` |
| `Searches/config.ps1` | `$SEARCH_MODE` (MCP/Local), search level, Jira source |
| `mcp_server/config.py` | Server paths, MySQL connection, auth settings |
| `Setup/secrets.env` | SSH key, sudo password, MySQL credentials (gitignored) |

**Full rebuild required** after changes to `CONTENT_TAGS`, `TERM_ALIASES`, or `nlp_classifier.py`.

---

## What Is Not Implemented

- `Setup/Unimplemented/` — placeholder stubs for a vector DB approach; not functional
- Jira Stage 2 indexing (`jira_processor.py`, nightly sync) — pending data governance approval
- FAISS / approximate nearest neighbors — not needed at current scale (~22K chunks as of last build; relevant threshold is ~50K)
