# JSON Output - Search Protocol

## ⚠️ MANDATORY
**NEVER** use `@folder`, `@file`, or fsRead on JSON files.  
**ALWAYS** search via MCP tools (preferred) or PowerShell fallback.  
**Why:** fsRead loads 75K+ tokens and gets truncated. MCP/PowerShell filters to ~20KB locally.

---

## MCP Search — Preferred (server-side, no local deps)

Use the **search_kb** and **search_jira** MCP tools directly. Amazon Q will call them automatically when the MCP server is configured in VS Code settings (see `mcp_server/README.md`).

```
search_kb(terms=["term1","term2"], query="full user query", level="Standard")
search_jira(terms=["term1","term2"])
```

**Levels:** Quick (~75 chunks) · Standard (~185) · Deep (~460) · Exhaustive (~920)

---

## PowerShell Fallback — when MCP server is unreachable

```powershell
# Standard — 6 phases, ~185 chunks (default)
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full query'"

# Deep — 8 phases, ~460 chunks
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full query' -Level 'Deep'"

# Exhaustive — 8 phases, ~920 chunks
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full query' -Level 'Exhaustive'"

# Jira — always run alongside KB search
powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms 'term1','term2'"
```

See `Searches/References/SearchLibraryJSON.md` for full protocol, Jira modes, and domain auto-detection.

---

## Structure
```
JSON/detail/
├── chunks.troubleshooting.jsonl
├── chunks.queries.jsonl
├── chunks.sop.jsonl
├── chunks.manual.jsonl
├── chunks.reference.jsonl
├── chunks.glossary.jsonl
├── chunks.general.jsonl
└── chunks.jsonl              # Unified (local only, git-ignored)
```

## Chunk Schema
```json
{
  "id": "doc.pdf::ch01::p10-12::para::abc123",
  "text": "[Chapter 1]\nContent...",
  "text_raw": "Content without breadcrumb",
  "tags": ["troubleshooting", "device"],
  "search_keywords": ["troubleshooting", "debug"],
  "search_text": "flattened searchable content",
  "metadata": {
    "nlp_category": "troubleshooting",
    "nlp_entities": {"ORG": ["Spectrum"]},
    "key_phrases": ["error code"]
  },
  "related_chunks": ["doc2.pdf::ch03::p15::para::def456"],
  "topic_cluster_id": "device+troubleshooting",
  "cluster_size": 23
}
```
