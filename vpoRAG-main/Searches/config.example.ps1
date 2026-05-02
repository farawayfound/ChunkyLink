# Searches/config.example.ps1 — copy to config.ps1 and adjust for your environment
# config.ps1 is gitignored — never commit it.

# ══════════════════════════════════════════════════════════════════════════════
# PRIMARY SEARCH MODE
# ══════════════════════════════════════════════════════════════════════════════
# "MCP"   — use the centralized LAN server (192.168.1.29).
#            Amazon Q calls search_kb / search_jira MCP tools directly.
#            PowerShell scripts are not used for KB or Jira searches.
# "Local" — use local JSONL files and local CSV/SQL sources.
#            Amazon Q calls Search-DomainAware.ps1 and Search-JiraTickets.ps1
#            via executeBash. No network dependency beyond optional SSMS.
$SEARCH_MODE = "MCP"


# ══════════════════════════════════════════════════════════════════════════════
# MCP MODE SETTINGS  (used when $SEARCH_MODE = "MCP")
# ══════════════════════════════════════════════════════════════════════════════

# URL of the MCP server on the local network.
# Configure in VS Code settings.json under amazonQ.mcp.servers (see mcp_server/README.md).
$MCP_SERVER_URL = "http://192.168.1.29:8000"

# SSH credentials for scripts that connect directly to the MCP server (e.g. Sync-JSONIndex.ps1).
# $MCP_SSH_KEY defaults to $HOME\.ssh\vporag_key if not set.
# Run Ansible\MCP\setup_ssh_key.ps1 once to generate and install the key.
$MCP_SSH_USER = "vpomac"
$MCP_SSH_KEY  = "$HOME\.ssh\vporag_key"

# Shared bearer token — must match AUTH_TOKEN in mcp_server/config.py on the server.
# Leave empty if AUTH_TOKEN is not set on the server (trusted LAN only).
$MCP_AUTH_TOKEN = ""

# ── MCP: KB search defaults ───────────────────────────────────────────────────
# Default search level passed to search_kb(level=...).
# Quick:      4 phases, ~75 chunks  — fast triage
# Standard:   6 phases, ~185 chunks — default, covers 90% of cases
# Deep:       8 phases, ~460 chunks — complex multi-system issues
# Exhaustive: 8 phases, ~920 chunks — root cause / outage analysis
$MCP_SEARCH_LEVEL = "Quick"

# ── MCP: Jira search source ───────────────────────────────────────────────────
# Which data source the MCP server's search_jira tool queries first.
# "mysql" — server-side MySQL on the MCP server (fastest; requires CSV ingest to have run)
# "csv"   — CSV files on the server's Samba share (always available)
# "sql"   — VIDPROD_MAIN via pyodbc (requires server to reach the SQL host on intranet)
# Set in mcp_server/config.py on the server — this value is informational only
# and does not override the server config. Change it there, not here.
$MCP_JIRA_SOURCE = "mysql"   # informational — actual setting lives in mcp_server/config.py


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL MODE SETTINGS  (used when $SEARCH_MODE = "Local")
# ══════════════════════════════════════════════════════════════════════════════

# ── Local: KB path ────────────────────────────────────────────────────────────
# Absolute path to the local JSON output directory.
# Must contain detail\chunks.*.jsonl (built by running indexers/build_index.py locally
# or synced via git pull from the server's committed category files).
$JSON_KB_DIR = "C:\path\to\your\JSON"

# Default search level for Search-DomainAware.ps1.
$JSON_SEARCH_LEVEL = "Standard"

# Override max chunks returned (0 = use level default).
$JSON_MAX_RESULTS = 0

# ── Local: Jira source ────────────────────────────────────────────────────────
# Primary source for Search-JiraTickets.ps1.
# "sqlite" — local SQLite mirror (structuredData/database/jira_local.db) — fastest, works fully offline
#            Sync with: python Setup/sync_local_db.py (requires LAN access to MCP server)
# "csv"    — read local CSV exports from $JIRA_DPS_CSV_DIR / $JIRA_RCA_CSV_DIR
# "sql"    — query VIDPROD_MAIN directly via jira_query.py + pyodbc
#            (requires ODBC Driver 17/18 installed locally and intranet access to VM0PWVPTSPL000)
$JIRA_PRIMARY_SOURCE = "sqlite"

# Merge results from ALL sources (LocalDB + CSV + SSMS) and deduplicate by Key.
# When $true, all three sources are queried regardless of which is primary.
$JIRA_SEARCH_ALL_SOURCES = $false

# ── Local: SQLite mirror ──────────────────────────────────────────────────────
# Path to the local SQLite DB file (created automatically on first sync).
$JIRA_LOCAL_DB = "structuredData\database\jira_local.db"
# Remote MySQL on the MCP server — used by sync_local_db.py to pull data into the local SQLite.
# Run: python Setup/sync_local_db.py  (requires LAN access to the MCP server)
$JIRA_REMOTE_MYSQL_HOST = "192.168.1.29"
$JIRA_REMOTE_MYSQL_PORT = 3306
$JIRA_REMOTE_MYSQL_USER = "jira_user"
$JIRA_REMOTE_MYSQL_PASS = ""  # Set to your jira_user MySQL password
$JIRA_REMOTE_MYSQL_DB   = "jira_db"

# ── Local: CSV directories ────────────────────────────────────────────────────
# Paths to local Jira CSV export directories (one per ticket type).
# Used only when $JIRA_PRIMARY_SOURCE = "csv" or $JIRA_SEARCH_ALL_SOURCES = $true.
$JIRA_DPS_CSV_DIR = "structuredData\JiraCSVexport\DPSTRIAGE"
$JIRA_RCA_CSV_DIR = "structuredData\JiraCSVexport\POSTRCA"

# ── Local: SQL connection ─────────────────────────────────────────────────────
# Used only when $JIRA_PRIMARY_SOURCE = "sql".
# Connection settings live in Searches/config.py (Python) — this block is a reminder.
# Requires: ODBC Driver 17 or 18 for SQL Server installed locally.
# Requires: intranet connectivity to VM0PWVPTSPL000 (not available off-network).
# Store credentials once with: python Searches/Connectors/jira_query.py --store-credentials
$JIRA_SQL_NOTE = "Connection settings in Searches/config.py — server VM0PWVPTSPL000, DB VIDPROD_MAIN"
