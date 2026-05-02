# SpecNav API Integration Plan

## Overview

Integrate a Spectrum Navigator (SpecNav) API into the vpoRAG triage workflow so that Amazon Q
can automatically retrieve device and account state at the start of every triage session —
eliminating the manual lookup steps engineers currently perform in the SpecNav UI.

**Current pain points this solves:**

| Problem | Current | After |
|---|---|---|
| MAC → account bridge | Engineer manually looks up in SpecNav UI | API returns account + device in one call |
| Entitlement check | Manual Cloud Guide lookup per channel | API returns entitled true/false per TMS ID |
| Effie/ECP mismatch | Manual DYWTU diagnostic tool run | API returns mismatch flag + codes directly |
| Stream quality check | Manual SpecNav streaming logs review | API returns bitrate, IP, quality score |
| DVR status | Manual `dvreng`/`pwreg` commands via SpecNav | API returns `dvr_supported` flag |
| KMA/location gap | Not available without SpecNav UI access | API returns KMA → enables VO Kibana queries |
| STB WorldBox logs | Manual navigation in SpecNav | API returns recent log entries |

---

## Goals and Acceptance Criteria

### Goal 1 — Amazon Q can pre-populate all three query systems from a single API call

**Acceptance criteria:**
- Given a MAC address or account number, the API returns enough data to construct Splunk SPL,
  VO Kibana, and OpenSearch DQL queries without any additional manual lookups
- `account_number` is present → Splunk queries can be pre-populated
- `kma` is present → VO Kibana `location:<KMA>` filter can be pre-populated
- `device.model` and `firmware` are present → OpenSearch DQL device filters can be pre-populated

### Goal 2 — Entitlement checks are automated

**Acceptance criteria:**
- API accepts `mac` + `tms_id` (or channel number) and returns `entitled: true/false`
- `mini_guide_entitled` is returned separately (matches SpecNav Mini Guide dropdown)
- `authorizing_package` identifies which CLMS package is granting entitlement
- Effie/ECP mismatch is flagged with `effie_codes[]` and `ecp_codes[]` arrays

### Goal 3 — Stream quality data is available without manual log review

**Acceptance criteria:**
- API returns current stream IP, bitrate, and a quality indicator for the device
- OOH (Out of Home) detection: flag raised when stream IP does not belong to Spectrum network
- DVR feature status (`dvr_supported`, `dvr_feature_active`) returned alongside stream data

### Goal 4 — Integration is non-blocking for the existing triage workflow

**Acceptance criteria:**
- API call is made in parallel with KB and Jira searches (not sequentially)
- If the API is unavailable or returns an error, triage continues with manual SpecNav fallback
- Amazon Q's `TriageAssistant.md` is updated to include the API call in the initial search step

---

## Most Common SpecNav Checks (Basis for API Design)

Derived from KB (SEOPS, Vertical Playbooks) and Jira ticket analysis. These are the checks
engineers perform manually today that the API should automate:

| Check | Frequency | SpecNav Location |
|---|---|---|
| Channel Entitled True/False | Very High | Cloud Guide → Entitlements tab |
| Mini Guide Entitled True/False | Very High | Cloud Guide → Mini Guide dropdown |
| Org Code lookup | Very High | Account Information tab |
| Effie/ECP code mismatch (DYWTU) | High | DYWTU Diagnostic Tool |
| Effie Entitlements match billing | High | Effie Entitlements page |
| Stream quality / bitrate | High | Streaming logs |
| Stream IP (OOH detection) | High | Streaming logs |
| DVR feature status | Medium | STB WorldBox commands (`dvreng`, `pwreg`) |
| STB WorldBox logs | Medium | Spectrum > STB WorldBox/STB WorldBox Logs |
| BOC/BC billing code mapping | Medium | Entitlements tab → BOC/BC column |
| GLI-6001 / STBA-5205 error state | Medium | Emulator (launched from SpecNav) |

---

## Proposed API Response Shape

### Primary endpoint: `GET /device/{mac}`

Returns all data needed for a full triage session pre-population.

```json
{
  "device": {
    "mac": "AA:BB:CC:DD:EE:FF",
    "account_number": "8260...",
    "org_code": "YNNAUS",
    "boc": "LA025",
    "kma": "LAX",
    "model": "WorldBox-XG1v4",
    "firmware": "2.4.0p7s1",
    "mso": "TWC"
  },
  "entitlements": {
    "effie_codes": ["TSPBLKBS01", "TSPBSBST01"],
    "ecp_codes": ["TSPBLKBS01"],
    "effie_ecp_mismatch": true,
    "mismatch_codes": ["TSPBSBST01"]
  },
  "stream": {
    "ip_address": "192.168.1.x",
    "is_spectrum_ip": true,
    "ooh_flag": false,
    "bitrate_kbps": 4500,
    "quality_indicator": "normal"
  },
  "dvr": {
    "dvr_supported": true,
    "dvr_feature_active": true,
    "dvr_eng_status": "OK"
  },
  "stb_health": {
    "last_reboot_timestamp": "2026-03-01T14:22:00Z",
    "last_reboot_reason": "user_initiated",
    "reboots_24h": 1,
    "active_errors": ["GLI-6001"]
  }
}
```

### Channel entitlement endpoint: `GET /device/{mac}/entitlement?tms_id={tms_id}`

```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "tms_id": "SH123456789",
  "channel_number": 12,
  "entitled": false,
  "mini_guide_entitled": false,
  "authorizing_package": null,
  "boc_bc_status": "Launched",
  "billing_code": "TSPBSBST01",
  "billing_code_in_package": false
}
```

### STB logs endpoint: `GET /device/{mac}/logs?limit=50`

```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "log_entries": [
    {
      "timestamp": "2026-03-04T10:15:00Z",
      "level": "ERROR",
      "code": "GLI-6001",
      "message": "Guide lineup info unavailable"
    }
  ]
}
```

---

## Integration with vpoRAG Triage Workflow

### Updated search step in `TriageAssistant.md`

The SpecNav API call runs in parallel with the existing KB and Jira searches:

```
Step 2 — Execute three searches simultaneously:

  # KB search
  powershell -Command "& 'Searches\Scripts\Search-DomainAware.ps1' -Terms ... -Query ..."

  # Jira search
  powershell -Command "& 'Searches\Scripts\Search-JiraTickets.ps1' -Terms ..."

  # SpecNav API (when MAC or account number is available)
  curl -s "http://<specnav-api>/device/<MAC>" -H "Authorization: Bearer <token>"
```

### Pre-population logic

When the SpecNav API response is available, Amazon Q should:

1. Use `account_number` to pre-fill Splunk queries (replace `ACCOUNT_NUMBER` placeholder)
2. Use `kma` to pre-fill VO Kibana `location:<KMA>` filter
3. Use `device.model` + `firmware` to add device context to OpenSearch DQL
4. If `effie_ecp_mismatch: true` → add Entitlement Recalc as first recommended action
5. If `ooh_flag: true` → add OOH/IP investigation as first hypothesis
6. If `active_errors` contains known codes (GLI-6001, STBA-5205) → link to KB playbook chunks

---

## Data Fields Mapped to Query Systems

| API Field | Query System | Usage |
|---|---|---|
| `account_number` | Splunk SPL | `index=aws-* ACCOUNT_NUMBER` |
| `kma` | VO Kibana | `"OV-TUNE-FAIL" AND location:<KMA>` |
| `mac` | VO Kibana / OpenSearch | Device-level filtering |
| `device.model` | OpenSearch DQL | `device.model: WorldBox-XG1v4` |
| `stream.ip_address` | Splunk SPL | IP-based session correlation |
| `entitlements.effie_codes` | Splunk SPL | Entitlement code verification queries |
| `stb_health.active_errors` | VO Kibana | Error code spike correlation |

---

## Open Questions

| Question | Impact |
|---|---|
| What authentication does the SpecNav API use? | Determines how credentials are stored and passed |
| Is there an existing SpecNav REST API or does one need to be built? | Determines build vs. integrate effort |
| What is the rate limit / SLA for the API? | Determines whether to cache responses per session |
| Are all data fields (KMA, Effie codes, stream IP) available in a single endpoint or multiple? | Determines number of parallel calls needed |
| Does the API support lookup by account number in addition to MAC? | Some triage sessions start with account, not MAC |
| What environments are available (prod, staging)? | Determines testing approach |
| Is the SpecNav API accessible from the vpoRAG MCP server network segment? | Relevant if MCP server plan (see MCP-Server-Plan.md) is implemented first |

---

## Relationship to Other Plans

- **MCP-Server-Plan.md**: If the MCP server is built first, the SpecNav API call can be
  implemented as a fourth MCP tool (`get_device_info`) alongside `search_kb`, `search_jira`,
  and `build_index`. This is the preferred integration path.
- **Jira Stage 2**: SpecNav device data (MAC, account, KMA) could enrich Jira ticket indexing
  to enable device-level ticket correlation — a future enhancement.

---

## Notes from Initial SpecNav Team Discussion (2026-03-05)

- SpecNav is used as the primary triage tool across all VPO engineers
- Most common entry point is MAC address lookup → Cloud Guide entitlement check
- DYWTU diagnostic tool is a frequent second step when entitlement issues are found
- Stream quality / bitrate check is the first step for A/V sync issues (confirmed by Jira pattern)
- DVR status commands (`dvreng list-completed`, `pwreg enumi`) are run via SpecNav STB WorldBox
- Tickets are sometimes auto-created by SpecNav itself (seen in Jira: "Spectrum Navigator
  Automated Jira Ticket Creation" description pattern)
