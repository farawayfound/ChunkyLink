# Tests - Agent Context

## Run
```bash
cd indexers && pytest tests/
# or: python tests/test_index_builders.py  (exit 0=pass, 1=fail)
```

## Core Tests
- `test_multiple_categories_routing()` — 5 files → validates each routes to correct `chunks.{category}.jsonl` and unified `chunks.jsonl`
- `test_incremental_multiple_categories()` — validates new files append without data loss, original chunks preserved

## Key Assertions
- `nlp_cat == category` — chunk in correct category file
- `total_in_categories == len(unified_chunks)` — no data loss
- `len(second_unified) > len(first_unified)` — incremental appends correctly

## Test Fixtures
```python
TEST_TROUBLESHOOTING = "Error code STBH-1234... fix: restart device..."
TEST_QUERIES        = "index=aws-stva sourcetype=... | stats count..."
TEST_SOP            = "Step 1: Navigate... Step 2: Select..."
TEST_MANUAL         = "Product documentation... Features include..."
TEST_REFERENCE      = "Contact: Team... Email... Phone..."
```

## Common Failures
- `"Category count mismatch"` → check `write_chunks_by_category()`
- `"Category mismatch: file=X, chunk=Y"` → check NLP classification logic
- `"Incremental failed: X -> X"` → check `indexer.append_new_records()` and state tracking
