# Jira Schema Reference

## DPSTRIAGE Statuses

**`resolved` preset — returned by default (top/custom modes):**
`Closed` | `Pending Verification` | `Routed to POST-RCA`
*Contains troubleshooting steps, mitigations, resolution details*

**`active` preset — returned by default (top/custom modes):**
`Triage In Progress` | `Pending Mitigation` | `More Info Needed` | `Blocked`
*Contains ongoing investigation notes and current workarounds*

**Excluded by default in top/custom modes (low signal):**
`Cancelled` | `Backlog`
*Included automatically in count/oldest modes (true totals)*
*Use `-Status 'Cancelled'` or `-Status 'Backlog'` to include explicitly in top/custom*

## POSTRCA Statuses
Default excludes `Closed` only — focus is on ongoing known issues still being worked.

**`active` preset (all non-closed):** `Open` | `In Progress` | `Submitted` | `Ready For Work` | `Pending Fix` | `Pending Release` | `Deployment Pending` | `Deployment In Progress` | `Blocked` | `Approved`
**`resolved` preset:** `Closed`

## Status Presets (use with `-Status`)

| Preset | Expands To |
|--------|------------|
| `active` | DPSTRIAGE: Triage In Progress, Pending Mitigation, More Info Needed, Blocked |
| `resolved` | DPSTRIAGE: Closed, Pending Verification, Routed to POST-RCA |

## Linked Issue Project Keys
Use these to filter `linked_issues LIKE '%KEY-%'` or join via STRING_SPLIT.

**Video Platform Services:**
SVIPVS, SVLANTERN, SVLINEUP, SVMAC, SVMARS, SVMBO, SVMETA, SVNAV, SVODN, SVPT, SVSEARCH, SVSETTINGS, SVZODIAC, SVENTITLE, SVINT, SVAV

**Client Apps:**
STVCAST, STVDROID, STVFUJI, STVGUIDE, STVIOS, STVROKURSG, STVTVSDK, STVWEB, SGUIDE, XUMO

**Infrastructure/Platform:**
VIDEOSRE, VIDEOINS, IPVIDEOENG, VPE, VDO, VTD, VTEA, VCDT, NETVDE2, SPECNET, ISPCENTRAL, DSI

**Web:**
WEBPLAT, WEBBUY, WEBBILL, WEBPSP, WEBTET, WEB_VOX

**Cross-ticket:**
DPSTRIAGE, POSTRCA, SDSRCA, SETRCA, SEIPOD

**Other:**
ADVERA, AEARRIS, AEHMX, AEODNTCH, AETCH, ASO, AXWTRBL, BEST, CHCAPABLTY, CHPROJECT, CPROTECT, JIRAREQ, MER, MOBIT2, OAKRELIABL, PICA, PINXT, SMABA, XPLATID, ZCLIENT

## Client Field
Sparse — most rows are NULL. Use only when user specifies a platform/device.

**Devices:** `Roku` | `Samsung TV` | `Apple TV` | `Android` | `Android TV` | `iOS` | `Amazon Fire TV` | `Fire TV` | `Chromecast` | `Xbox` | `X-Class` | `Xumo-XiOne` | `Xumo-ES1`
**STB:** `Spectrum Guide` | `iGuide` | `Set Top Box`
**Web/OVP:** `Website` | `OVP` | `ODN` | `Passport`
**Other:** `No Client`

Values are comma-separated strings (e.g. `"Roku, Samsung TV, iOS"`). Filter with `Client LIKE '%Roku%'`.

## Useful Filter Patterns

```sql
-- Default exclusion in top/custom modes (applied automatically)
AND [Status] NOT IN ('Cancelled','Backlog')

-- Active investigations only (-Status 'active')
AND [Status] IN ('Triage In Progress','Pending Mitigation','More Info Needed','Blocked')

-- Resolved/escalated only (-Status 'resolved')
AND [Status] IN ('Closed','Pending Verification','Routed to POST-RCA')

-- Active POSTRCA only (-Status 'active' -TicketType postrca)
AND [Status] NOT IN ('Approved','Closed')

-- Linked to a specific team/service
AND linked_issues LIKE '%SVLINEUP-%'

-- Specific client/platform
AND [Client] LIKE '%Roku%'

-- Has any linked issues
AND linked_issues IS NOT NULL
```

## PowerShell Examples

```powershell
# Active investigations only
& 'Search-JiraTickets.ps1' -Terms 'pixelation','stva' -Status 'active'

# Resolved tickets only (rich troubleshooting detail)
& 'Search-JiraTickets.ps1' -Terms 'pixelation','stva' -Status 'resolved'

# True count including all statuses (count/oldest always include all)
& 'Search-JiraTickets.ps1' -Terms 'pixelation','stva' -Mode 'count' -Since 1
```

---

## Data Source Configuration

Controlled via `Searches/search_config.ps1`:

| Setting | Values | Default | Description |
|---------|--------|---------|-------------|
| `JIRA_PRIMARY_SOURCE` | `"sql"` \| `"csv"` | `"csv"` | Which source to query first |
| `JIRA_SEARCH_BOTH_SOURCES` | `True` \| `False` | `False` | Merge results from both sources (deduped by Key) |
| `JIRA_CSV_DIR` | relative path | `"structuredData\JiraCSVexport"` | CSV export directory (relative to repo root) |

When `JIRA_PRIMARY_SOURCE = "sql"`, CSV is still used as an automatic fallback if the DB is unreachable.

---

## CSV Fallback Export

When the live DB is unreachable, `Search-JiraTickets.ps1` automatically falls back to the most
recently modified CSV in `structuredData/JiraCSVexport/`. To refresh it:

**JQL for export:**
```
project IN ("Digital Platforms Support Triage", "Post RCA")
AND created >= startOfWeek(-2)
AND Status != Cancelled
AND NOT (project = "Digital Platforms Support Triage" AND Status = Backlog)
ORDER BY updated DESC
```
Export → CSV, max 1000 rows. Drop into `structuredData/JiraCSVexport/` — picked up automatically.

> **Tip:** Use `startOfMonth(-2)` for a broader historical window when investigating older issues.

**Fields searched in fallback:** Summary, Root Cause, Resolution/Mitigation Solution,
Resolution Category, Vertical, Responsible Team, Client.

**Status exclusions are identical to the live DB** — DPSTRIAGE excludes Cancelled + Backlog,
POSTRCA excludes Closed, count/oldest modes bypass exclusions for true totals.
