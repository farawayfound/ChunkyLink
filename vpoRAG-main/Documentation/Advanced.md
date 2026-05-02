# Advanced Reference

## Optimization Implementation Details

### Parallel index building

Document processors run concurrently in `build_index.py` via `ThreadPoolExecutor(max_workers=PARALLEL_OCR_WORKERS)`. Each file is dispatched to a worker; results are collected and written after all workers complete. Cross-reference enrichment is similarly parallelized. The GIL is not a bottleneck here because most work is I/O-bound (file reads) or releases the GIL (spaCy, PyMuPDF).

### MCP search_kb chunk cache

`search_kb.py` maintains a module-level `_CHUNK_CACHE` dict keyed by an MD5 of each category file's `mtime_ns + size`. On cache miss, all 33K chunks are loaded once and both `all_chunks` and `domain_chunks` (filtered subset) are stored. On cache hit, no I/O occurs. Cache is invalidated automatically after a rebuild because file mtimes change.

A background daemon thread (`chunk-warmup`) preloads the default domain cache at server startup so the first tool call is never cold.

### MCP search_kb phase optimizations

- **`_sl` field** — built at load time as `(text + search_text[:500]).lower()`. All phase filters use `str.in` on `_sl` rather than calling `.lower()` per chunk per search.
- **Phase 4 `_deep_hits`** — uses a `set` for O(1) tag/keyword lookup instead of iterating a list per chunk.
- **Phase 6 filter** — pre-filters on original search terms (typically 4–7) before applying the full expanded term set (20+) for scoring. Reduces the hot path from 22K×20 to 22K×4 string comparisons.
- **`_score_chunk`** — uses `str.count` instead of `re.findall` for term frequency.
- **`_slim` output** — strips `_sl`, `search_text`, `search_keywords`, `related_chunks`, `raw_markdown`, `text_raw`, `element_type` and truncates `text` to 2000 chars. Keeps per-chunk output ~2.4KB vs ~7–10KB raw.

### Accept-header shim (`server.py`)

`mcp` 1.26.0 requires `Accept: application/json, text/event-stream` on every POST. Amazon Q's MCP client sends `Accept: application/json` only on the initial handshake, causing a 406. `_AcceptShim` is a raw ASGI middleware (outermost layer, before Starlette) that injects `text/event-stream` into the Accept header on POST requests before the MCP library validates it.

### Deploy build guard (`vporag-deploy.sh`)

Before restarting `vporag-mcp`, the script checks `/tmp/vporag_build.pid`. If the PID exists and the process is alive, the restart is skipped and a warning is printed. Files are still deployed — only the restart is deferred. The guard is server-side so it applies regardless of how the deploy was triggered (`.bat`, `.ps1`, or direct SSH).

Doc objects are cached by chunk ID at module level in `utils/cross_reference.py` to avoid recomputing embeddings for every similarity comparison (~50–60% faster):

```python
_doc_cache = {}

def compute_similarity(chunk1, chunk2):
    id1, id2 = chunk1["id"], chunk2["id"]
    if id1 not in _doc_cache:
        _doc_cache[id1] = nlp(chunk1.get("text_raw", chunk1["text"])[:500])
    if id2 not in _doc_cache:
        _doc_cache[id2] = nlp(chunk2.get("text_raw", chunk2["text"])[:500])
    return _doc_cache[id1].similarity(_doc_cache[id2])
```

Text is truncated to 500 chars for performance. Cache is in-process only — not persisted across runs.

### Tag normalization

Implemented in `utils/nlp_classifier.py`:

```python
def _normalize_tag(tag: str) -> str:
    tag = tag.lower().strip()
    tag = re.sub(r'[\n\r]+', ' ', tag)      # Remove newlines
    tag = re.sub(r'\s+', '-', tag)           # Spaces to hyphens
    tag = re.sub(r'[^\w\-]', '', tag)        # Remove special chars
    tag = re.sub(r'\-{2,}', '-', tag)        # Collapse hyphens
    tag = tag.strip('-')
    return tag[:50]
```

Before: `"provisioning-(billing\ncodes-&-bocs"` → After: `"provisioning-billing-codes-bocs"`

### Chunk deduplication

Hash-based, scoped per document in `processors/pdf_processor.py`:

```python
seen_hashes = {}
for part in parts:
    if not should_deduplicate(part, seen_hashes, dedup_intensity):
        detail_records.append(chunk)
```

`should_deduplicate()` is implemented independently in both `text_processing.py` and `csv_processor.py` (same logic, no shared import to avoid circular deps).

### NLP category scoring

Weighted keyword scoring with category-specific multipliers. Minimum score of 3 required to avoid false positives:

```python
scores = {
    "queries":         _score_keywords(text_lower, _QUERY_KEYWORDS) * 4,
    "troubleshooting": _score_keywords(text_lower, _TROUBLESHOOT_KEYWORDS) * 3,
    "glossary":        _score_keywords(text_lower, _GLOSSARY_KEYWORDS) * 5,
    "sop":             imperative_verbs * 3 + numbered_steps * 5,
    ...
}
best_cat = max(scores, key=scores.get)
return best_cat if scores[best_cat] >= 3 else "general"
```

Structural boosts: pipe density for queries, colon-definition patterns for glossary (`^[A-Z][^:]{2,30}:\s+\w`), numbered steps for SOP.

---

## Symmetric vs Asymmetric Cross-References

The combined indexer (`build_index.py`) builds **symmetric** cross-references by default — both forward refs (new → existing) and backward refs (existing → new).

**Why it matters:** Without backward refs, an existing chunk about "Xumo troubleshooting" won't reference a newly added chunk about "Xumo error code 1234" even though they're semantically related.

**Performance trade-off:**

| Scenario | Symmetric combined | Two-stage | Asymmetric combined |
|----------|--------------------|-----------|---------------------|
| First build (1K) | ~25s | ~45s | ~25s |
| 10% incremental (1K) | ~30s | ~45s | ~7s |
| 10% incremental (10K) | ~8min | ~12min | ~2min |

Asymmetric is much faster for small incremental updates but produces incomplete cross-references. To disable symmetry (not recommended):

```python
ENABLE_SYMMETRIC_CROSS_REFS = False  # config.py — forward refs only
```

**When to use two-stage instead of combined:**
- Rebuilding cross-refs with different thresholds without reprocessing documents
- Corpus >50K chunks
- Debugging cross-reference issues in isolation

---

## OCR Output Format

OCR-extracted text is appended to the chunk with a marker so it's distinguishable from regular text:

```json
{
  "id": "document.pdf::ch01::p10-12::para::abc123",
  "text": "[Chapter 1]\nRegular text content...\n\n[OCR from images]\nText extracted from screenshot",
  "element_type": "paragraph"
}
```

Both regular text and OCR text are searchable via `search_text`. The marker allows filtering OCR-only content if needed.

---

## Markdown Indexer Architecture

The Markdown indexer (`scripts/build_index_md.py`) reuses all JSONindexers components via `sys.path` injection — it does not duplicate processors, NLP, or cross-reference logic:

```
MDindexers
  └── sys.path.insert → JSONindexers/
        ├── core/incremental_indexer.py
        ├── processors/*.py
        └── utils/*.py
```

The only MD-specific code is the output writer: `chunk_to_markdown()` and `write_chunks_by_category()` which produce `.md` files instead of `.jsonl`. The processing pipeline, chunk schema, and NLP enrichment are identical.

---

## Jira Integration — Stage 2 Roadmap

Stage 1 (direct SQL query via `jira_query.py`) is complete. A SQLite mirror (`Searches/jira_local.db`) was added as a fast offline alternative — synced from the MCP server's MySQL via `Searches/sync_local_db.py`. This partially addresses the local storage need but does not add cross-referencing between tickets and KB chunks.

Stage 2 adds indexing for explicit cross-referencing. Triggers for Stage 2:

- Resolution notes field added to `JIRA_VIDEO_DETAILS` → worth indexing as SOP chunks
- Need explicit pre-linked cross-references between tickets and KB chunks
- Query latency becomes a problem at scale

Stage 2 additions (not yet implemented):
- `jira_processor.py` — 3-chunk-per-ticket builder (symptom / resolution / query)
- `sync_jira.py` — incremental sync using `row_last_updated` as change detection
- Task Scheduler nightly job
- Cross-reference builder run against combined KB + Jira chunks

**Open questions before Stage 2:**

| Question | Why it matters |
|----------|----------------|
| Are comments/work logs in `JIRA_VIDEO_DETAILS` or a separate table? | May contain the most useful triage context — worth a JOIN |
| Is `row_last_updated` reliably updated on every change? | Required for incremental sync |
| Any data governance rules on storing ticket data locally? | Stage 2 writes ticket data to JSONL |

Stage 2 does not replace Stage 1 — direct query remains for on-demand lookup; indexing adds cross-referencing on top.

---

## Sync Scripts

### Sync-JSONIndex.ps1 — JSON KB sync from MCP server

`Setup/Sync-JSONIndex.ps1` syncs the 7 category JSONL files from the MCP server to the local `JSON/detail/` directory. Uses SSH + SCP with key auth.

```powershell
# Sync only if remote index is newer
powershell -Command "& 'Setup\Sync-JSONIndex.ps1'"

# Force sync regardless of timestamps
powershell -Command "& 'Setup\Sync-JSONIndex.ps1' -Force"
```

Reads from `Searches/config.ps1`: `$JSON_KB_DIR` (local target), `$JIRA_REMOTE_MYSQL_HOST` (SSH server), `$MCP_SSH_USER`, `$MCP_SSH_KEY`. Remote path defaults to `/srv/vpo_rag/JSON/detail`.

Timestamp comparison uses `find ... -printf '%T@'` on the remote side. Each file is transferred individually via `scp`.

### sync_local_db.py — MySQL → SQLite sync

`Setup/sync_local_db.py` pulls the remote MySQL `jira_db` into the local SQLite mirror at `Searches/jira_local.db`.

```bash
python Setup/sync_local_db.py
```

Reads all connection settings from `Searches/config.ps1` via `_read_ps1_var()` — no hardcoded values. Syncs both `dpstriage` and `postrca` tables using an `Updated`-guard upsert: rows are inserted or replaced only if the remote `Updated` timestamp is newer than the local copy. `LOCAL_DB` is resolved as `Path(__file__).parent.parent / $JIRA_LOCAL_DB` to avoid path doubling.

---

All entry-point scripts support both package-style and direct execution via try/except:

```python
try:
    from indexers import config
    from indexers.core.incremental_indexer import IncrementalIndexer
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import config
    from core.incremental_indexer import IncrementalIndexer
```

Scripts not yet updated to dual-import (apply the same pattern if needed):
- `scripts/build_index_high_retention.py`
- `scripts/build_cross_references.py`
- `scripts/build_cross_references_incremental.py`
- `scripts/verify_optimizations.py`

---

## State File Schema

`JSON/state/processing_state.json` tracks per-file hashes for incremental processing:

```json
{
  "processed_files": {
    "C:\\docs\\file1.pdf": {
      "hash": "md5_of_size_and_mtime",
      "size": 12345,
      "mtime": 1704672000,
      "doc_ids": ["file1.pdf"],
      "file_name": "file1.pdf"
    }
  },
  "last_run": "2025-01-15T10:30:00",
  "version": "1.0"
}
```

Delete this file to force a full rebuild. The `IncrementalIndexer` class manages all state I/O.
