# -*- coding: utf-8 -*-
"""
query_local_db.py — Search local SQLite Jira mirror.
Called by Search-JiraTickets.ps1 when JIRA_PRIMARY_SOURCE = "mysql".
Outputs JSON matching the same schema as jira_query.py.
"""
import sqlite3, json, sys, argparse
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent.parent / "structuredData" / "database" / "jira_local.db"

SEARCH_COLS = {
    "dpstriage": ["Summary", "Description", "Root_Cause", "Resolution_Mitigation", "Last_Comment"],
    "postrca":   ["Summary", "Description", "Root_Cause", "Resolution_Mitigation", "Last_Comment"],
}

def score_row(row, terms):
    s = 0
    summary = (row["Summary"] or "").lower()
    for t in terms:
        tl = t.lower()
        if tl in summary:
            s += 3
        for col in ["Description", "Root_Cause", "Resolution_Mitigation", "Last_Comment"]:
            if tl in (row[col] or "").lower():
                s += 1
    return s

def build_where(terms, cols, since, status_list, client, table):
    clauses, params = [], []
    # keyword match across search columns
    term_clauses = []
    for t in terms:
        col_clauses = [f"LOWER({c}) LIKE ?" for c in cols]
        term_clauses.append("(" + " OR ".join(col_clauses) + ")")
        params.extend([f"%{t.lower()}%"] * len(cols))
    clauses.append("(" + " OR ".join(term_clauses) + ")")

    if since and since > 0:
        cutoff = (datetime.now() - timedelta(days=since * 30)).strftime("%Y-%m-%d")
        clauses.append("(Created IS NULL OR Created >= ?)")
        params.append(cutoff)

    if status_list:
        placeholders = ",".join(["?"] * len(status_list))
        clauses.append(f"Status IN ({placeholders})")
        params.extend(status_list)

    if client:
        clauses.append("(Vertical LIKE ? OR Assignee LIKE ?)")
        params.extend([f"%{client}%", f"%{client}%"])

    return " AND ".join(clauses), params

def query_table(con, table, terms, mode, limit, since, status_list, client, top):
    cols = SEARCH_COLS[table]
    where, params = build_where(terms, cols, since, status_list, client, table)
    sql = f"SELECT * FROM {table} WHERE {where}"

    cur = con.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    if mode == "count":
        return len(rows)

    if mode == "oldest":
        if not rows:
            return None
        rows.sort(key=lambda r: r.get("Created") or "")
        r = rows[0]
        return {"Key": r["Key"], "Summary": r["Summary"], "Status": r["Status"], "Created": r["Created"]}

    # top / custom — score and trim
    for r in rows:
        r["RelevanceScore"] = score_row(r, terms)
    rows.sort(key=lambda r: r["RelevanceScore"], reverse=True)
    n = limit if limit > 0 else top

    result = []
    for r in rows[:n]:
        result.append({
            "Key":            r["Key"],
            "Summary":        r["Summary"],
            "Status":         r["Status"],
            "Created":        r["Created"],
            "Updated":        r["Updated"],
            "RootCause":      r["Root_Cause"],
            "Resolution":     r["Resolution_Mitigation"],
            "LastComment":    r["Last_Comment"],
            "Vertical":       r["Vertical"],
            "RelevanceScore": r["RelevanceScore"],
        })
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--mode",        default="top", choices=["top","count","oldest","custom"])
    parser.add_argument("--ticket-type", default="both", choices=["both","dpstriage","postrca"])
    parser.add_argument("--limit",       type=int, default=0)
    parser.add_argument("--since",       type=int, default=0)
    parser.add_argument("--status",      nargs="*", default=[])
    parser.add_argument("--client",      default="")
    parser.add_argument("--db",          default=str(DEFAULT_DB))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(json.dumps({"error": f"Local DB not found: {db_path}"}))
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    tables = {
        "both":      [("dpstriage", 10), ("postrca", 5)],
        "dpstriage": [("dpstriage", 10)],
        "postrca":   [("postrca",   5)],
    }[args.ticket_type]

    if args.mode == "count":
        out = {}
        for table, _ in tables:
            out[f"{table}_count"] = query_table(con, table, args.terms, "count",
                                                args.limit, args.since, args.status, args.client, 0)
        out.update({"mode": "count", "terms": args.terms, "source": "local_db"})
        print(json.dumps(out))

    elif args.mode == "oldest":
        out = {}
        for table, _ in tables:
            out[f"{table}_oldest"] = query_table(con, table, args.terms, "oldest",
                                                 args.limit, args.since, args.status, args.client, 0)
        out.update({"mode": "oldest", "terms": args.terms, "source": "local_db"})
        print(json.dumps(out))

    else:
        out = {"mode": args.mode, "terms": args.terms, "source": "local_db"}
        for table, default_top in tables:
            out[table] = query_table(con, table, args.terms, args.mode,
                                     args.limit, args.since, args.status, args.client, default_top)
        # ensure both keys always present
        if "dpstriage" not in out: out["dpstriage"] = []
        if "postrca"   not in out: out["postrca"]   = []
        print(json.dumps(out))

    con.close()

if __name__ == "__main__":
    main()
