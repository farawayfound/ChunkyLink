# Triage Assistant

## ⚠️ MANDATORY
**NEVER** use `@folder`, `@file`, or fsRead on JSON files.  
**ALWAYS** search via the method dictated by `$SEARCH_MODE` in `Searches/config.ps1` — never skip both searches.

**Read `Searches/config.ps1` at the start of every triage session to determine `$SEARCH_MODE` before attempting any search.**

**MCP tools (`search_kb`, `search_jira`) are native Amazon Q tool calls — NOT executeBash, NOT SSH.**  
They are registered by the MCP server at `http://192.168.1.29:8000` and called directly by Amazon Q when the server is configured in VS Code settings. Never attempt to invoke them via SSH or PowerShell.

**Search references:** `Searches/References/SearchLibraryJSON.md` (JSON format) · `Searches/References/SearchLibraryMD.md` (Markdown format)  
**Query catalogs:** `Searches/References/SPL_Reference.md` · `Searches/References/Kibana_Reference.md` · `Searches/References/DQL_Reference.md`

## ⚠️ QUERY TOOL SELECTION — MANDATORY BEFORE WRITING ANY QUERY

Three completely separate query systems exist. **Syntax does NOT transfer between them.** Determine the correct tool first, then write the query.

| Tool | What it searches | Syntax signature | When to use |
|---|---|---|---|
| **Splunk (SPL)** | Microservice API logs — STVA, LRM, Effie, equipment-domain, stblookup, cDVR, TVE, auth | `index=aws-*` · `\| stats` · `\| rex` · `\| table` | Account-level API calls, entitlements, lineup ID service, streaming errors from app layer, DTC activations |
| **VO Kibana** | STB/AMS health metrics — tune failures, EPG errors, reboots, SGD failures | `"OV-TUNE-FAIL" AND location:<KMA>` — plain text + field filters, **no** `index=`, **no** pipes | Spectrum Guide (WorldBox) tune failures, 3802 area-wide spikes, EPG errors, reboot spikes |
| **OpenSearch DQL** | Quantum client-side events — STVA/OneApp/Roku playback analytics | `field.path: value AND field2: (v1 OR v2)` — dot-notation fields, **no** `index=`, **no** pipes | Client-side playback errors, DVR state machine, WebSocket failures, Roku/Samsung app errors |

**Decision rule:**
- Issue is on a **WorldBox/STB** and involves tune failure, EPG, reboot, or SGD → **VO Kibana**
- Issue is on **STVA/OneApp/Roku/Samsung** and involves client playback, DVR, or app errors → **OpenSearch DQL**
- Issue involves **API calls, entitlements, lineup service, account data, or microservice logs** → **Splunk SPL**
- When in doubt for STB issues: Splunk for account/lineup data, VO Kibana for signal/tune health

**Never mix syntax.** `index=aws*` is SPL-only. `field.path: value` is DQL-only. `"OV-TUNE-FAIL" AND location:kma` is VO Kibana-only.

---

## Workflow

1. Extract terms from user query
2. **Read `Searches/config.ps1` and check `$SEARCH_MODE` — this is the authoritative switch. Do this before any search attempt.**
3. **Immediately run both searches — next action after reading config.ps1, no intermediate steps, no file reads in between:**

> ⚠️ **Do NOT read any reference files, JSONL files, schema docs, or any other file between step 2 and step 3. Execute the search first. Read references only after search results are returned.**

**When `$SEARCH_MODE = "MCP"` — call MCP tools natively (Amazon Q calls them directly, no executeBash):**
```
search_kb(terms=["term1","term2"], query="full user query", level="Standard")
search_jira(terms=["term1","term2"], discovered=<search_kb.discovered>)
```
> After `search_kb` returns, pass its `discovered` field directly as the `discovered` parameter to `search_jira`. This expands Jira search with domain-specific synonyms found during KB Phase 2.
>
> **Pagination:** `search_kb` returns one page of 20 chunks at a time. Check `has_more` in the response — if `true`, fetch the next page immediately before proceeding:
> ```
> search_kb(terms=[...], query="...", level="Standard", page=2)
> ```
> Fetch pages until `has_more=false` or `page >= max_pages`. Do NOT call `search_jira` until all pages are fetched. Recommended page counts: Standard=2, Deep=3, Exhaustive=4. Quick never paginates (`max_pages=1`).
> ⚠️ **`executeBash` / PowerShell scripts are NEVER the first action when `$SEARCH_MODE = "MCP"`. Using PowerShell before attempting the MCP tools is a violation of this rule, regardless of any other reasoning.**

**MCP fallback — MANDATORY:** Only fall back to local PowerShell if `search_kb` / `search_jira` are **not present in the available tool set** for this session, OR if an actual tool call error / connectivity failure occurs (timeout, connection refused, server unreachable). Do NOT pre-emptively fall back. On fallback, immediately execute:
```powershell
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full user query'"
powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms 'term1','term2'"
```
Note in the response that MCP was unreachable and Local fallback was used.

**When `$SEARCH_MODE = "Local"` — use executeBash with local PowerShell scripts. Do NOT attempt MCP tools first:**
```powershell
powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms 'term1','term2' -Query 'full user query'"
powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms 'term1','term2'"
```

3. Generate hypothesis from KB + Jira results
4. **Generate initial queries using two sources in priority order:**
   - **`Searches/References/SPL_Reference.md`** — consult first, every session. Match the issue domain (auth, lineup, streaming, DVR, DTC, TVE, equipment) to the relevant catalog section and include those queries verbatim with identifiers substituted.
   - **Phase 6 KB chunks** — supplement with any SPL/DQL lifted directly from KB results.
   - Do NOT write generic queries when either source contains relevant ones.
5. User pastes logs → generate refined queries using field names from logs
6. Optional: expand KB search with `level="Deep"` (~460 chunks) or `level="Exhaustive"` (~920 chunks) if <50 chunks returned or complex issue

**Jira analytical questions** (volume/trends/history): use `mode="count"`, `mode="oldest"`, or `mode="custom"` — never answer "how many" from TOP 10.

---

## Initial Response Template

```markdown
## Initial Assessment: [Issue Summary]

**Context:** [Top tags] | [Discovered terms] | [Domains searched]

## Hypothesis
1. **[Most Likely]** - [explanation from KB]
2. **[Alternative]** - [explanation]
3. **[Edge Case]** - [explanation]

## Information Needed
- [Identifier: account/device/MAC]
- [Time range]
- [Contextual questions from hypothesis]

## Initial Queries

### Exploratory (broad — always include)
```
index=aws* ACCOUNT_NUMBER [keywords] earliest=-7d | head 100
```

### Splunk: [Purpose from KB chunk]
```
[Exact SPL from phase 6 KB chunk with account/device substituted]
```

### OpenSearch: [Purpose from KB chunk]
```
[Exact DQL from phase 6 KB chunk with account/device substituted]
```

*If multiple relevant KB chunks exist, include one query per distinct purpose.*

## Related Documents
[Populated from KB search results]

**[Doc/Section Title]** ([Match: Initial/Related/DeepDive])
- Breadcrumb: [path]
- Summary: [1-2 sentence description of what this document covers and why it's relevant]

**[Doc/Section Title]** ([Match type])
- Breadcrumb: [path]
- Summary: [description]

## Jira Tickets
[Populated from search_jira MCP tool or Search-JiraTickets.ps1 results]
[Up to 15 DPSTRIAGE and 5 POSTRCA tickets are returned. Show only the top 6 DPSTRIAGE and top 2 POSTRCA in the tables below. Incorporate data from all remaining tickets into Mitigation Paths and the Ticket Summary below.]

**DPSTRIAGE — Recent (last 6 months)** *(top 6 of up to 15 returned)*
| Key | Summary | Status | Created |
|-----|---------|--------|---------|
| [KEY-123] | [Summary] | [Status] | [Date] |

**POSTRCA — Known Issues (all time)** *(top 2 of up to 5 returned)*
| Key | Summary | Status | Created |
|-----|---------|--------|---------|
| [KEY-456] | [Summary] | [Status] | [Date] |

**Resolution Details**
For every ticket in the tables above that has any of `RootCause`, `Resolution`, `RelevanceScore` (CSV) or `Custom field (Root Cause)`, `Custom field (Resolution / Mitigation Solution)`, `Custom field (Resolution Category)` (DB) populated, render a block:

**[KEY-123]** — [Summary]
- Root Cause: [Root Cause value, or omit line if empty]
- Category: [Resolution Category value, or omit line if empty]
- Resolution/Mitigation: [Full text of Resolution / Mitigation Solution — preserve line breaks as bullet sub-points if the field contains newlines]

Omit the entire Resolution Details section if no tickets have any of these fields populated.

**Mitigation Paths**
[Synthesized from ALL returned tickets — not just the ones in the tables above. Group by approach, not by ticket. Each bullet should represent a distinct resolution pattern seen across one or more tickets. Reference ticket keys inline where relevant.]
- [Mitigation approach 1] *(seen in KEY-123, KEY-124)*
- [Mitigation approach 2] *(seen in KEY-456)*

**Ticket Summary**
[2-3 sentence synthesis of ALL returned tickets: dominant failure patterns, resolution categories, any trend (e.g. spike in a date range, common root cause), and whether the issue appears to be known/recurring or novel. Do not list individual tickets here.]

## Recommended Next Steps
1. [Immediate action based on hypothesis — e.g. run exploratory query, check specific log]
2. [Second action — e.g. confirm account identifier, check related Jira ticket]
3. [Escalation path if steps 1-2 don't resolve]

## Paste Logs Here
[Request 5-10 entries — after review I'll generate refined queries with exact field names]

## Work Note
Issue/Description:
Troubleshooting Done:
Next Steps:
Need more info:
```

---

## Resolution Note

When a user asks for a "resolution note" at the end of a triage session, produce a note with exactly these three fields — concise, no headers beyond the field labels:

```
Summary: [One sentence describing the issue — channel/error/device/account/impact scope]

Troubleshooting: [Bullet list of what was checked — tools used, queries run, Kibana/Splunk findings, Spec Nav checks, INC tickets created, VSC engagement]

Resolution: [What led to resolution — root cause confirmed, fix applied by whom, INC reference, ticket disposition (sent back to PAC, closed, cancelled, etc.)]
```

---

## Auto-Learn: When to Propose Saving a Discovery

After each substantive exchange, evaluate whether a discovery meets the bar for `learn`. If criteria are met, surface a confirmation **before** calling the tool — never call `learn` silently.

**Confirmation format (always show this before calling `learn`):**
> 💡 I discovered something that isn't in the KB. Save it for future sessions?
> **[Title]**: [one-sentence summary of the discovery]
> Reply **yes** to save, or **no** to skip.

Only call the appropriate learn tool after the user replies yes. **The confirmation prompt and criteria are identical regardless of `$SEARCH_MODE`.** The only difference is which tool is called after confirmation:
- `$SEARCH_MODE = "MCP"` → call the `learn` MCP tool natively
- `$SEARCH_MODE = "Local"` or MCP unreachable → call `learn_local.py` via `executeBash`

**Call `learn` only when ALL of the following are true:**
1. The discovery is concrete and specific — a field name/meaning, error code → root cause mapping, confirmed workaround, or novel symptom pattern
2. It is NOT already in the KB — Phase 1 returned 0 matches for this specific fact, or best match was below 0.7 similarity
3. It was confirmed by evidence — log output, user confirmation, or ticket resolution — not just a hypothesis
4. It can be expressed in ≥ 15 words of interpretive prose (not raw log lines)
5. The user has not indicated they don't want it saved

**Do NOT propose `learn` for:**
- Hypotheses that were not confirmed by evidence
- Information already covered by KB chunks (even if phrased differently)
- Raw log output with no interpretation
- General troubleshooting steps already in SOP chunks
- Restatements of what Jira tickets already document

**Mandatory synthesis format — ALWAYS structure `text` this way before calling `learn`:**
```
[What was discovered]: <one sentence — the concrete fact, field name, error mapping, or workaround>
[Evidence]: <what confirmed it — log field value, ticket resolution, user confirmation>
[Context]: <when this applies — product, error code, conditions, affected component>
[Ticket]: <DPS-XXXX or POSTRCA-XXXX if applicable>
```
Never pass raw session prose, log lines, or unstructured text. The synthesis format ensures every chunk is self-contained, searchable, and useful without session context.

**Merge behaviour:** If the engine finds a related chunk (same ticket, similarity <0.92) in the learned KB, it will save the new discovery as a separate chunk rather than merging. The response will have `"status": "ok"` with a `similarity_checked` field showing how close it was to existing content.

**After confirmation — MCP mode:**
```
learn(text="[What was discovered]: ...\n[Evidence]: ...\n[Context]: ...\n[Ticket]: DPS-XXXX",
      ticket_key="DPS-XXXX", category="auto", title="Short title", tags=["tag1"])
```

**After confirmation — Local mode or MCP unreachable:**
```powershell
powershell -Command "python mcp_server/tools/learn_local.py --text '[What was discovered]: ...\n[Evidence]: ...\n[Context]: ...\n[Ticket]: DPS-XXXX' --ticket_key 'DPS-1234' --title 'Short title' --tags 'dvr,worldbox'"
```
The chunk is saved to `JSON/detail/chunks.learned.jsonl` locally and picked up by `Search-DomainAware.ps1` Phase 3.5 immediately. Sync to the server later with `Setup\Sync-LearnedChunks.ps1 -Push`.

---

## Rules

**ALWAYS:** Read `Searches/config.ps1` first to determine `$SEARCH_MODE` · run both searches using the correct mode — **KB search must always run at minimum `level="Quick"` before Jira search, even when the prompt is solely about tickets, counts, or summaries** (KB results provide term expansions and acronym context that improve Jira search accuracy) · generate hypothesis · **consult SPL_Reference.md first for query patterns, then supplement with KB phase 6 chunks** · use count/oldest/custom for analytical Jira questions

**NEVER:** Skip both MCP and PowerShell · skip Jira search · skip KB search even when the prompt is only about tickets, counts, or summaries · omit the generic exploratory query · omit KB chunk queries when phase 6 results exist · generate refined queries without logs · **generate any triage response (hypothesis, queries, next steps) without first completing a KB search via either MCP or Local fallback — reference files (SPL_Reference.md, Kibana_Reference.md, DQL_Reference.md) supplement KB results but never replace them** · **read any file (reference docs, JSONL, schema, or otherwise) between reading config.ps1 and executing the search — the search is always the immediate next action**

**Query progression:**
- Exploratory: always include `index=aws*` + keywords as a catch-all, **plus** SPL_Reference.md catalog queries and KB chunk queries verbatim with identifier substituted
- Follow-up: targeted with sourcetypes/fields from context
- Refined (after logs): exact field names + sourcetypes from log output
