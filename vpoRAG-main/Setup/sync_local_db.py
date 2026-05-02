# -*- coding: utf-8 -*-
"""
sync_local_db.py — Pull Jira ticket data from the remote MySQL server into a
local SQLite database for offline fallback search.

Usage:
    python Setup/sync_local_db.py              # sync both tables
    python Setup/sync_local_db.py --table dps  # sync dpstriage only
    python Setup/sync_local_db.py --table rca  # sync postrca only

Exit codes: 0 = already up to date, 1 = error, 2 = updated
The local SQLite file path is read from Searches/config.ps1 (JIRA_LOCAL_DB).
"""
import sqlite3, sys, time, argparse
from datetime import datetime
from pathlib import Path

try:
    import mysql.connector
except ImportError:
    raise SystemExit("pip install mysql-connector-python")

# ── Config — read from Searches/config.ps1 via env or fallback to ps1 parse ──
def _read_ps1_var(ps1_path: Path, var: str, default: str) -> str:
    """Extract a scalar variable value from a .ps1 config file."""
    try:
        for line in ps1_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"${var}") and "=" in line:
                val = line.split("=", 1)[1].strip()
                # Strip inline comment (outside of quotes)
                for q in ('"', "'"):
                    if val.startswith(q):
                        end = val.find(q, 1)
                        if end != -1:
                            val = val[1:end]
                            break
                else:
                    # Unquoted — strip inline comment
                    if "#" in val:
                        val = val[:val.index("#")].strip()
                return val
    except Exception:
        pass
    return default

_ps1 = Path(__file__).parent.parent / "Searches" / "config.ps1"
REMOTE_HOST = _read_ps1_var(_ps1, "JIRA_REMOTE_MYSQL_HOST", "192.168.1.29")
REMOTE_PORT = int(_read_ps1_var(_ps1, "JIRA_REMOTE_MYSQL_PORT", "3306"))
REMOTE_USER = _read_ps1_var(_ps1, "JIRA_REMOTE_MYSQL_USER", "jira_user")
REMOTE_PASS = _read_ps1_var(_ps1, "JIRA_REMOTE_MYSQL_PASS", "")
REMOTE_DB   = _read_ps1_var(_ps1, "JIRA_REMOTE_MYSQL_DB",   "jira_db")

_local_db_val = _read_ps1_var(_ps1, "JIRA_LOCAL_DB", "structuredData/database/jira_local.db")
LOCAL_DB = (Path(__file__).parent.parent / _local_db_val).resolve()

TABLES = ["dpstriage", "postrca"]

# Columns in order — must match remote schema exactly
COLUMNS = [
    "Key", "Issue_id", "Status", "Assignee", "Summary", "Description",
    "Created", "Updated", "Priority", "Platform_Affected", "Root_Cause",
    "Resolution_Category", "Requesting_Organization", "Environment_HE_Controller",
    "Customer_Type", "Customer_Impact", "Last_Comment", "Resolution_Mitigation",
    "Vertical"
]

# ── Local SQLite setup ────────────────────────────────────────────────────────
TICKET_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    Key TEXT PRIMARY KEY,
    Issue_id TEXT, Status TEXT, Assignee TEXT, Summary TEXT, Description TEXT,
    Created TEXT, Updated TEXT, Priority TEXT, Platform_Affected TEXT,
    Root_Cause TEXT, Resolution_Category TEXT, Requesting_Organization TEXT,
    Environment_HE_Controller TEXT, Customer_Type TEXT, Customer_Impact TEXT,
    Last_Comment TEXT, Resolution_Mitigation TEXT, Vertical TEXT
)
"""

SYNC_LOG_DDL = """
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at TEXT,
    remote_host TEXT,
    table_name TEXT,
    rows_synced INTEGER,
    duration_sec REAL,
    status TEXT,
    error TEXT
)
"""

def get_local_db():
    con = sqlite3.connect(str(LOCAL_DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    for t in TABLES:
        cur.execute(TICKET_DDL.format(table=t))
    cur.execute(SYNC_LOG_DDL)
    con.commit()
    return con

def dt_to_str(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)

def _remote_snapshot(remote_cur, table):
    """Return (count, max_updated) from remote table."""
    remote_cur.execute(f"SELECT COUNT(*), MAX(`Updated`) FROM {table}")
    row = remote_cur.fetchone()
    return (row[0] or 0, dt_to_str(row[1]) or "")

def _local_snapshot(local_con, table):
    """Return (count, max_updated) from local table, or (0, '') if missing."""
    try:
        cur = local_con.cursor()
        cur.execute(f"SELECT COUNT(*), MAX(Updated) FROM {table}")
        row = cur.fetchone()
        return (row[0] or 0, row[1] or "")
    except Exception:
        return (0, "")

def sync_table(remote_cur, local_con, table):
    t0 = time.time()
    cols_sql = ", ".join(f"`{c}`" for c in COLUMNS)
    remote_cur.execute(f"SELECT {cols_sql} FROM {table}")
    rows = remote_cur.fetchall()

    local_cur = local_con.cursor()
    placeholders = ", ".join(["?"] * len(COLUMNS))
    col_names = ", ".join(COLUMNS)
    update_set = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "Key")

    for row in rows:
        vals = tuple(dt_to_str(v) for v in row)
        local_cur.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(Key) DO UPDATE SET {update_set} "
            f"WHERE excluded.Updated > {table}.Updated OR {table}.Updated IS NULL",
            vals
        )

    local_con.commit()
    duration = round(time.time() - t0, 2)
    synced = len(rows)

    local_cur.execute(
        "INSERT INTO sync_log (synced_at, remote_host, table_name, rows_synced, duration_sec, status) "
        "VALUES (?, ?, ?, ?, ?, 'ok')",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), REMOTE_HOST, table, synced, duration)
    )
    local_con.commit()
    print(f"  {table}: {synced} rows synced in {duration}s")
    return synced

def main():
    parser = argparse.ArgumentParser(description="Sync remote Jira MySQL → local SQLite")
    parser.add_argument("--table", choices=["dps", "rca", "both"], default="both")
    args = parser.parse_args()

    tables = {
        "dps": ["dpstriage"],
        "rca": ["postrca"],
        "both": TABLES
    }[args.table]

    print(f"Connecting to {REMOTE_HOST}:{REMOTE_PORT}...")
    try:
        remote = mysql.connector.connect(
            host=REMOTE_HOST, port=REMOTE_PORT,
            user=REMOTE_USER, password=REMOTE_PASS,
            database=REMOTE_DB, connection_timeout=8
        )
    except Exception as e:
        print(f"ERROR: Cannot reach remote DB — {e}")
        print("MCP server may be offline. Local DB not updated.")
        sys.exit(1)

    remote_cur = remote.cursor()
    local_con  = get_local_db()

    # Pre-check: compare remote vs local snapshots to detect no-change case
    needs_sync = False
    for table in tables:
        r_count, r_max = _remote_snapshot(remote_cur, table)
        l_count, l_max = _local_snapshot(local_con, table)
        if r_count != l_count or r_max != l_max:
            needs_sync = True
            break

    if not needs_sync:
        remote_cur.close()
        remote.close()
        local_con.close()
        print("Jira DB already up to date.")
        sys.exit(0)

    print(f"Syncing to {LOCAL_DB}...")
    total = 0
    for table in tables:
        try:
            total += sync_table(remote_cur, local_con, table)
        except Exception as e:
            print(f"  ERROR syncing {table}: {e}")
            local_con.cursor().execute(
                "INSERT INTO sync_log (synced_at, remote_host, table_name, rows_synced, duration_sec, status, error) "
                "VALUES (?, ?, ?, 0, 0, 'error', ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), REMOTE_HOST, table, str(e))
            )
            local_con.commit()

    remote_cur.close()
    remote.close()
    local_con.close()
    print(f"Done. {total} total rows synced -> {LOCAL_DB}")
    sys.exit(2)

if __name__ == "__main__":
    main()
