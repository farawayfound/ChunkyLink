# Troubleshooting

## Installation

**spaCy model not found:**
```bash
python -m spacy download en_core_web_md
# If that fails:
python -m spacy download en_core_web_md --user
# If import error:
pip uninstall spacy && pip install spacy==3.7.2 && python -m spacy download en_core_web_md
```

**Tesseract not found:**
- Windows: set `TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"` in config.py
- macOS/Linux: `which tesseract` to verify install path
- Or disable: `ENABLE_OCR = False`

**Dependency errors:**
```bash
pip install -r requirements.txt
python check_deps.py
```

---

## Processing

**No files processed:** Check `SRC_DIR` in config.py points to a directory containing PDF, PPTX, DOCX, TXT, or CSV files.

**Slow processing:**
```python
ENABLE_CAMELOT = False          # Must be False (default)
ENABLE_OCR = False              # Disable temporarily
PARALLEL_OCR_WORKERS = 2        # Reduce if CPU overloaded
OCR_MIN_IMAGE_SIZE = (300, 300) # Skip more images
```

**Memory issues:** Close other applications, or split source documents into smaller batches. Peak usage is ~500MB.

**Poor tag quality:**
```bash
python scripts/verify_optimizations.py
```
If tags are still poor, ensure `ENABLE_AUTO_CLASSIFICATION = True` and `ENABLE_AUTO_TAGGING = True`, then rebuild.

**Duplicate chunks:** Run `verify_optimizations.py`. If duplicates persist, check for multiple source files with identical content.

---

## Output

**Empty JSON files:** Check `JSON/logs/build_index_with_cross_refs.log`. Verify source files have content and `MIN_CHUNK_TOKENS = 16` isn't filtering everything.

**Missing cross-references:** Ensure `ENABLE_CROSS_REFERENCES = True`. Lower `MIN_SIMILARITY_THRESHOLD` (e.g., 0.6) for more links. Verify spaCy model has vectors:
```bash
python -c "import spacy; nlp = spacy.load('en_core_web_md'); print(nlp.vocab.vectors.shape)"
```

---

## Amazon Q / Search

**MCP tools not available in session:** Restart VS Code with Developer: Reload Window (`Ctrl+Shift+P`). If tools still don't appear, verify `%APPDATA%\Code\User\mcp.json` contains `serverUrl: http://192.168.1.29:8000/mcp` and run `python mcp_server/scripts/test_mcp.py` to confirm the server is reachable.

**search_kb returns 0 results:** JSONL files may not exist on the server yet — trigger a build: `build_index(force_full=True)` via MCP or `ssh vpomac@192.168.1.29 sudo -u vporag /srv/vpo_rag/mcp_server/scripts/run_build.sh`.

**search_kb output exceeds 100K character limit:** The server enforces `MCP_MAX_RESULTS = 5` and strips heavy fields automatically. If this error recurs, verify the deployed `mcp_server/tools/search_kb.py` is current: `python mcp_server/scripts/test_mcp.py`.

**search_jira returns CSV warning:** MySQL on the MCP server is down or credentials are missing — CSV fallback is active. Check: `ssh vpomac@192.168.1.29 sudo systemctl status mysql`.

**MCP server unreachable:** Set `$SEARCH_MODE = "Local"` in `Searches/config.ps1` to fall back to PowerShell scripts. To restore MCP: `ssh vpomac@192.168.1.29 sudo systemctl restart vporag-mcp`.

**Search not working (Local mode):** Verify `JSON/Agents.md` exists — it contains the search instructions Amazon Q reads. Without it, Q cannot execute local searches.

**Context not loading:** Do NOT use `@folder` to load JSON directly. Amazon Q executes PowerShell searches automatically via `JSON/Agents.md`.

**Poor search results:** Ensure NLP and cross-references are enabled, then rebuild:
```bash
del JSON\state\processing_state.json
python build_index.py
```

**Token limit exceeded:** This should not occur with the local search workflow. If it does, verify `JSON/Agents.md` exists and Amazon Q is running PowerShell searches rather than loading JSON directly.

---

## OCR

**Poor accuracy:** Check image resolution. Try `OCR_LANGUAGES = 'eng+spa'` for mixed content. Complex backgrounds are not supported.

**OCR too slow:** Reduce `PARALLEL_OCR_WORKERS`, increase `OCR_MIN_IMAGE_SIZE`, or disable with `ENABLE_OCR = False`.

---

## CSV

**Encoding errors:** Handled automatically with UTF-8 error replacement. If issues persist, convert the CSV to UTF-8 before processing.

**Missing columns:** The processor adapts to any column structure — no configuration needed.

**Empty rows skipped:** Expected — rows with fewer than 10 characters are filtered automatically.

---

## Incremental Updates Slow

Expected when bidirectional cross-references are enabled — existing chunks must be re-enriched to point back to new chunks. For faster (incomplete) updates:
```python
ENABLE_CROSS_REFERENCES = False
```
Or use two-stage:
```bash
python scripts/build_index_incremental.py
python scripts/build_cross_references.py
```

---

## Common Error Messages

| Error | Fix |
|-------|-----|
| `No module named 'spacy'` | `pip install spacy==3.7.2` |
| `Can't find model 'en_core_web_md'` | `python -m spacy download en_core_web_md` |
| `TesseractNotFoundError` | Install Tesseract or set `ENABLE_OCR = False` |
| `FileNotFoundError` | Check `SRC_DIR` and `OUT_DIR` paths in config.py |
| `MemoryError` | Close other applications or process smaller batches |
| `Tool search_kb is not available` | MCP server unreachable or VS Code not reloaded after mcp.json change |
| `search_kb output exceeds maximum character limit` | Server not running latest search_kb.py — run `Setup\Deploy-MCPServer.ps1` |

---

## Known Limitations

- Optimized for English (different spaCy models needed for other languages)
- OCR requires Tesseract (or disable)
- Complex tables may not preserve perfectly
- Images are not described — OCR extracts text only
- Related chunks exclude same document (by design)
