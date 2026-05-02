# -*- coding: utf-8 -*-
"""
Jira Query — server-side MySQL (jira_db) primary, SSMS remote secondary.

Source selection is controlled by the JIRA_PRIMARY_SOURCE setting in
mcp_server/config.py (server) or Searches/config.py (Windows client):
  "mysql"  — server-side MySQL jira_db (default on MCP server)
  "sql"    — remote SSMS VIDPROD_MAIN (requires corporate network)
  "csv"    — flat-file fallback (handled by search_jira.py, not here)

On the Windows client, JIRA_PRIMARY_SOURCE = "sqlite" routes to the local
SQLite mirror (Searches/jira_local.db) via query_local_db.py instead.

Usage:
  python Searches/Connectors/jira_query.py term1 term2 [--discovered tag1 tag2]
                                                       [--mode top|count|oldest|custom]
                                                       [--limit N]
                                                       [--since MONTHS]
                                                       [--ticket-type dpstriage|postrca|both]
Output: JSON to stdout
"""

import os, sys, json, logging, re
from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    raise SystemExit("Please install pymysql: pip install pymysql")

try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

try:
    import keyring
except ImportError:
    raise SystemExit("Please install keyring: pip install keyring")

# Searches/Connectors/ → parent is Searches/ → parent is repo root
_searches_dir = Path(__file__).resolve().parent.parent
_repo_root    = _searches_dir.parent
sys.path.insert(0, str(_searches_dir))
import config as _searches_config
# Merge mcp_server/config.py on top when available (provides MYSQL_* on the server)
try:
    import importlib.util as _ilu
    _mcp_spec = _ilu.spec_from_file_location("_mcp_config", str(_repo_root / "mcp_server" / "config.py"))
    if _mcp_spec:
        _mcp_config = _ilu.module_from_spec(_mcp_spec)
        _mcp_spec.loader.exec_module(_mcp_config)
        # Overlay mcp_server/config attributes onto Searches/config so callers see one namespace
        for _k, _v in vars(_mcp_config).items():
            if not _k.startswith("__"):
                setattr(_searches_config, _k, _v)
except Exception:
    pass  # mcp_server/config.py absent (Windows client) — Searches/config.py is sufficient
config = _searches_config

KEYRING_SERVICE = "vpoRAG_Jira"
MAX_TERMS = 5
DEFAULT_TOP_DPSTRIAGE = 15
DEFAULT_TOP_POSTRCA   = 5
DEFAULT_SINCE_MONTHS  = 6

DEFAULT_EXCLUDE_STATUSES = {
    "dpstriage": ("Cancelled", "Backlog"),
    "postrca":   ("Closed",),
}


# ── Retry thresholds ─────────────────────────────────────────────────────────
RETRY_MIN_DPSTRIAGE = 5
RETRY_MIN_POSTRCA   = 2

# ── Field intent map — keyword → {column: weight} ────────────────────────────
# Detected from terms; drives dynamic field selection in queries.
_FIELD_INTENT: list[tuple[str, dict]] = [
    # resolution / fix intent
    (r"\b(fix|resolv|mitigat|workaround|solution|clear cache|reboot|restart)",
     {"Resolution_Mitigation": 3, "Resolution_Category": 2, "Root_Cause": 1}),
    # root cause / diagnosis intent
    (r"\b(root.?cause|cause|why|reason|diagnos|fault|failure|outage)",
     {"Root_Cause": 3, "Description": 2, "Resolution_Mitigation": 1}),
    # platform / device intent
    (r"\b(ios|android|roku|xumo|firetv|appletv|stb|set.?top|laptop|macbook|browser|platform|device)",
     {"Platform_Affected": 3, "Description": 2, "Summary": 1}),
    # error / symptom intent
    (r"\b(error|no local|missing|not authorized|black screen|buffering|freeze|hang|crash|fail)",
     {"Description": 3, "Summary": 2, "Root_Cause": 1}),
    # org / customer intent
    (r"\b(org|organization|vertical|customer|residential|commercial|enterprise|division)",
     {"Requesting_Organization": 3, "Vertical": 2, "Customer_Type": 1}),
    # environment / headend intent
    (r"\b(headend|node|controller|environment|he |sdv|cms)",
     {"Environment_HE_Controller": 3, "Description": 2}),
    # comment / recent activity intent
    (r"\b(comment|update|latest|recent|last note|activity)",
     {"Last_Comment": 3, "Description": 1}),
]

# All searchable text columns with default weights (used when no intent detected)
_DEFAULT_FIELDS = {
    "Summary":              3,
    "Description":          2,
    "Root_Cause":           2,
    "Resolution_Mitigation":1,
    "Resolution_Category":  1,
    "Last_Comment":         1,
    "Labels":               2,
}

# Relaxed retry uses all columns equally
_RELAXED_FIELDS = {
    "Summary":                  3,
    "Description":              2,
    "Root_Cause":               2,
    "Resolution_Mitigation":    2,
    "Resolution_Category":      1,
    "Last_Comment":             1,
    "Labels":                   2,
    "Platform_Affected":        1,
    "Requesting_Organization":  1,
    "Vertical":                 1,
    "Environment_HE_Controller":1,
    "Customer_Impact":          1,
}


def _detect_fields(terms: list[str]) -> dict[str, int]:
    """Score terms against intent patterns; return field→weight dict."""
    combined = " ".join(terms).lower()
    scores: dict[str, int] = {}
    for pattern, fields in _FIELD_INTENT:
        if re.search(pattern, combined, re.I):
            for col, w in fields.items():
                scores[col] = max(scores.get(col, 0), w)
    # Always include Summary + Description as baseline
    scores.setdefault("Summary", 2)
    scores.setdefault("Description", 1)
    return scores if len(scores) > 2 else _DEFAULT_FIELDS


# ── Shared helpers ────────────────────────────────────────────────────────────

def _term_like_clauses(terms: list[str], fields: dict[str, int],
                       placeholder: str = "%s") -> tuple[str, list]:
    cols = list(fields.keys())
    per_term = " OR ".join(f"`{c}` LIKE {placeholder}" for c in cols)
    clause = " OR ".join(f"({per_term})" for _ in terms)
    params = [f"%{t}%" for t in terms for _ in cols]
    return clause, params


def _score_expr(terms: list[str], fields: dict[str, int],
                placeholder: str = "%s") -> tuple[str, list]:
    parts, params = [], []
    for t in terms:
        for col, weight in fields.items():
            parts.append(f"(CASE WHEN `{col}` LIKE {placeholder} THEN {weight} ELSE 0 END)")
            params.append(f"%{t}%")
    return " + ".join(parts), params


# ── MySQL query functions ─────────────────────────────────────────────────────

def _mysql_conn() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", getattr(config, "MYSQL_HOST", "localhost")),
        port=int(os.environ.get("MYSQL_PORT", getattr(config, "MYSQL_PORT", 3306))),
        user=os.environ.get("MYSQL_USER", getattr(config, "MYSQL_USER", "jira_user")),
        password=os.environ.get("MYSQL_PASS", getattr(config, "MYSQL_PASS", "")),
        database=os.environ.get("MYSQL_DB", getattr(config, "MYSQL_DB", "jira_db")),
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


def _status_clauses(table: str, statuses: list[str]) -> tuple[str, list]:
    excl_statuses = DEFAULT_EXCLUDE_STATUSES.get(table.lower(), ())
    if statuses:
        return f"AND Status IN ({','.join('%s' for _ in statuses)})", list(statuses)
    elif excl_statuses:
        return f"AND Status NOT IN ({','.join('%s' for _ in excl_statuses)})", list(excl_statuses)
    return "", []


def _client_clauses(client: str) -> tuple[str, list]:
    if client:
        return "AND (Vertical LIKE %s OR Platform_Affected LIKE %s)", [f"%{client}%", f"%{client}%"]
    return "", []


def _mysql_query_top(table: str, top: int, terms: list[str], since_months: int,
                     exclude_keys: list[str], statuses: list[str], client: str,
                     fields: dict[str, int] = None) -> tuple[str, list]:
    fields = fields or _detect_fields(terms)
    score_expr, score_params = _score_expr(terms, fields)
    where_clause, where_params = _term_like_clauses(terms, fields)
    date_filter   = f"AND Created > DATE_SUB(NOW(), INTERVAL {since_months} MONTH)" if since_months else ""
    excl          = f"AND `Key` NOT IN ({','.join('%s' for _ in exclude_keys)})" if exclude_keys else ""
    excl_params   = list(exclude_keys) if exclude_keys else []
    status_clause, status_params = _status_clauses(table, statuses)
    client_clause, client_params = _client_clauses(client)
    sql = f"""
SELECT `Key`, Summary, Description, Status, Platform_Affected AS Client, Created,
       Root_Cause AS RootCause, Resolution_Mitigation AS Resolution,
       Resolution_Category, Last_Comment,
       ({score_expr}) AS RelevanceScore
FROM `{table}`
WHERE 1=1 {date_filter} AND ({where_clause}) {excl} {status_clause} {client_clause}
ORDER BY RelevanceScore DESC, Created DESC
LIMIT {top}
"""
    return sql, score_params + where_params + excl_params + status_params + client_params


def _mysql_query_count(table: str, terms: list[str], since_months: int,
                       statuses: list[str], client: str,
                       fields: dict[str, int] = None) -> tuple[str, list]:
    fields = fields or _detect_fields(terms)
    where_clause, where_params = _term_like_clauses(terms, fields)
    date_filter   = f"AND Created > DATE_SUB(NOW(), INTERVAL {since_months} MONTH)" if since_months else ""
    status_clause, status_params = _status_clauses(table, statuses)
    client_clause, client_params = _client_clauses(client)
    sql = f"SELECT COUNT(*) AS TotalCount FROM `{table}` WHERE 1=1 {date_filter} AND ({where_clause}) {status_clause} {client_clause}"
    return sql, where_params + status_params + client_params


def _mysql_query_oldest(table: str, terms: list[str], statuses: list[str], client: str,
                        fields: dict[str, int] = None) -> tuple[str, list]:
    fields = fields or _detect_fields(terms)
    where_clause, where_params = _term_like_clauses(terms, fields)
    status_clause, status_params = _status_clauses(table, statuses)
    client_clause, client_params = _client_clauses(client)
    sql = f"SELECT `Key`, Summary, Status, Created FROM `{table}` WHERE 1=1 AND ({where_clause}) {status_clause} {client_clause} ORDER BY Created ASC LIMIT 1"
    return sql, where_params + status_params + client_params


def query_jira_mysql(terms: list[str], discovered: list[str] = None,
                     mode: str = "top", limit: int = None,
                     since_months: int = None, ticket_type: str = "both",
                     statuses: list[str] = None, client: str = None,
                     raw_sql: str = None) -> dict:
    if raw_sql:
        # Normalize common table name aliases so raw SQL works regardless of what the caller used
        raw_sql = re.sub(r'\bdpstriage_tickets\b', 'dpstriage', raw_sql, flags=re.I)
        raw_sql = re.sub(r'\bpostrca_tickets\b',   'postrca',   raw_sql, flags=re.I)
        # Backtick-quote bare `Key` column references (MySQL reserved word)
        raw_sql = re.sub(r'(?<!`)\bKey\b(?!`)', '`Key`', raw_sql)
        with _mysql_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(raw_sql)
                rows = cur.fetchall()
                return {"raw_results": [dict(r) for r in rows], "mode": "raw", "source": "mysql"}

    terms = terms[:MAX_TERMS]
    run_dps = ticket_type in ("both", "dpstriage")
    run_rca = ticket_type in ("both", "postrca")
    fields  = _detect_fields(terms)

    def _exec_top(cur, table, top, sm, excl, f):
        sql, params = _mysql_query_top(table, top, terms, sm, excl, statuses or [], client, f)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    with _mysql_conn() as conn:
        with conn.cursor() as cur:

            if mode == "count":
                result = {}
                if run_dps:
                    sql, params = _mysql_query_count("dpstriage", terms, since_months, statuses or [], client, fields)
                    cur.execute(sql, params)
                    result["dpstriage_count"] = cur.fetchone()["TotalCount"]
                if run_rca:
                    sql, params = _mysql_query_count("postrca", terms, since_months, statuses or [], client, fields)
                    cur.execute(sql, params)
                    result["postrca_count"] = cur.fetchone()["TotalCount"]
                result.update({"mode": "count", "terms": terms, "source": "mysql"})
                return result

            if mode == "oldest":
                result = {}
                if run_dps:
                    sql, params = _mysql_query_oldest("dpstriage", terms, statuses or [], client, fields)
                    cur.execute(sql, params)
                    result["dpstriage_oldest"] = cur.fetchone()
                if run_rca:
                    sql, params = _mysql_query_oldest("postrca", terms, statuses or [], client, fields)
                    cur.execute(sql, params)
                    result["postrca_oldest"] = cur.fetchone()
                result.update({"mode": "oldest", "terms": terms, "source": "mysql"})
                return result

            # top / custom — initial pass
            top_dps = limit or DEFAULT_TOP_DPSTRIAGE
            top_rca = limit or DEFAULT_TOP_POSTRCA
            sm_dps  = since_months if since_months is not None else (DEFAULT_SINCE_MONTHS if mode == "top" else None)
            sm_rca  = since_months if since_months is not None else (DEFAULT_SINCE_MONTHS if mode == "top" else None)

            dpstriage, postrca = [], []
            if run_dps:
                dpstriage = _exec_top(cur, "dpstriage", top_dps, sm_dps, [], fields)
            if run_rca:
                postrca = _exec_top(cur, "postrca", top_rca, sm_rca, [], fields)

            if discovered:
                disc = discovered[:MAX_TERMS]
                excl = [r["Key"] for r in dpstriage + postrca]
                if run_dps:
                    dpstriage += _exec_top(cur, "dpstriage", max(1, top_dps // 2), sm_dps, excl, fields)
                if run_rca:
                    postrca   += _exec_top(cur, "postrca",   max(1, top_rca // 2), sm_rca, excl, fields)

            # ── Retry with relaxed strategy if below thresholds ──────────────────────
            needs_retry = (
                (run_dps and len(dpstriage) < RETRY_MIN_DPSTRIAGE) or
                (run_rca and len(postrca)   < RETRY_MIN_POSTRCA)
            )
            retry_reason = None
            if needs_retry:
                retry_steps = [
                    # Step 1: broaden fields, keep date filter
                    {"fields": _RELAXED_FIELDS, "since": sm_dps, "label": "relaxed_fields"},
                    # Step 2: broaden fields + drop date filter
                    {"fields": _RELAXED_FIELDS, "since": None,   "label": "relaxed_fields_no_date"},
                ]
                for step in retry_steps:
                    excl_keys = [r["Key"] for r in dpstriage + postrca]
                    retry_dps, retry_rca = [], []
                    if run_dps and len(dpstriage) < RETRY_MIN_DPSTRIAGE:
                        retry_dps = _exec_top(cur, "dpstriage", top_dps - len(dpstriage),
                                              step["since"], excl_keys, step["fields"])
                    if run_rca and len(postrca) < RETRY_MIN_POSTRCA:
                        retry_rca = _exec_top(cur, "postrca", top_rca - len(postrca),
                                              step["since"], excl_keys, step["fields"])
                    if retry_dps or retry_rca:
                        dpstriage += retry_dps
                        postrca   += retry_rca
                        retry_reason = step["label"]
                    # Stop if both thresholds now met
                    if (not run_dps or len(dpstriage) >= RETRY_MIN_DPSTRIAGE) and \
                       (not run_rca or len(postrca)   >= RETRY_MIN_POSTRCA):
                        break

    result = {
        "dpstriage": dpstriage,
        "postrca":   postrca,
        "mode":      mode,
        "terms":     terms,
        "discovered_terms": discovered or [],
        "source":    "mysql",
    }
    if retry_reason:
        result["_retry"] = retry_reason
    return result


# ── SSMS (remote SQL Server) query functions ──────────────────────────────────

def _where_terms_ssms(terms: list[str]) -> tuple[str, list]:
    clause = " OR ".join("(Summary LIKE ? OR [Description] LIKE ?)" for _ in terms)
    params = [p for t in terms for p in (f"%{t}%", f"%{t}%")]
    return clause, params


def _score_expr_ssms(terms: list[str]) -> tuple[str, list]:
    expr = " + ".join(
        "(CASE WHEN Summary LIKE ? THEN 2 ELSE 0 END + CASE WHEN [Description] LIKE ? THEN 1 ELSE 0 END)"
        for _ in terms
    )
    params = [p for t in terms for p in (f"%{t}%", f"%{t}%")]
    return expr, params


def _extra_filters_ssms(statuses: list[str], client: str, exclude_statuses: tuple = ()) -> tuple[str, list]:
    clauses, params = [], []
    if statuses:
        clauses.append(f"AND [Status] IN ({','.join('?' for _ in statuses)})")
        params.extend(statuses)
    elif exclude_statuses:
        clauses.append(f"AND [Status] NOT IN ({','.join('?' for _ in exclude_statuses)})")
        params.extend(exclude_statuses)
    if client:
        clauses.append("AND [Client] LIKE ?")
        params.append(f"%{client}%")
    return " ".join(clauses), params


def _ssms_conn():
    username = os.environ.get("JIRA_USER") or keyring.get_password(KEYRING_SERVICE, "username")
    password = os.environ.get("JIRA_PASS") or keyring.get_password(KEYRING_SERVICE, "password")
    if not username or not password:
        raise RuntimeError(
            "Jira SSMS credentials not found. Set JIRA_USER/JIRA_PASS env vars (server) "
            "or run: python Searches/Connectors/jira_query.py --store-credentials (Windows)"
        )
    conn_str = (
        f"DRIVER={{{getattr(config, 'JIRA_SQL_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
        f"SERVER={config.JIRA_SQL_SERVER};"
        f"DATABASE={getattr(config, 'JIRA_SQL_DATABASE', 'VIDPROD_MAIN')};"
        f"UID={username};PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


def _row_to_dict(cursor, row) -> dict:
    cols = [col[0] for col in cursor.description]
    return {k: (str(v) if v is not None else None) for k, v in zip(cols, row)}


def query_jira_ssms(terms: list[str], discovered: list[str] = None,
                    mode: str = "top", limit: int = None,
                    since_months: int = None, ticket_type: str = "both",
                    statuses: list[str] = None, client: str = None) -> dict:
    if not HAS_PYODBC:
        raise RuntimeError("pyodbc not installed — SSMS source unavailable")
    terms = terms[:MAX_TERMS]
    run_dps = ticket_type in ("both", "dpstriage")
    run_rca = ticket_type in ("both", "postrca")

    with _ssms_conn() as conn:
        cur = conn.cursor()

        if mode == "count":
            result = {}
            for prefix, run in (("DPSTRIAGE", run_dps), ("POSTRCA", run_rca)):
                if not run:
                    continue
                wc, wp = _where_terms_ssms(terms)
                df = f"AND Created > DATEADD(MONTH, -{since_months}, GETDATE())" if since_months else ""
                extra, ep = _extra_filters_ssms(statuses or [], client)
                sql = f"SELECT COUNT(*) FROM [VIDPROD_MAIN].[VSO].[JIRA_VIDEO_DETAILS] WHERE [Key] LIKE '{prefix}%' {df} AND ({wc}) {extra}"
                cur.execute(sql, wp + ep)
                result[f"{prefix.lower()}_count"] = cur.fetchone()[0]
            result.update({"mode": "count", "terms": terms, "source": "ssms"})
            return result

        if mode == "oldest":
            result = {}
            for prefix, run, key in (("DPSTRIAGE", run_dps, "dpstriage_oldest"), ("POSTRCA", run_rca, "postrca_oldest")):
                if not run:
                    continue
                wc, wp = _where_terms_ssms(terms)
                extra, ep = _extra_filters_ssms(statuses or [], client)
                sql = f"SELECT TOP 1 [Key],Summary,[Status],Created FROM [VIDPROD_MAIN].[VSO].[JIRA_VIDEO_DETAILS] WHERE [Key] LIKE '{prefix}%' AND ({wc}) {extra} ORDER BY Created ASC"
                cur.execute(sql, wp + ep)
                row = cur.fetchone()
                result[key] = _row_to_dict(cur, row) if row else None
            result.update({"mode": "oldest", "terms": terms, "source": "ssms"})
            return result

        top_dps = limit or DEFAULT_TOP_DPSTRIAGE
        top_rca = limit or DEFAULT_TOP_POSTRCA
        sm_dps  = since_months if since_months is not None else (DEFAULT_SINCE_MONTHS if mode == "top" else None)
        sm_rca  = since_months if since_months is not None else (DEFAULT_SINCE_MONTHS if mode == "top" else None)

        def _top(prefix, top, sm, excl):
            se, sp = _score_expr_ssms(terms)
            wc, wp = _where_terms_ssms(terms)
            df = f"AND Created > DATEADD(MONTH, -{sm}, GETDATE())" if sm else ""
            ex = f"AND [Key] NOT IN ({','.join('?' for _ in excl)})" if excl else ""
            extra, ep = _extra_filters_ssms(statuses or [], client, DEFAULT_EXCLUDE_STATUSES.get(prefix.lower(), ()))
            sql = f"SELECT TOP {top} [Key],Summary,[Description],[Status],[Client],Created,linked_issues,({se}) AS RelevanceScore FROM [VIDPROD_MAIN].[VSO].[JIRA_VIDEO_DETAILS] WHERE [Key] LIKE '{prefix}%' {df} AND ({wc}) {ex} {extra} ORDER BY RelevanceScore DESC,Created DESC"
            cur.execute(sql, sp + wp + list(excl) + ep)
            return [_row_to_dict(cur, r) for r in cur.fetchall()]

        dpstriage = _top("DPSTRIAGE", top_dps, sm_dps, []) if run_dps else []
        postrca   = _top("POSTRCA",   top_rca, sm_rca,  []) if run_rca else []

        if discovered:
            disc = discovered[:MAX_TERMS]
            excl = [r["Key"] for r in dpstriage + postrca]
            if run_dps:
                dpstriage += _top("DPSTRIAGE", max(1, top_dps // 2), sm_dps, excl)
            if run_rca:
                postrca   += _top("POSTRCA",   max(1, top_rca // 2), since_months, excl)

    return {"dpstriage": dpstriage, "postrca": postrca, "mode": mode,
            "terms": terms, "discovered_terms": discovered or [], "source": "ssms"}


# ── Public entry point ────────────────────────────────────────────────────────

def query_jira(terms: list[str], discovered: list[str] = None,
               mode: str = "top", limit: int = None,
               since_months: int = None, ticket_type: str = "both",
               statuses: list[str] = None, client: str = None,
               raw_sql: str = None) -> dict:
    """Query Jira tickets. Routes to MySQL, SSMS, or raises — caller handles CSV fallback."""
    source = getattr(config, "JIRA_PRIMARY_SOURCE", "mysql").lower()
    if source == "mysql":
        return query_jira_mysql(terms, discovered, mode, limit, since_months, ticket_type, statuses, client, raw_sql)
    elif source == "sql":
        return query_jira_ssms(terms, discovered, mode, limit, since_months, ticket_type, statuses, client)
    else:
        raise RuntimeError(f"Unknown JIRA_PRIMARY_SOURCE '{source}' — use 'mysql' or 'sql'")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-credentials", action="store_true",
                        help="Store Jira SSMS credentials in keyring (Windows)")
    parser.add_argument("terms", nargs="*")
    parser.add_argument("--discovered", nargs="*", default=[])
    parser.add_argument("--mode", choices=["top", "count", "oldest", "custom"], default="top")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--since", type=int, default=None, dest="since_months")
    parser.add_argument("--ticket-type", choices=["both", "dpstriage", "postrca"], default="both")
    parser.add_argument("--status", nargs="*", default=None)
    parser.add_argument("--client", type=str, default=None)
    args = parser.parse_args()

    if args.store_credentials:
        import io
        stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
        sys.stdout.write("Jira SSMS username: "); sys.stdout.flush()
        u = stdin.readline().rstrip("\n")
        sys.stdout.write("Jira SSMS password: "); sys.stdout.flush()
        p = stdin.readline().rstrip("\n")
        keyring.set_password(KEYRING_SERVICE, "username", u)
        keyring.set_password(KEYRING_SERVICE, "password", p)
        print(f"Stored username: {u}, password length: {len(p)}")
        sys.exit(0)

    if not args.terms:
        parser.error("terms are required unless using --store-credentials")

    try:
        result = query_jira(
            args.terms, discovered=args.discovered or None,
            mode=args.mode, limit=args.limit, since_months=args.since_months,
            ticket_type=args.ticket_type, statuses=args.status, client=args.client,
        )
        print(json.dumps(result, ensure_ascii=False, default=str))
    except Exception as ex:
        logging.exception(f"Jira query failed: {ex}")
        sys.exit(1)
