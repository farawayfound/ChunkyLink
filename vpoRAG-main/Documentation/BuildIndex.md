# Build Index

## Processing Pipeline

Each document passes through this pipeline:

```
File → processor (build_for_*) → raw chunks
     → add_topic_metadata()     → path-based tags
     → enrich_record_with_nlp() → NLP category, entities, key_phrases
     → _promote_nlp_category()  → NLP category as first tag
     → is_quality_chunk()       → filter low-quality
     → enrich_chunk_with_cross_refs() → search_keywords, search_text, related_chunks, cluster
     → write_chunks_by_category() → category JSONL files + unified
```

---

## Output Structure

### Category files (`JSON/detail/`)

Chunks are split by NLP-detected category for faster, targeted search:

| File | Content |
|------|---------|
| `chunks.troubleshooting.jsonl` | Problem-solving, error fixes |
| `chunks.queries.jsonl` | SQL/Splunk/technical queries |
| `chunks.sop.jsonl` | Step-by-step procedures |
| `chunks.manual.jsonl` | Product documentation |
| `chunks.reference.jsonl` | Contacts, specs, org info |
| `chunks.glossary.jsonl` | Term definitions |
| `chunks.general.jsonl` | Uncategorized content |
| `chunks.jsonl` | Unified (all categories, local only — gitignored) |

Category files are tracked in git. The unified file is compiled locally on each run.

### Router files (`JSON/router/`)

- `router.docs.jsonl` — document-level summaries
- `router.chapters.jsonl` — chapter-level summaries with breadcrumbs

### Chunk schema

```json
{
  "id": "doc.pdf::ch01::p10-12::para::abc123",
  "text": "[Chapter 1]\nContent with breadcrumb...",
  "text_raw": "Content without breadcrumb",
  "element_type": "paragraph",
  "metadata": {
    "doc_id": "doc.pdf",
    "chapter_id": "ch01",
    "page_start": 10,
    "page_end": 12,
    "nlp_category": "troubleshooting",
    "nlp_entities": {"ORG": ["Spectrum"], "PRODUCT": ["Xumo"]},
    "key_phrases": ["error code", "device model"]
  },
  "tags": ["troubleshooting", "device", "action-configure"],
  "search_keywords": ["troubleshooting", "debug", "fix"],
  "search_text": "flattened searchable content...",
  "related_chunks": ["doc2.pdf::ch03::p15::para::def456"],
  "topic_cluster_id": "device+troubleshooting",
  "cluster_size": 23
}
```

---

## NLP Features

### Auto-classification

Categorizes chunks into 7 categories using weighted keyword scoring with category-specific multipliers. Minimum threshold of 3 avoids false positives. Structural boosts: pipe density for queries, colon-definition patterns for glossary, numbered steps for SOP.

### Auto-tagging (hybrid mode)

`ENABLE_AUTO_TAGGING = True` runs both passes on every chunk:

1. **NLP auto-tags** — extracts acronyms, frequent nouns, org/product entities, dominant verbs (`action-*`)
2. **`CONTENT_TAGS` phrase matching** — always applied on top regardless of the flag; enforces 80+ domain-specific tags covering VPO tools (specnav, mototerm, mind-control-tool, tmc, scope, effie, splunk, kibana…), STB command namespaces (pwreg-commands, silentdiag, sgd-commands, dsgccproxy…), hardware platforms (worldbox, xumo, docsis, hydra…), infrastructure components (ams, csm, stitcher, spp, lrm, clms, ipvs, epgs…), client platforms (stva, stva-roku, stva-ios, cdvr, pltv…), and error code families (error-3802, error-rci, error-guide-unavailable, error-gvod…)

The two tag sets are merged, NLP category is promoted to position 0, then `MAX_TAGS_PER_CHUNK` cap is applied last so the category tag never displaces a domain tag.

Tags are normalized: special characters removed, spaces converted to hyphens, max 50 chars, cap 25 per chunk.

### Adding a new category

Edit `_determine_category_automatic()` in `indexers/utils/nlp_classifier.py`, add detection patterns, and re-run the indexer. The new category file is created automatically.

---

## Cross-References

Cross-references link related chunks across documents and categories. They are built as a post-processing step over all chunks.

### What gets added to each chunk

- `search_keywords` — expanded terms including auto-generated synonyms
- `search_text` — flattened content combining text, breadcrumb, tags, key_phrases, entities
- `related_chunks` — IDs of semantically similar chunks from other documents (≥0.7 similarity)
- `topic_cluster_id` — cluster identifier based on shared tags (3+ common)
- `cluster_size` — number of chunks in the same cluster

### Bidirectionality

When adding new chunks to an existing index, the combined indexer builds both forward refs (new → existing) and backward refs (existing → new), ensuring complete symmetrical relationships.

### Domain synonyms

If `TERM_ALIASES = {}` in config.py, synonyms are auto-generated from corpus analysis:
1. Analyze top 20 most frequent tags
2. Find co-occurring terms in the same chunks
3. Use spaCy similarity (>0.75) to identify synonyms
4. Build alias groups (max 3 synonyms per term)

To define manually:
```python
TERM_ALIASES = {
    "xumo": ["xumo", "scxi11bei", "streaming device"],
    "authentication": ["auth", "login", "credential"],
}
```

---

## Incremental Processing

State is tracked in `JSON/state/processing_state.json` using MD5 hashes of file size + mtime. Only new or modified files are processed on each run.

When a file changes:
1. Old records are removed from all category files
2. The updated file is processed
3. Cross-references are rebuilt bidirectionally
4. State is updated

Delete `processing_state.json` to force a full rebuild.

---

## Performance

| Chunks | First build | 10% incremental |
|--------|-------------|-----------------|
| 1,000  | ~15s        | ~20s            |
| 5,000  | ~1min       | ~1.5min         |
| 10,000 | ~3min       | ~5min           |

Combined indexer is 1.5–2x faster than the two-stage approach because it avoids I/O between stages and processes cross-references inline. Peak memory ~500MB (spaCy model + doc cache).

### Parallel processing

Document processors (PDF, DOCX, PPTX, TXT, CSV) run concurrently via `ThreadPoolExecutor` using `PARALLEL_OCR_WORKERS` as the thread count. Cross-reference enrichment is also parallelized. Controlled by `PARALLEL_OCR_WORKERS` in `config.py` (default: 4).

---

## Markdown Output (alternative)

```bash
cd indexers
python scripts/build_index_md.py
```

Output: `MD/detail/chunks.{category}.md` — use only for human documentation review or one-off analysis. The JSON format is the supported production format.
