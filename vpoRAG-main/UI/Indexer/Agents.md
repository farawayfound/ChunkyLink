# vpoRAG Control Panel - Agent Reference

## Purpose
Web UI for managing the vpoRAG knowledge base. **For triage, use Amazon Q with TriageAssistant.md — not this UI.**

## Start
```bash
cd UI/Indexer && python app.py  # http://localhost:5000
# or: UI/Indexer/RUN_UI.bat
```

## UI Standards
**All buttons MUST have descriptive tooltips (`title` attribute).**  
Format: `"Action type: What happens + any warnings for destructive actions"`  
Example: `title="Incremental build: Processes new/modified files with full bidirectional cross-references (A↔B)"`

## Features
- **Build Index** — Incremental build with bidirectional cross-references (A↔B)
- **Rebuild All** — Full rebuild (deletes state, reprocesses everything)
- **Index Only** — Fast incremental, no cross-references
- **Cross-Refs Only** — Incremental cross-refs (backward only: existing→new, NOT bidirectional)
- **Settings** — Edit `indexers/config.py` directly (changes take effect on next build)
- **Logs** — Last 500 lines, refresh on demand
- **Stats** — File/chunk counts + category breakdown, real-time via WebSocket

## Notes
- Runs on localhost:5000 (not network-exposed, no auth)
- Config editor has full write access to config.py
- Build time: 2-5 min for 10K chunks
