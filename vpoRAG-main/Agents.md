# vpoRAG - Agent Context

Converts documents (PDF, PPTX, DOCX, TXT, CSV) into structured JSON chunks with NLP enrichment and cross-references for Amazon Q.

## Structure
- `indexers/` — Core indexing pipeline (see `indexers/Agents.md`)
- `JSON/` — Output knowledge base (see `JSON/Agents.md` for search protocol)
- `Searches/` — PowerShell search scripts and reference docs
- `.amazonq/rules/` — TriageAssistant, SummaryCreator agent rules
- `UI/` — Optional Flask web UI (see `UI/Agents.md`)

## Build Index
```bash
cd indexers && python build_index.py
```

## Query Protocol
❌ Do NOT use `@folder` or fsRead on JSON files  
✅ ALWAYS use executeBash → PowerShell → filtered chunks → analyze

See `JSON/Agents.md` for search commands.
