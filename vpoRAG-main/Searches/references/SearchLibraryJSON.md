# Search Library Reference

## ⚠️ MANDATORY
**NEVER** use `@folder`, `@file`, or fsRead on JSON files.  
**ALWAYS** use MCP tools (preferred) or executeBash → PowerShell fallback. See `JSON/Agents.md`.

---

## MCP Tools — Preferred

| Tool | Replaces | Notes |
|------|----------|-------|
| `search_kb` | `Search-DomainAware.ps1` | Server-side, all 8 phases, same scoring |
| `search_jira` | `Search-JiraTickets.ps1` | MySQL primary → CSV fallback |
| `build_index` | `python build_index.py` | Triggers remote rebuild |

Configure in VS Code: see `mcp_server/README.md`.

---

## PowerShell Scripts — Local Fallback
- `Search-DomainAware.ps1` — 4-phase Quick, 6-phase Standard, 8-phase Deep/Exhaustive
- `Search-JiraTickets.ps1` — Live Jira DB (top/count/oldest/custom modes)
- `Jira_Schema.md` — Status values, project keys, client/platform values
- `SPL_Reference.md` — Splunk query catalog
- `DQL_Reference.md` — OpenSearch/Kibana DQL syntax

---

## Domain Auto-Detection

| Pattern | Domain |
|---------|--------|
| error, issue, problem, fail, broken, stuck, crash, fix | troubleshooting |
| splunk, kibana, sql, query, index=, sourcetype= | queries |
| how to, steps, procedure, configure, setup, install | sop |
| documentation, manual, guide, feature, specification | manual |
| contact, team, escalate, who, phone, email | reference |
| what does, mean, definition, acronym, stands for | glossary |

**Default (no match):** troubleshooting + queries + sop

---

## Search Phases

**Quick (4):**
1. Initial — Match 2+ input terms in target domains
2. Term Discovery — Extract frequent tags/keywords/entities from Phase 1
3. Related Chunks — Follow cross-references (cross-domain)
4. Queries/SOPs — Cross-domain search in queries/troubleshooting/sop

**Standard (6):**
1. Initial — Match 2+ input terms in target domains
2. Term Discovery — Extract frequent tags/keywords/entities from Phase 1
3. Related Chunks — Follow cross-references (cross-domain)
4. Deep Dive — Search with discovered terms (3+ matches)
5. Topic Clusters — Chunks in same semantic clusters (cluster_size ≥ 3)
6. Queries/SOPs — Cross-domain search in queries/troubleshooting/sop

**Deep/Exhaustive adds:**
7. Fuzzy Matching — Prefix match on 5+ char terms (2+ matches)
8. Entity Expansion — Match by NLP entities (cross-domain)

**Scoring:** Term freq (0-40) + Tags (0-20) + Keywords (0-15) + Match bonus (Initial +25, Related +20, Query +15, DeepDive +10, other +5)

---

## Expansion Levels

| Level | Phases | Chunks | Time | Use Case |
|-------|--------|--------|------|----------|
| Quick | 4 | ~75 | 5-10s | Fast triage, high-confidence terms |
| Standard | 6 | ~185 | 15-30s | Fast triage (90%) |
| Deep | 8 | ~460 | 30-45s | Complex multi-system |
| Exhaustive | 8 | ~920 | 45-60s | Root cause / outages |

---

## Jira Modes

| Mode | Returns | Use When |
|------|---------|----------|
| `top` | Ranked TOP N (default 10 DPS / 5 RCA) | Default triage |
| `count` | Total matching count | "How many similar issues?" |
| `oldest` | Earliest matching ticket | "When was this first reported?" |
| `custom` | TOP N with custom window | More results or wider history |

**Params:** `-Limit N` · `-Since MONTHS` (0=all time) · `-TicketType both|dpstriage|postrca` · `-Status` · `-Client`

**Rule:** Never answer volume/trend/history questions from a TOP 10 result — use `count`, `oldest`, or `custom`.

---

## See Also
- `SearchLibraryMD.md` — Equivalent search functions for Markdown output format (`MD/detail/`)
