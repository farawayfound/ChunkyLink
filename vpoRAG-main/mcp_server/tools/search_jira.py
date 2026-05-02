# -*- coding: utf-8 -*-
"""search_jira tool — wraps jira_query.py + CSV fallback (Phase 4)."""
import csv, logging, os, re, time
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "Searches" / "Connectors"))
import config
from logger import log_event

# ── NL → query intent parser ─────────────────────────────────────────────────

_NL_PATTERNS: list[tuple] = [
    # (compiled_regex, mode, extra_kwargs)
    # COUNT patterns
    (re.compile(r"\bhow many\b",                          re.I), "count", {}),
    (re.compile(r"\btotal (number|count|tickets?)\b",     re.I), "count", {}),
    (re.compile(r"\bcount\b",                             re.I), "count", {}),
    (re.compile(r"\bhow often\b",                         re.I), "count", {}),
    (re.compile(r"\bfrequency\b",                         re.I), "count", {}),
    (re.compile(r"\bnumber of (tickets?|issues?|cases?)\b",re.I), "count", {}),
    # OLDEST patterns
    (re.compile(r"\boldest\b",                            re.I), "oldest", {}),
    (re.compile(r"\bfirst (reported|seen|ticket|case)\b", re.I), "oldest", {}),
    (re.compile(r"\bwhen (did|was) .{0,30}(first|start)", re.I), "oldest", {}),
    (re.compile(r"\boriginated\b",                        re.I), "oldest", {}),
    (re.compile(r"\bgoing back\b",                        re.I), "oldest", {}),
    (re.compile(r"\bhow far back\b",                      re.I), "oldest", {}),
    # ALL / no-limit patterns → custom mode, high limit
    (re.compile(r"\ball (\w+ )?(tickets?|issues?|cases?|dpstriage|postrca)\b", re.I), "custom", {"limit": 200}),
    (re.compile(r"\bevery (ticket|issue|case)\b",         re.I), "custom", {"limit": 200}),
    (re.compile(r"\bfull list\b",                         re.I), "custom", {"limit": 200}),
    (re.compile(r"\blist (all|every)\b",                  re.I), "custom", {"limit": 200}),
    # TREND / time-series patterns → count with since
    (re.compile(r"\btrend\b",                             re.I), "count", {"since": 6}),
    (re.compile(r"\bover (the )?(last|past) (\d+) (month|week|day)", re.I), "count", {}),
    (re.compile(r"\bspike\b",                             re.I), "count", {"since": 3}),
    (re.compile(r"\bincreasing\b",                        re.I), "count", {"since": 6}),
    # MOST COMMON / aggregation patterns → custom with high limit for downstream grouping
    (re.compile(r"\bmost common\b",                       re.I), "custom", {"limit": 100}),
    (re.compile(r"\btop (\d+)\b",                         re.I), "top",    {}),
    (re.compile(r"\bmost frequent\b",                     re.I), "custom", {"limit": 100}),
    (re.compile(r"\bbreakdown\b",                         re.I), "custom", {"limit": 100}),
    (re.compile(r"\bby (root cause|category|team|client|status)\b", re.I), "custom", {"limit": 100}),
    (re.compile(r"\bgroup(ed)? by\b",                     re.I), "custom", {"limit": 100}),
    (re.compile(r"\bdistribution\b",                      re.I), "custom", {"limit": 100}),
    # STATUS filters extracted from question
    # "active"/"in progress" → active preset (4 specific in-flight statuses)
    # "open" intentionally NOT mapped — means "not closed", which is the default behaviour
    (re.compile(r"\bactive\b|\bin progress\b",            re.I), "top",    {"status": ["active"]}),
    (re.compile(r"\bclosed\b|\bresolved\b|\bfixed\b",     re.I), "top",    {"status": ["resolved"]}),
    # SINCE extraction — "last N months/weeks"
    (re.compile(r"last (\d+) months?",                    re.I), "top",    {}),
    (re.compile(r"past (\d+) months?",                    re.I), "top",    {}),
    (re.compile(r"this (week|month|year)",                re.I), "top",    {}),
]

_SINCE_WEEK_RE  = re.compile(r"(?:last|past) (\d+) weeks?",  re.I)
_SINCE_MONTH_RE = re.compile(r"(?:last|past) (\d+) months?", re.I)
_SINCE_YEAR_RE  = re.compile(r"(?:last|past) (\d+) years?",  re.I)
_SINCE_THE_YEAR_RE = re.compile(r"(?:last|past) year\b",     re.I)  # "the last year"
_TOP_N_RE       = re.compile(r"\btop (\d+)\b",               re.I)
_TICKET_TYPE_RE = re.compile(r"\b(dpstriage|postrca|post.?rca|post rca)\b", re.I)


def _parse_question(question: str) -> dict:
    """Translate a natural-language question into search_jira kwargs.

    Returns a dict with keys: mode, limit, since, status, ticket_type.
    Only keys that differ from defaults are included.
    """
    if not question or not question.strip():
        return {}

    result: dict = {}
    q = question.strip()

    # Ticket type detection
    tt_match = _TICKET_TYPE_RE.search(q)
    if tt_match:
        raw = tt_match.group(1).lower().replace(" ", "").replace("-", "")
        result["ticket_type"] = "postrca" if "postrca" in raw else "dpstriage"

    # Since extraction (highest specificity wins)
    m = _SINCE_YEAR_RE.search(q)
    if m:
        result["since"] = int(m.group(1)) * 12
    elif _SINCE_THE_YEAR_RE.search(q):
        result["since"] = 12
    else:
        m = _SINCE_MONTH_RE.search(q)
        if m:
            result["since"] = int(m.group(1))
        else:
            m = _SINCE_WEEK_RE.search(q)
            if m:
                result["since"] = max(1, round(int(m.group(1)) / 4))

    if re.search(r"\bthis week\b", q, re.I):
        result["since"] = 1
    elif re.search(r"\bthis month\b", q, re.I):
        result["since"] = 1
    elif re.search(r"\bthis year\b", q, re.I):
        result["since"] = 12

    # Top-N extraction
    top_m = _TOP_N_RE.search(q)
    if top_m:
        result["limit"] = int(top_m.group(1))

    # Mode + extra kwargs from pattern table.
    # Priority order: count > oldest > custom > top
    # Collect all matching modes and pick highest priority.
    _MODE_PRIORITY = {"count": 4, "oldest": 3, "custom": 2, "top": 1}
    best_mode: str | None = None
    best_priority = 0
    for pattern, mode, extras in _NL_PATTERNS:
        if pattern.search(q):
            p = _MODE_PRIORITY.get(mode, 0)
            if p > best_priority:
                best_priority = p
                best_mode = mode
            # Always apply extras (status, limit) regardless of mode priority
            for k, v in extras.items():
                if k not in result:
                    result[k] = v
    if best_mode:
        result["mode"] = best_mode

    # Expand status preset strings
    if "status" in result:
        result["status"] = _expand_status(result["status"])

    return result


# ── Synonym expansion (mirrors Get-Synonyms in Search-JiraTickets.ps1) ───────
_SYNONYMS: dict[str, list[str]] = {
    "error":     ["error", "fail", "issue", "problem", "broken"],
    "fail":      ["error", "fail", "issue", "problem", "broken"],
    "issue":     ["error", "fail", "issue", "problem", "broken"],
    "problem":   ["error", "fail", "issue", "problem", "broken"],
    "broken":    ["error", "fail", "issue", "problem", "broken"],
    "freeze":    ["freeze", "hang", "stuck", "unresponsive", "lock"],
    "hang":      ["freeze", "hang", "stuck", "unresponsive", "lock"],
    "stuck":     ["freeze", "hang", "stuck", "unresponsive", "lock"],
    "restart":   ["restart", "reboot", "bounce", "cycle"],
    "reboot":    ["restart", "reboot", "bounce", "cycle"],
    "playback":  ["playback", "play", "watch", "view", "stream"],
    "play":      ["playback", "play", "watch", "view", "stream"],
    "recording": ["recording", "record", "dvr", "schedule"],
    "record":    ["recording", "record", "dvr", "schedule"],
    "fix":       ["fix", "resolve", "repair", "correct", "mitigate"],
    "resolve":   ["fix", "resolve", "repair", "correct", "mitigate"],
}

_STATUS_PRESETS: dict[str, list[str]] = {
    "active":   ["Triage In Progress", "Pending Mitigation", "More Info Needed", "Blocked"],
    "resolved": ["Closed", "Pending Verification", "Routed to POST-RCA"],
}

# DPSTRIAGE CSV columns: Summary, Description, Custom field (Root Cause),
# Custom field (Resolution / Mitigation Solution), Custom field (Resolution Category),
# Custom field (Vertical), Custom field (Responsible Team), Custom field (Last Comment)
# POSTRCA CSV columns: Summary, Custom field (Root cause (text)),
# Custom field (Resolution / Mitigation Solution), Custom field (Vertical),
# Custom field (Responsible Team), Custom field (Client)
_CSV_SEARCH_FIELDS_DPS = [
    "Summary",
    "Description",
    "Custom field (Root Cause)",
    "Custom field (Resolution / Mitigation Solution)",
    "Custom field (Resolution Category)",
    "Custom field (Vertical)",
    "Custom field (Responsible Team)",
    "Custom field (Last Comment)",
]
_CSV_SEARCH_FIELDS_RCA = [
    "Summary",
    "Custom field (Root cause (text))",
    "Custom field (Resolution / Mitigation Solution)",
    "Custom field (Vertical)",
    "Custom field (Responsible Team)",
    "Custom field (Client)",
]

# DPSTRIAGE: exclude noise statuses (denylist — permissive, future-proof)
# POSTRCA: allowlist of known valid statuses (mirrors PS1 $rcaInclude)
_DEFAULT_EXCLUDE: dict[str, tuple] = {
    "DPSTRIAGE": ("Cancelled", "Backlog"),
}
_POSTRCA_INCLUDE: tuple = (
    "Open", "In Progress", "Closed", "Approved", "Blocked", "Submitted",
    "Pending Release", "Template", "Ready For Work", "Pending Fix",
    "Deployment Complete", "Deployment In Progress", "Deployment Pending",
)


def _expand_terms(terms: list[str]) -> list[str]:
    expanded = []
    for t in terms:
        expanded.extend(_SYNONYMS.get(t.lower(), [t]))
    seen, out = set(), []
    for t in expanded:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:5]


def _expand_status(status: list[str]) -> list[str]:
    if len(status) == 1 and status[0].lower() in _STATUS_PRESETS:
        return _STATUS_PRESETS[status[0].lower()]
    return status


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _latest_csv(csv_dir: str) -> Path | None:
    d = Path(csv_dir)
    if not d.exists():
        return None
    files = sorted(d.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _csv_match(row: dict, terms: list[str], fields: list[str]) -> bool:
    for t in terms:
        pat = re.escape(t)
        for f in fields:
            if re.search(pat, row.get(f, ""), re.I):
                return True
    return False


def _csv_score(row: dict, terms: list[str], fields: list[str]) -> float:
    score = 0
    for t in terms:
        pat = re.escape(t)
        if re.search(pat, row.get("Summary", ""), re.I):
            score += 3
        for f in fields[1:]:
            if re.search(pat, row.get(f, ""), re.I):
                score += 1
    # Subtle recency bonus — light tiebreaker, does not override term relevance
    try:
        age_days = (datetime.now() - datetime.fromisoformat(row.get("Created", ""))).days
        if   age_days <= 30:  score += 3
        elif age_days <= 90:  score += 2
        elif age_days <= 180: score += 1
    except (ValueError, TypeError):
        pass
    return score


def _csv_filter(rows: list[dict], prefix: str, status: list[str],
                apply_defaults: bool, client: str) -> list[dict]:
    out = [r for r in rows if r.get("Issue key", "").startswith(f"{prefix}-")]
    if status:
        out = [r for r in out if r.get("Status", "") in status]
    elif apply_defaults:
        if prefix == "POSTRCA":
            out = [r for r in out if r.get("Status", "") in _POSTRCA_INCLUDE]
        else:
            excl = _DEFAULT_EXCLUDE.get(prefix, ())
            out = [r for r in out if r.get("Status", "") not in excl]
    if client:
        pat = re.escape(client)
        out = [r for r in out if
               re.search(pat, r.get("Custom field (Vertical)", ""), re.I) or
               re.search(pat, r.get("Custom field (Client)", ""), re.I)]
    return out


def _csv_select_top(matched: list[dict], top: int, terms: list[str],
                    is_rca: bool = False) -> list[dict]:
    fields = _CSV_SEARCH_FIELDS_RCA if is_rca else _CSV_SEARCH_FIELDS_DPS
    pre = [(r, _csv_score(r, terms, fields)) for r in matched]
    pre.sort(key=lambda x: -x[1])
    if is_rca:
        return [
            {
                "Key":            r.get("Issue key", ""),
                "Summary":        r.get("Summary", ""),
                "Status":         r.get("Status", ""),
                "Created":        r.get("Created", ""),
                "RootCause":      r.get("Custom field (Root cause (text))", ""),
                "Resolution":     r.get("Custom field (Resolution / Mitigation Solution)", ""),
                "Client":         r.get("Custom field (Client)", ""),
                "Vertical":       r.get("Custom field (Vertical)", ""),
                "Priority":       r.get("Priority", ""),
                "RelevanceScore": s,
            }
            for r, s in pre[:top]
        ]
    return [
        {
            "Key":            r.get("Issue key", ""),
            "Summary":        r.get("Summary", ""),
            "Status":         r.get("Status", ""),
            "Created":        r.get("Created", ""),
            "RootCause":      r.get("Custom field (Root Cause)", ""),
            "Resolution":     r.get("Custom field (Resolution / Mitigation Solution)", ""),
            "ResolutionCategory": r.get("Custom field (Resolution Category)", ""),
            "Vertical":       r.get("Custom field (Vertical)", ""),
            "LastComment":    r.get("Custom field (Last Comment)", ""),
            "RelevanceScore": s,
        }
        for r, s in pre[:top]
    ]


def _search_csv(terms: list[str], ticket_type: str, status: list[str],
                client: str, mode: str, limit: int, since: int) -> dict | None:
    csv_path = _latest_csv(config.JIRA_CSV_DIR)
    if not csv_path:
        logging.warning(f"search_jira CSV: no CSV found in {config.JIRA_CSV_DIR}")
        return None

    logging.info(f"search_jira CSV: {csv_path.name}")
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if since:
        cutoff = datetime.now() - timedelta(days=since * 30)
        filtered = []
        for r in rows:
            try:
                if datetime.fromisoformat(r.get("Created", "")) >= cutoff:
                    filtered.append(r)
            except (ValueError, TypeError):
                filtered.append(r)
        rows = filtered

    apply_defaults = mode in ("top", "custom") and not status
    top_dps = limit if limit else 15
    top_rca = limit if limit else 5

    dp_rows = _csv_filter(rows, "DPSTRIAGE", status, apply_defaults, client)
    rc_rows = _csv_filter(rows, "POSTRCA",   status, apply_defaults, client)
    dp_matched = [r for r in dp_rows if _csv_match(r, terms, _CSV_SEARCH_FIELDS_DPS)]
    rc_matched = [r for r in rc_rows if _csv_match(r, terms, _CSV_SEARCH_FIELDS_RCA)]

    if mode == "count":
        result = {"mode": "count", "terms": terms, "source": "csv"}
        if ticket_type in ("both", "dpstriage"):
            result["dpstriage_count"] = len(dp_matched)
        if ticket_type in ("both", "postrca"):
            result["postrca_count"] = len(rc_matched)
        return result

    if mode == "oldest":
        def _oldest(matched: list[dict]) -> dict | None:
            if not matched:
                return None
            r = min(matched, key=lambda x: x.get("Created", "9999"))
            return {"Key": r.get("Issue key", ""), "Summary": r.get("Summary", ""),
                    "Status": r.get("Status", ""), "Created": r.get("Created", "")}
        result = {"mode": "oldest", "terms": terms, "source": "csv"}
        if ticket_type in ("both", "dpstriage"):
            result["dpstriage_oldest"] = _oldest(dp_matched)
        if ticket_type in ("both", "postrca"):
            result["postrca_oldest"] = _oldest(rc_matched)
        return result

    dp_final = _csv_select_top(dp_matched, top_dps, terms, is_rca=False) if ticket_type in ("both", "dpstriage") else []
    rc_final = _csv_select_top(rc_matched, top_rca, terms, is_rca=True)  if ticket_type in ("both", "postrca") else []
    return {"dpstriage": dp_final, "postrca": rc_final,
            "mode": mode, "terms": terms, "source": "csv"}


# ── Merge (mirrors Merge-JiraResults) ────────────────────────────────────────

def _merge(a: dict, b: dict) -> dict:
    def _dedup(lst: list[dict]) -> list[dict]:
        seen, out = set(), []
        for item in lst:
            k = item.get("Key") or item.get("key", "")
            if k not in seen:
                seen.add(k)
                out.append(item)
        return out

    if a.get("mode") == "count":
        return {
            "dpstriage_count": (a.get("dpstriage_count") or 0) + (b.get("dpstriage_count") or 0),
            "postrca_count":   (a.get("postrca_count")   or 0) + (b.get("postrca_count")   or 0),
            "mode": "count", "terms": a.get("terms", []), "source": "merged",
        }
    if a.get("mode") == "oldest":
        def _pick_oldest(x, y):
            if not x: return y
            if not y: return x
            return x if (x.get("Created", "9999") <= y.get("Created", "9999")) else y
        return {
            "dpstriage_oldest": _pick_oldest(a.get("dpstriage_oldest"), b.get("dpstriage_oldest")),
            "postrca_oldest":   _pick_oldest(a.get("postrca_oldest"),   b.get("postrca_oldest")),
            "mode": "oldest", "terms": a.get("terms", []), "source": "merged",
        }
    return {
        "dpstriage": _dedup((a.get("dpstriage") or []) + (b.get("dpstriage") or [])),
        "postrca":   _dedup((a.get("postrca")   or []) + (b.get("postrca")   or [])),
        "mode": a.get("mode", "top"), "terms": a.get("terms", []), "source": "merged",
    }


# ── Tool entry point ──────────────────────────────────────────────────────────

async def run(
    terms: list[str],
    discovered: list[str] = [],
    mode: str = "top",
    limit: int = 0,
    since: int = 0,
    ticket_type: str = "both",
    status: list[str] = [],
    client: str = "",
    question: str = "",
    sql: str = "",
) -> dict:
    """Search Jira tickets via live SQL with automatic CSV fallback.

    Args:
        terms: Search terms (required).
        discovered: Additional terms discovered from KB search.
        mode: top | count | oldest | custom.
        limit: Max results per ticket type; 0 = mode default.
        since: Only tickets created within this many months; 0 = no limit.
        ticket_type: both | dpstriage | postrca.
        status: Filter by status values (or preset: active | resolved).
        client: Filter by client name (partial match).
        question: Natural-language question — auto-sets mode/limit/since/status.
        sql: Raw SQL override (SELECT only) passed directly to jira_query.
    """
    if not terms:
        return {"error": "terms is required"}

    # NL question overrides explicit params (question is higher-level intent)
    if question:
        parsed = _parse_question(question)
        if parsed.get("mode"):        mode        = parsed["mode"]
        if parsed.get("limit"):       limit       = parsed["limit"]
        if parsed.get("since"):       since       = parsed["since"]
        if parsed.get("status"):      status      = parsed["status"]
        if parsed.get("ticket_type"): ticket_type = parsed["ticket_type"]

    t0 = time.monotonic()
    try:
        return await _run(terms, discovered, mode, limit, since, ticket_type, status, client, sql)
    except Exception as ex:
        duration_ms = round((time.monotonic() - t0) * 1000)
        log_event("tool_error", tool="search_jira", error_type=type(ex).__name__,
                  error=str(ex), terms=terms, mode=mode, duration_ms=duration_ms)
        logging.exception(f"search_jira unhandled error: {ex}")
        return {"error": str(ex)}


async def _run(
    terms: list[str],
    discovered: list[str] = [],
    mode: str = "top",
    limit: int = 0,
    since: int = 0,
    ticket_type: str = "both",
    status: list[str] = [],
    client: str = "",
    sql: str = "",
) -> dict:
    t0 = time.monotonic()
    expanded   = _expand_terms(terms)
    status     = _expand_status(status)
    csv_since  = since if since else (6 if mode == "top" else 0)
    search_both = getattr(config, "JIRA_SEARCH_BOTH_SOURCES", False)
    primary     = getattr(config, "JIRA_PRIMARY_SOURCE", "sql").lower()

    # Set keyring backend before importing jira_query
    backend = getattr(config, "KEYRING_BACKEND", "")
    if backend:
        os.environ.setdefault("PYTHON_KEYRING_BACKEND", backend)

    sql_result  = None
    csv_result  = None
    sql_error   = None

    if primary != "csv":
        try:
            import jira_query
            _jira_kwargs = dict(
                discovered=discovered[:5] or None,
                mode=mode,
                limit=limit or None,
                since_months=since or None,
                ticket_type=ticket_type,
                statuses=status or None,
                client=client or None,
            )
            if sql:
                _jira_kwargs["raw_sql"] = sql
            sql_result = jira_query.query_jira(expanded, **_jira_kwargs)
            logging.info("search_jira: SQL query succeeded")
        except Exception as ex:
            sql_error = str(ex)
            logging.warning(f"search_jira: SQL unavailable — {ex}")

    if primary == "csv" or sql_result is None:
        csv_result = _search_csv(expanded, ticket_type, status, client, mode, limit, csv_since)

    if search_both:
        if sql_result is None and primary != "csv":
            pass  # already tried and failed
        elif primary == "csv":
            try:
                import jira_query
                _jira_kwargs2 = dict(
                    discovered=discovered[:5] or None,
                    mode=mode,
                    limit=limit or None,
                    since_months=since or None,
                    ticket_type=ticket_type,
                    statuses=status or None,
                    client=client or None,
                )
                if sql:
                    _jira_kwargs2["raw_sql"] = sql
                sql_result = jira_query.query_jira(expanded, **_jira_kwargs2)
            except Exception as ex:
                logging.warning(f"search_jira: SQL (both-sources) unavailable — {ex}")
                sql_result = None
        elif csv_result is None:
            csv_result = _search_csv(expanded, ticket_type, status, client, mode, limit, csv_since)

    if sql_result and csv_result:
        result = _merge(sql_result, csv_result)
    elif sql_result:
        result = sql_result
    elif csv_result:
        result = csv_result
    else:
        return {"error": "No data source available", "sql_error": sql_error,
                "dpstriage": [], "postrca": [], "mode": mode, "terms": expanded}

    if sql_error and not search_both:
        result["_warning"] = f"SQL unavailable, used CSV fallback: {sql_error}"

    if mode == "count":
        dps_count = result.get("dpstriage_count") or 0
        rca_count  = result.get("postrca_count")   or 0
    elif mode == "oldest":
        dps_count = 1 if result.get("dpstriage_oldest") else 0
        rca_count  = 1 if result.get("postrca_oldest")   else 0
    else:
        dps_count = len(result.get("dpstriage") or [])
        rca_count  = len(result.get("postrca")   or [])
    duration_ms = round((time.monotonic() - t0) * 1000)
    logging.info(
        f"search_jira: mode={mode} source={result.get('source','?')} "
        f"dps={dps_count} rca={rca_count}"
    )
    log_event("search_jira",
              terms=expanded, mode=mode, ticket_type=ticket_type,
              source=result.get("source", "?"),
              dps_rows=dps_count, rca_rows=rca_count,
              sql_error=sql_error, duration_ms=duration_ms)

    if mode == "top" and dps_count == 0 and rca_count == 0:
        log_event("search_jira_warning",
                  warning_type="no_results",
                  terms=expanded, mode=mode, ticket_type=ticket_type,
                  source=result.get("source", "?"),
                  sql_error=sql_error, duration_ms=duration_ms)

    return result
