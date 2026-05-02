# vpoRAG — Development Guidelines

## File Header Convention
Every Python module uses the UTF-8 encoding declaration followed by a one-line module docstring:
```python
# -*- coding: utf-8 -*-
"""
Module purpose — one line description
"""
```

## Import Organization
1. Standard library — comma-separated on one line when related: `import re, json, hashlib, datetime, logging, sys`
2. Third-party — wrapped in `try/except ImportError` with `raise SystemExit("pip install X")` for hard dependencies
3. Optional third-party — wrapped in `try/except` setting a `HAS_X = False` flag for graceful degradation
4. Local imports — always via the dual-path pattern (see below)

## Dual Import Pattern (every module that can run standalone)
```python
try:
    from indexers import config
    from indexers.utils.nlp_classifier import enrich_record_with_nlp
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import config
    from utils.nlp_classifier import enrich_record_with_nlp
```
This allows both `python -m indexers.build_index` and `cd indexers && python build_index.py`.

## Config Access Pattern
Always use `getattr(config, 'KEY', default)` for optional config values — never assume a key exists:
```python
dedup_intensity = getattr(config, 'DEDUPLICATION_INTENSITY', 1)
max_tags        = getattr(config, 'MAX_TAGS_PER_CHUNK', 25)
auto_classify   = getattr(config, 'ENABLE_AUTO_CLASSIFICATION', False)
```

## Naming Conventions
- **Functions**: `snake_case`, verb-first (`build_for_pdf`, `enrich_chunk_with_cross_refs`, `find_related_chunks`)
- **Private helpers**: leading underscore (`_build_top_query`, _score_keywords`, `_normalize_tag`, `_promote_nlp_category`)
- **Constants / config keys**: `UPPER_SNAKE_CASE`
- **Classes**: `PascalCase` (`IncrementalIndexer`, `TestJSONIndexer`)
- **Chunk IDs**: double-colon delimited, deterministic: `doc.pdf::ch01::p10-12::para::abc123`
- **Route IDs**: `filename::doc` or `filename::chNN`

## Error Handling
- Wrap per-file processing in `try/except Exception as ex` with `logging.exception(...)` — never let one bad file abort the whole run
- Use `raise SystemExit("message")` for unrecoverable dependency errors (missing packages, missing spaCy model)
- Graceful degradation for optional features: set module-level flag (`HAS_OCR = False`, `nlp = None`) and skip with a warning log

## Logging
Use Python's `logging` module throughout — never bare `print()` in indexer code:
```python
logging.info(f"Processing {len(files)} files...")
logging.warning(f"NLP enrichment failed: {e}")
logging.exception(f"PDF error {path.name}: {ex}")
```
Always add both a file handler and a console handler so output appears in terminal and log file simultaneously. Log file goes to `OUT_DIR/logs/`.

## Chunk Schema — Required Fields
```python
{
    "id":           f"{doc_name}::{ch_id}::p{pg0}-{pg1}::para::{sha8(text)}",
    "text":         f"[{breadcrumb}]\n{text}",   # With breadcrumb context prefix
    "text_raw":     text,                         # Without prefix — used for NLP/similarity
    "element_type": "paragraph",                  # "paragraph", "table", "glossary", "csv_row"
    "metadata": {
        "doc_id":     path.name,
        "chapter_id": ch_id,
        "page_start": int,
        "page_end":   int,
    },
    "tags":         [],
    "raw_markdown": None                          # Populated for tables only
}
```
After NLP enrichment, metadata also contains `nlp_category`, `nlp_entities`, `key_phrases`.
After cross-ref enrichment, chunk also contains `search_keywords`, `search_text`, `related_chunks`, `topic_cluster_id`, `cluster_size`.

## Hybrid Tagging (CONTENT_TAGS always enforced)

`enrich_record_with_nlp()` runs two passes on every chunk regardless of `ENABLE_AUTO_TAGGING`:
1. NLP auto-tags (acronyms, nouns, entities, action verbs) — skipped if `ENABLE_AUTO_TAGGING=False`
2. `CONTENT_TAGS` phrase matching — **always runs**, merges domain tags on top

Merge order: NLP tags → CONTENT_TAGS matches → NLP category promoted to position 0 → `MAX_TAGS_PER_CHUNK` cap (25) applied last.

The cap is applied **after** category promotion so the category tag is never displaced by a domain tag.

`CONTENT_TAGS` has 80+ VPO domain entries. `TERM_ALIASES` has 55 synonym groups. Both live in `config.py` and are the primary extension point for domain knowledge — no code changes needed to add new tags.

**Full rebuild required** after changes to `CONTENT_TAGS`, `TERM_ALIASES`, or `nlp_classifier.py` — incremental runs only retag changed files.

## NLP Category Promotion
After NLP enrichment, always promote `nlp_category` to the first tag position:
```python
def _promote_nlp_category(enriched: Dict) -> Dict:
    nlp_cat = enriched.get("metadata", {}).get("nlp_category")
    if nlp_cat:
        enriched["tags"] = [nlp_cat] + [t for t in enriched.get("tags", []) if t != nlp_cat]
    return enriched
```

## Hash Generation
Use `sha8()` (first 8 chars of SHA-256) for deterministic, collision-resistant IDs:
```python
def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:8]
```

## JSONL I/O Pattern
Always use `ensure_ascii=False` and explicit `utf-8` encoding. Skip empty lines on read:
```python
# Write
with open(file_path, 'w', encoding='utf-8') as f:
    for record in records:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

# Read
with open(file_path, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            record = json.loads(line)
```

## Deduplication Pattern
`should_deduplicate()` is implemented independently in both `text_processing.py` and `csv_processor.py` (same logic, no shared import to avoid circular deps). Always pass a `seen_hashes` dict scoped to the current document:
```python
seen_hashes = {}
for part in parts:
    if not should_deduplicate(part, seen_hashes, dedup_intensity):
        detail_records.append(...)
```

## spaCy Usage
- Load model once at module level, not per-call
- Cache Doc objects by chunk ID to avoid recomputation during cross-reference building
- Truncate text to 500 chars for similarity computation (performance)
- Always check `nlp is not None` before using — model may fail to load

```python
# Module level
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    raise SystemExit("python -m spacy download en_core_web_md")

# Caching pattern
_doc_cache = {}
if chunk_id not in _doc_cache:
    _doc_cache[chunk_id] = nlp(text[:500])
```

## Category Scoring (NLP Classifier)
Use weighted keyword scoring with category-specific multipliers, not simple presence checks. Minimum threshold of 3 to avoid false positives:
```python
scores = {
    "queries":         _score_keywords(text_lower, _QUERY_KEYWORDS) * 4,
    "troubleshooting": _score_keywords(text_lower, _TROUBLESHOOT_KEYWORDS) * 3,
    "glossary":        _score_keywords(text_lower, _GLOSSARY_KEYWORDS) * 5,
    ...
}
best_cat = max(scores, key=scores.get)
return best_cat if scores[best_cat] >= 3 else "general"
```
Additional structural boosts: pipe density for queries, colon-definition patterns for glossary, numbered steps for sop.

**Queries penalty:** chunks without any SPL/DQL/Kibana syntax (`index=`, `| stats`, `| eval`, `| rex`, `field.word:`, `OV-TUNE-FAIL`) receive a `-8` score penalty before the threshold check. This prevents tool-access tables and SOP steps from being misclassified as `queries` just because they appear in a document tagged with the `queries` CONTENT_TAG. Takes effect on the next full rebuild.

## Processor Return Contract
All `build_for_*` functions return the same dict shape:
```python
return {"router": [router_records...], "detail": [detail_records...]}
```
PDF processor also returns `"pages": int`. CSV processor returns `"router": []` (no router records).

## Test Pattern
Tests use `tempfile.mkdtemp()` for isolation, mutate `config.SRC_DIR` / `config.OUT_DIR` in setup, and restore originals in teardown. Tests are class-based with explicit `setup()`/`teardown()` (not pytest fixtures). Run with `python tests/test_json_indexer.py`.

## PowerShell Search Conventions
- Scripts read `config.ps1` for `$JSON_KB_DIR`, `$JSON_SEARCH_LEVEL`, `$JSON_MAX_RESULTS`, `$JIRA_PRIMARY_SOURCE`
- Domain auto-detection from query text before selecting category files
- Always fall back to unified `chunks.jsonl` if category files don't exist
- Results include `MatchType` and `RelevanceScore` added as NoteProperties before output
- Phase labels in order: Initial → Related → DeepDive → Cluster → Query → Fuzzy → Entity → **Learned (Phase 3.5)**
- Phase 3.5 loads `chunks.learned.jsonl` independently; skipped in Quick mode; caps: Standard=15, Deep=30, Exhaustive=60; `MatchType="Learned"`
- Jira search: SQLite primary (default) with CSV and SQL fallback; `$JIRA_PRIMARY_SOURCE` controls order; results merged by `Key` deduplication
- `TAG_STOPLIST` — set of NLP noise tags excluded from Phase 2 discovery and Phase 4 scoring. Defined in `config.py` and loaded by `search_kb.py` and `Search-DomainAware.ps1`. Does not affect indexing. Add new noise tags here after running an audit.

## MCP Server Deployment

All file deployments to the MCP server go through `Setup/Deploy-ToMCP.bat` (cmd.exe) or `Setup/Deploy-ToMCP.ps1` (PowerShell). Credentials are loaded automatically from `Setup/secrets.env` (gitignored).

**Dashboard template/JS directories** — `templates/tabs/` and `static/modules/` must exist on the server before deploying files into them. If deploying to a fresh server, create them first via a single SSH call:
```
ssh -i C:\Users\P3315113\.ssh\vporag_key -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 vpomac@192.168.1.29 "echo vpomac007 | sudo -S sh -c 'mkdir -p /srv/vpo_rag/UI/MCPdashboard/templates/tabs /srv/vpo_rag/UI/MCPdashboard/static/modules && chown -R vporag:vporag /srv/vpo_rag/UI/MCPdashboard/templates/tabs /srv/vpo_rag/UI/MCPdashboard/static/modules' 2>&1"
```
Then deploy normally via `Deploy-ToMCP.ps1 -Files @(...) -RestartService`.

**Standard deploy + restart (from cmd.exe / terminal):**
```
Setup\Deploy-ToMCP.bat mcp_server/tools/search_jira.py Searches/Connectors/jira_query.py
```

**Sync learned chunks from local to server (engine-based dedup):**
```
powershell -ExecutionPolicy Bypass -File Setup\Sync-LearnedChunks.ps1 -Push
```
Dry-run (no push): omit `-Push`. Each chunk runs through `LocalLearnEngine.process()` on the server — dedup and quality gating applied. Only `ok` outcomes are marked `source=synced` locally.

**Restart service only:**
```
Setup\Deploy-ToMCP.bat
```

**Preferred invocation from `executeBash` (avoids cmd.exe argument parsing issues):**
```powershell
powershell -ExecutionPolicy Bypass -Command "& 'Setup\Deploy-ToMCP.ps1' -Files @('path/to/file.py') -RestartService"
```

**From within a PowerShell script (dot-source for helper functions):**
```powershell
. "$PSScriptRoot\Deploy-ToMCP.ps1"
Invoke-McpScp -LocalPath $localFile      # SCP to /tmp on server
Invoke-McpSsh -Command "sudo -S mv ..."  # Run sudo command (password injected automatically)
Deploy-Files -RelPaths @("mcp_server/tools/search_jira.py")  # SCP + mv + chown in one SSH call
Restart-McpService                        # Restart both services + verify active
```

**Implementation rules (do not deviate):**
- Paths passed to `scp`/`ssh` must use forward slashes — `Deploy-ToMCP.ps1` normalizes automatically
- Script-scope variables inside functions must use `$script:VAR` qualifier (PS 5.1 child-scope rule)
- sudo password is piped via stdin: `echo $pass | sudo -S <cmd>` — no TTY needed
- Always invoke via `.bat` or `powershell -Command "& '...'"` — never `powershell -File` (breaks array params)
- `Deploy-Files` runs `sudo sh -c 'mv $tmp $remote && chown vporag:vporag $remote'` — single SSH call per file
- `Restart-McpService` restarts **both** `vporag-mcp` and `vporag-dashboard` in a **single SSH call** — never restart them separately or in separate SSH connections (causes hangs)
- Deployed files are automatically `chown vporag:vporag` — files left owned by root are unreadable by the service
- After restart, allow 3 seconds before checking service status
- The MCP session token becomes invalid after a service restart — expect a `Session not found` error on the first MCP tool call; retry once
- If the deploy hangs, retry the identical command once — transient SSH hangs are normal; the consolidated single-call design minimises this risk

## Running Commands on the MCP Server and Capturing Output

**Critical:** The PowerShell `&` operator swallows SSH stdout entirely when used with complex pipelines. Never use `& ssh ...` in PowerShell and expect to read the output. Two reliable patterns exist:

**Pattern 1 — cmd.exe ssh (the ONLY reliable pattern from `executeBash`):**
```
ssh -i C:\Users\P3315113\.ssh\vporag_key -o BatchMode=yes -o ConnectTimeout=15 vpomac@192.168.1.29 "<command> 2>&1"
```
This is the only pattern that reliably returns stdout from `executeBash`. Always use this for diagnostic queries, MySQL commands, and any remote command where you need to read the output. Inject credentials inline: `MYSQL_PASS=Vp0rag_J1ra#2026! python script.py`

**Pattern 2 — SCP then ssh (for running local scripts remotely):**
```
scp -i C:\Users\P3315113\.ssh\vporag_key C:/Temp/script.py vpomac@192.168.1.29:/tmp/script.py
ssh -i C:\Users\P3315113\.ssh\vporag_key -o BatchMode=yes -o ConnectTimeout=15 vpomac@192.168.1.29 "MYSQL_PASS=Vp0rag_J1ra#2026! /srv/vpo_rag/venv/bin/python /tmp/script.py 2>&1"
```

**Pattern 3 — `Run-OnMcp.ps1` helpers (for PowerShell scripts, NOT `executeBash`):**
```powershell
. "Setup\Run-OnMcp.ps1"
$out = Invoke-OnMcp "ls /srv/vpo_rag"           # any remote command
$out = Invoke-PythonOnMcp "C:\Temp\script.py"   # SCP + run via venv, MYSQL_PASS injected
$out = Invoke-MySqlOnMcp "SELECT COUNT(*) FROM dpstriage"
Write-Output $out
```
`Run-OnMcp.ps1` uses the temp-file redirect pattern to bypass PowerShell stdout swallowing. It works when dot-sourced in a `.ps1` script but **does not work when called from `executeBash`** — use cmd.exe ssh there instead.

**MySQL credentials** are stored in `Setup/secrets.env` under `MYSQL_PASS`. Never hardcode the password. Always read it from secrets.env or inject via `MYSQL_PASS=... python script.py`.

**sudo password** is `MCP_SUDO_PASS` in `secrets.env`. The MySQL `jira_user` password is `MYSQL_PASS` in `secrets.env`. These are different credentials.

**`ADD COLUMN IF NOT EXISTS` is MariaDB syntax — not valid in MySQL 8.0.** Use plain `ALTER TABLE t ADD COLUMN col ...` after confirming the column doesn't exist with `SHOW COLUMNS FROM t`.

**The `Labels` field** (values: `3802`, `DVR`, `Guide_Unavailable`, etc.) is the primary error-code field in DPSTRIAGE Jira tickets. It is NOT included in the current CSV export template — it must be added to the Jira export configuration before it will appear in the DB. Until then, use `Resolution_Category` for breakdown queries.

## CPNI Sanitization

All text is sanitized via `utils/cpni_sanitizer.py` before being written to the KB. Two integration points:
- `indexers/build_index.py` — `_enrich()` calls `sanitize_cpni()` on both `text` and `text_raw` for every chunk from every processor
- `mcp_server/tools/learn_engine.py` — `LearnEngine.process()` calls it as the first step before Gate 1

The sanitizer is loaded via `importlib.util.spec_from_file_location` in `learn_engine.py` to bypass missing `__init__.py` on the server. Falls back to a no-op lambda with a warning if the file cannot be loaded.

**Query-aware mode:** `_is_query_text()` detects SPL/Kibana/DQL via `_QUERY_SIGNALS` regex. In query context, only email and bearer token redaction applies. Account numbers are still redacted in both modes, but UUID trace IDs (`8-4-4-4-12` hex) and pure hex strings are protected via a protect-then-restore stash pattern in `_redact_account_numbers()`.

## What NOT to Do
- Never use `@folder` or `fsRead` on JSON files — they exceed context limits (75K+ tokens)
- Never call `print()` in indexer modules — use `logging`
- Never hardcode paths — always use `Path(__file__).parent` relative resolution or config values
- Never load full `chunks.jsonl` when only category files are needed
- Never omit `ensure_ascii=False` on JSON writes (content contains special characters)
- Never mix Splunk SPL, VO Kibana, and OpenSearch DQL syntax — completely separate query systems
- Never use `rag_setup/` code — it is placeholder only and not functional
- Never skip the `is_quality_chunk()` filter — it removes garbled OCR and sub-10-word fragments
- Never use raw `scp` or `ssh sudo` commands to deploy to the MCP server — always use `Setup\Deploy-ToMCP.bat`
- Never use `powershell -File` to invoke `Deploy-ToMCP.ps1` — use `powershell -Command "& '...' "` or the `.bat` launcher
- Never commit `Setup/secrets.env` — it is gitignored and contains live server credentials
- Never use `& ssh ...` in PowerShell and expect to read stdout — use **cmd.exe ssh directly** from `executeBash`: `ssh -i C:\Users\P3315113\.ssh\vporag_key -o BatchMode=yes vpomac@192.168.1.29 "<cmd> 2>&1"`
- Never use `??` null-coalescing operator in `.ps1` files — PS 5.1 does not support it
- Never use Unicode typographic characters (em-dashes, curly quotes) in `.ps1` files — use ASCII equivalents
- Never use `.Count` under `Set-StrictMode` on a potentially single-item result without wrapping in `@()`
- Never use `ADD COLUMN IF NOT EXISTS` in MySQL 8.0 — it is MariaDB syntax and silently fails; use plain `ADD COLUMN` after checking with `SHOW COLUMNS`
