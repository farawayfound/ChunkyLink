# VO Kibana Reference - Spectrum Guide / AMS

> **Scope:** VO Kibana only. Kibana search syntax (plain text + `field:value` filters) is INVALID in Splunk and OpenSearch DQL.
> - `index=aws*`, `| stats`, `| rex` are **Splunk SPL** — do NOT use in Kibana queries
> - `field.path: value` dot-notation is **OpenSearch DQL** — do NOT use in Kibana queries
> - Account/lineup/entitlement data → use **SPL_Reference.md** (Splunk)
> - STVA/OneApp/Roku client errors → use **DQL_Reference.md** (OpenSearch)

## Overview

VO Kibana is the primary tool for monitoring Spectrum Guide (STB) health metrics — tune failures, EPG errors, reboots, and SGD failures. It is **not** Splunk and does not use SPL syntax.

**URL:** `http://kibana.vo.charter.com/`  
**Timezone:** All timestamps in VO Kibana are **MST**  
**Index:** `spec-zod-ams-am_activity-*` (also `spec-zod-ams-am*`)  
**Access:** Create a VOINTAKE ticket → email Scott.W.Bullock@charter.com, Lance Zukel, MAHENDRANADHA.YERASI@charter.com with request and ticket info

> Replaced legacy Venona dashboard (deprecated).

---

## Core Search Syntax

```
"SEARCH_TERM" AND location:<KMA>
"SEARCH_TERM" AND location:<KMA> AND Reason:<REASON_CODE>
"SEARCH_TERM" AND ("<MAC1>" OR "<MAC2>" OR "<MAC3>")
```

- **location** = KMA (Key Market Area) of the STB's market. Find KMA via: Playbook - DVR Cassandra to AMS Mapping
- **Reason** = specific error/reason code (e.g. `STREAM-NO-DATA`, `DVBS_REBOOT_POWER_CABLE_UNPLUGGED`)
- Add **App Screen** filter for additional context on tune failures

---

## Search Terms by Use Case

| Search Term | Use Case |
|---|---|
| `OV-TUNE-FAIL` | Tune failures / 3802 channel unavailable |
| `EPG-ERR` | EPG/guide data errors (3401, No Data on mini-guide) |
| `REBOOT` | STB reboot spikes |
| `SGD-FAIL` | SGD (Spectrum Guide Data) failures |

---

## Query Patterns

### Tune Failures — Area-Wide Spike Check (3802 / OV-TUNE-FAIL)
```
"OV-TUNE-FAIL" AND location:<KMA>
```
*Add TMS ID and error code to narrow down. Example: `"OV-TUNE-FAIL" AND 14897 AND location:denttx`*  
*Input: Site Data, Error, TMS ID. Add App Screen filter.*

### EPG Errors — Specific STB MACs
```
"EPG-ERR" AND ("<MAC1>" OR "<MAC2>" OR "<MAC3>")
```
*Use: Find which specific STB in an account is hitting EPG errors (3401 / No Data on mini-guide)*

### EPG Errors — Market-Wide Spike Check
```
"EPG-ERR" AND location:<KMA>
```
*Remove MAC filters, add location/ashne. If spike → create INC (e.g. INC000011557601)*

### Reboot Spike Check
```
"REBOOT" AND location:<KMA>
```
*Select Reason. If `DVBS_REBOOT_POWER_CABLE_UNPLUGGED` → ignore (customer unplugged). Otherwise investigate.*

### SGD Failure Spike Check
```
"SGD-FAIL" AND location:<KMA>
```
*Check Reason and note spike times. Remember MST offset when correlating with AM Report (EST/CST markets).*

### STB Log Verification (after SpecNav log capture)
```
"<MAC_ADDRESS>"
```
*After scheduling log capture in SpecNav MindControl, verify logs started in VO Kibana before waiting for completion.*

---

## Workflow: Correlating with AM Report

1. Open Spec Nav → Reports → Audience Measurement Report
2. Click Lineup-Level, select Market, set date to yesterday
3. Note the time and market of the spike (EST/CST)
4. Open VO Kibana — **convert spike time to MST** before searching
5. Search with appropriate term (`OV-TUNE-FAIL`, `REBOOT`, `SGD-FAIL`)
6. Select location = KMA of that market
7. Select Reason — note the dominant reason code
8. If spike is widespread → create INC, assign to VSC with all info

---

## When to Use VO Kibana vs Splunk

| Scenario | Tool |
|---|---|
| STB tune failure / 3802 error | VO Kibana (`OV-TUNE-FAIL`) |
| EPG / guide data missing | VO Kibana (`EPG-ERR`) |
| STB reboot spike | VO Kibana (`REBOOT`) |
| SGD failure spike | VO Kibana (`SGD-FAIL`) |
| STB lineup lookup / entitlements | Splunk (`index=aws-spec stblookup`) |
| Account-level error analysis | Splunk (`index=aws-*`) |
| STVA streaming / lineup ID | Splunk (`index=aws-stva`) |

---

## Notes

- VO Kibana covers **Spectrum Guide (STB/WorldBox)** — not STVA streaming devices
- For STVA/OneApp playback errors use OpenSearch Quantum Events (see DQL_Reference.md)
- Spike threshold for INC creation: typically >2% error rate in AM Report
- Known reboot cause to ignore: `DVBS_REBOOT_POWER_CABLE_UNPLUGGED` (customer action)
- Mass reboot known issue: POSTTRIAGE-4825 / ZCLIENT-465 (boxes crash every ~24 days in some markets)
