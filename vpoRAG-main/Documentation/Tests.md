# Tests

## Running Tests

```bash
cd indexers
python tests/test_json_indexer.py
python tests/test_md_indexer.py
```

Exit code 0 = all passed, 1 = failures.

## Test Files

| File | Tests |
|------|-------|
| `tests/test_json_indexer.py` | JSON indexer: output structure, NLP enrichment, category routing, cross-category relationships, search fields, CSV processing, incremental updates, router records |
| `tests/test_md_indexer.py` | Markdown indexer: same coverage + JSON/MD parity verification |
| `tests/test_content.py` | Shared VPO test content fixtures (queries, SOP, manual, troubleshooting, reference, CSV) |

## What Gets Validated

- Files created, chunks generated
- All required fields present (`id`, `metadata`, `tags`, `text`)
- NLP enrichment: categories, tags, entities extracted; NLP category is first tag
- Chunks routed to correct category files; counts consistent with unified file
- Cross-category relationships: shared tags across categories
- Incremental updates: new files append without overwriting
- CSV data processed with NLP enrichment
- Router records generated for documents

## Test Design

Tests use realistic VPO content (CEITEAM ticket creation, NetOps INC escalation, APEX3000 troubleshooting, etc.) rather than generic fixtures. This ensures NLP classification behaves as it would in production.

Assertions are intentionally flexible where NLP output varies:
- Category count: `≥2` not exact (NLP may group similar content)
- Tag matching: uses common VPO terms that appear across categories
- Chunk counts: `≥` not `>` (unified files rebuild, not append)

## Adding a Test

```python
def test_your_feature(self):
    print("TEST: Your feature...")
    self.setup()
    try:
        self.create_test_txt("test.txt", "content")
        self.run_indexer()
        chunks = self.load_chunks()
        assert len(chunks) > 0, "No chunks generated"
        print("  [PASS] Your feature works")
    finally:
        self.teardown()
```

Add to `run_all_tests()`:
```python
tests = [
    # ... existing tests
    tester.test_your_feature,
]
```

## CI/CD

```yaml
- name: Run Tests
  run: |
    cd indexers
    python tests/test_json_indexer.py
```
