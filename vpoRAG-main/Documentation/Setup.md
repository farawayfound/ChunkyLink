# Setup Guide

## 1. Install Dependencies

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_md
python Setup/Local/check_deps.py
```

**spaCy model** (`en_core_web_md`, ~40MB) is required for NLP classification, tagging, and cross-reference similarity.

### OCR (optional)

Extracts text from images embedded in PDFs, PPTX, and DOCX files.

**Windows:** Download from https://github.com/UB-Mannheim/tesseract/wiki, install to `C:\Program Files\Tesseract-OCR\`  
**macOS:** `brew install tesseract`  
**Linux:** `sudo apt-get install tesseract-ocr`

Disable if not needed: `ENABLE_OCR = False` in config.py

### Jira search (optional)

Three sources are supported — install only what you need:

**SQLite mirror (recommended, default):** No extra dependencies. Sync from the MCP server's MySQL:
```bash
pip install mysql-connector-python
python Setup/sync_local_db.py
```
Requires LAN access to the MCP server (`192.168.1.29`). Set `$JIRA_REMOTE_MYSQL_*` in `Searches/config.ps1` first.

**CSV exports:** No dependencies. Drop CSV files into `structuredData/JiraCSVexport/DPSTRIAGE/` and `POSTRCA/`. See [CSV-and-Jira.md](CSV-and-Jira.md).

**Direct SQL (intranet only):**
```bash
pip install pyodbc keyring
```
Requires ODBC Driver 17 for SQL Server and intranet access to `VM0PWVPTSPL000`. Store credentials once:
```bash
python Searches/Connectors/jira_query.py --store-credentials
```

---

## 2. Configure

**Indexer config:**
```bash
cp indexers/config.example.py indexers/config.py
```

Edit `indexers/config.py` — at minimum set:
```python
SRC_DIR = r"C:\path\to\documents"   # Source files (PDF, PPTX, DOCX, TXT, CSV)
OUT_DIR = r"C:\path\to\JSON"        # Output directory
```

**Search config:**
```bash
cp Searches/config.example.ps1 Searches/config.ps1
```

Edit `Searches/config.ps1` — set `$JSON_KB_DIR` to match `OUT_DIR`:
```powershell
$JSON_KB_DIR = "C:\path\to\JSON"  # Must match OUT_DIR in indexers/config.py
```

See [Inference.md](Inference.md) for all other search config options.

```python
# Required
SRC_DIR = r"C:\path\to\documents"   # Source files (PDF, PPTX, DOCX, TXT, CSV)
OUT_DIR = r"C:\path\to\JSON"        # Output directory

# Chunking
PARA_TARGET_TOKENS = 512            # Chunk size (~4 chars/token)
PARA_OVERLAP_TOKENS = 128           # Overlap between chunks
MIN_CHUNK_TOKENS = 16               # Minimum chunk size

# NLP
ENABLE_AUTO_CLASSIFICATION = True   # NLP categorization (7 categories)
ENABLE_AUTO_TAGGING = True          # NLP tag extraction
MAX_TAGS_PER_CHUNK = 10

# Cross-references
ENABLE_CROSS_REFERENCES = True      # Semantic chunk linking
MAX_RELATED_CHUNKS = 5
MIN_SIMILARITY_THRESHOLD = 0.7
TERM_ALIASES = {}                   # Empty = auto-generate from corpus

# OCR
ENABLE_OCR = True
PARALLEL_OCR_WORKERS = 4
TESSERACT_PATH = None               # None = auto-detect
                                    # Windows: r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Table extraction
ENABLE_CAMELOT = False              # Keep False — very slow, rarely needed

# Deduplication
DEDUPLICATION_INTENSITY = 1         # 0=off, 1=exact, 2-9=fuzzy (97%→76%)
```

### Manual classification fallback (when `ENABLE_AUTO_CLASSIFICATION = False`)

```python
DOC_PROFILES = {
    "queries":         ["query", "sql", "splunk"],
    "troubleshooting": ["troubleshoot", "debug", "error"],
    "sop":             ["procedure", "workflow", "steps"],
    "manual":          ["guide", "manual", "documentation"],
    "reference":       ["reference", "glossary", "contacts"],
}
```

### Manual tagging fallback (when `ENABLE_AUTO_TAGGING = False`)

```python
CONTENT_TAGS = {
    "xumo":           ["xumo", "streaming", "device"],
    "authentication": ["auth", "login", "credential"],
}
```

---

## 3. Build Index

```bash
cd indexers
python build_index.py
```

This single command processes all documents, applies NLP, builds cross-references, deduplicates, and writes category JSONL files. Only new/modified files are processed on subsequent runs.

**Full rebuild** (delete state first):
```bash
del JSON\state\processing_state.json
python build_index.py
```

**Two-stage alternative** (use when rebuilding cross-refs with different thresholds):
```bash
python scripts/build_index_incremental.py
python scripts/build_cross_references.py
```

Both execution styles work:
```bash
# From project root
python -m indexers.build_index

# From indexers directory
cd indexers && python build_index.py
```

---

## 4. Connect Amazon Q to the MCP Server

Amazon Q uses the MCP server at `192.168.1.29:8000` for KB and Jira searches. This replaces the local PowerShell scripts for all search operations.

### VS Code configuration (one-time per machine)

1. Open the Amazon Q chat panel → click **+** (Add MCP Server)
2. Fill in:
   - **Name:** `vpoRAG`
   - **Scope:** `Global`
   - **Transport:** `http`
   - **URL:** `http://192.168.1.29:8000/mcp`
   - **Timeout:** `0`
3. Restart VS Code

This writes to `%APPDATA%\Code\User\mcp.json`. Verify the file contains:
```json
{
    "mcpServers": {
        "vpoRAG": {
            "serverUrl": "http://192.168.1.29:8000/mcp"
        }
    }
}
```

### Verify connectivity
```bash
python mcp_server/scripts/test_mcp.py
```
Expected: `10 passed, 0 failed`

### Output cap
Amazon Q enforces a 100K character limit on MCP tool output. The server strips heavy fields (`search_text`, `search_keywords`, `related_chunks`, etc.) and caps results at `MCP_MAX_RESULTS = 5` (set in `mcp_server/config.py`). All search levels (Quick through Exhaustive) work — the level controls search quality, not result count.

### Fallback
If the MCP server is unreachable, set `$SEARCH_MODE = "Local"` in `Searches/config.ps1`. Amazon Q will use `Search-DomainAware.ps1` and `Search-JiraTickets.ps1` via `executeBash` instead.

---

## 5. Web UI (optional)

```bash
# Windows
RUN_UI.bat

# macOS/Linux
cd UI && pip install -r requirements.txt && python app.py
```

Open http://localhost:5000 — provides config editing, index building with live log streaming, and log viewer.

If port 5000 is in use, edit the last line of `UI/app.py`: `socketio.run(app, host='0.0.0.0', port=5001)`

---

## 5. Verify

```bash
python Setup/Local/check_deps.py
cd indexers && python scripts/verify_optimizations.py
```

Expected output from verify:
```
✅ Tag Normalization
✅ Deduplication
✅ Cross-References
✅ Metadata Reduction
```

Check logs: `JSON/logs/build_index_with_cross_refs.log`
