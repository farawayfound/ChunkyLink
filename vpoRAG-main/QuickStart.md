# Quick Start

Get vpoRAG running in ~15 minutes. For full details see [Documentation/Setup.md](Documentation/Setup.md), [Documentation/BuildIndex.md](Documentation/BuildIndex.md), and [Documentation/Inference.md](Documentation/Inference.md).

## 1. Install

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_md
python Setup/Local/check_deps.py
```

OCR and Jira SQL are optional — see [Setup.md](Documentation/Setup.md) for those steps.

## 2. Configure

```bash
cp indexers/config.example.py indexers/config.py
cp Searches/config.example.ps1 Searches/config.ps1
```

Set the required paths in `indexers/config.py`:
```python
SRC_DIR = r"C:\path\to\documents"
OUT_DIR = r"C:\path\to\JSON"
```

Set the matching output path in `Searches/config.ps1`:
```powershell
$JSON_KB_DIR = "C:\path\to\JSON"  # Must match OUT_DIR above
```

All other settings have working defaults. See [Setup.md](Documentation/Setup.md) and [Inference.md](Documentation/Inference.md) for the full config reference.

## 3. Build Index

```bash
cd indexers
python build_index.py
```

Processes all documents, applies hybrid NLP tagging (auto-tags + 80+ VPO domain `CONTENT_TAGS` always enforced), builds cross-references, and writes category JSONL files. Re-run at any time — only new/modified files are processed.

**Full rebuild** (required after changes to `CONTENT_TAGS`, `TERM_ALIASES`, or `nlp_classifier.py`):
```bash
del JSON\state\processing_state.json
python build_index.py
```

On the MCP server, use `run_build.sh` — `--user` is required:
```bash
/srv/vpo_rag/mcp_server/scripts/run_build.sh --full --user=P<7digits>
```

## 4. Connect Amazon Q to the MCP Server

Amazon Q uses the MCP server at `192.168.1.29:8000` for KB and Jira searches. Configure it once in VS Code:

1. Open the Amazon Q chat panel → click the **+** (Add MCP Server)
2. Fill in:
   - **Name:** `vpoRAG`
   - **Scope:** `Global`
   - **Transport:** `http`
   - **URL:** `http://192.168.1.29:8000/mcp`
   - **Timeout:** `0`
3. Restart VS Code — `search_kb`, `search_jira`, and `build_index` will be available in every session

Verify the server is reachable:
```bash
python mcp_server/scripts/test_mcp.py
```

If the MCP server is unreachable, Amazon Q falls back to local PowerShell scripts automatically (requires `$SEARCH_MODE = "Local"` in `Searches/config.ps1`).

## 5. Use with Amazon Q

**Do not** use `@folder` to load JSON directly — files exceed context limits. Amazon Q reads `JSON/Agents.md` and calls `search_kb`/`search_jira` via MCP (or PowerShell fallback) to filter relevant chunks before analysis.

## 6. Web UI (optional)

Double-click `UI/RUN_UI.bat` → open http://localhost:5000 for config editing and index building with live log streaming.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| spaCy model not found | `python -m spacy download en_core_web_md` |
| Tesseract errors | Set `ENABLE_OCR = False` in config.py |
| No files processed | Check `SRC_DIR` in config.py |
| Slow processing | Ensure `ENABLE_CAMELOT = False` (default) |

See [Documentation/Troubleshooting.md](Documentation/Troubleshooting.md) for more.

---

## Further Reading

| Topic | Document |
|-------|----------|
| Full install, config, OCR, Jira SQL | [Documentation/Setup.md](Documentation/Setup.md) |
| Pipeline, output schema, NLP, cross-references | [Documentation/BuildIndex.md](Documentation/BuildIndex.md) |
| Search scripts, levels, PowerShell patterns | [Documentation/Inference.md](Documentation/Inference.md) |
| CSV processing and Jira integration | [Documentation/CSV-and-Jira.md](Documentation/CSV-and-Jira.md) |
| Optimization internals, advanced config | [Documentation/Advanced.md](Documentation/Advanced.md) |
| Common errors and fixes | [Documentation/Troubleshooting.md](Documentation/Troubleshooting.md) |
