# .kiro — Kiro CLI Context

This directory contains the standalone triage agent steering file for Kiro CLI users.

```
.kiro/
├── README.md                  ← you are here
└── steering/
    └── KiroTriageAgent.md     ← self-contained triage agent rule
```

---

## Setup

### 1. Install Kiro CLI and locate your config directory

Kiro CLI on Windows with WSL stores its configuration under your WSL home directory:

```
\\wsl.localhost\Ubuntu-20.04\home\<your-wsl-username>\.kiro\
```

All paths below use `<username>` as the example WSL username — replace with your own.

### 2. Copy the steering rule

Copy `KiroTriageAgent.md` to Kiro's steering directory so it is auto-loaded every session:

```
\\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\steering\KiroTriageAgent.md
```

Create the `steering/` directory if it doesn't exist.

### 3. Place the data files

Kiro CLI needs access to two data files for local fallback searches. The recommended location is
a `Data/` folder inside `.kiro/`:

```
\\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\Data\JSON\          ← KB index (copy from JSON/)
\\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\Data\jira_local.db  ← local Jira SQLite mirror
```

To populate these:
- **JSON index** — copy the contents of `JSON/` from the main repo into `.kiro\Data\JSON\`.
  Only the `detail/` subdirectory is needed (`chunks.*.jsonl` files).
- **jira_local.db** — copy from `Setup\Local\jira_local.db` in the main repo, or run
  `python Setup/sync_local_db.py` to pull a fresh copy from the MCP server.

### 4. Update the paths in the rule file

Open `KiroTriageAgent.md` and update the three path values at the top of the file to match
where you placed the data files:

```
KB_DIR   = \\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\Data\JSON
JIRA_DB  = \\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\Data\jira_local.db
LEARN_DB = \\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\Data\JSON\detail\chunks.learned.jsonl
```

These are the only values that need to change per engineer. Everything else in the rule is
self-contained.

### 5. Configure the MCP server in Kiro

Add the vpoMac MCP server entry to:

```
\\wsl.localhost\Ubuntu-20.04\home\<username>\.kiro\settings\mcp.json
```

```json
{
  "mcpServers": {
    "vpoMac": {
      "url": "http://192.168.1.29:8000/mcp",
      "headers": {
        "Authorization": "Bearer vporag-P<your-7-digit-ID>"
      }
    }
  }
}
```

Replace `P<your-7-digit-ID>` with your employee ID (e.g. `vporag-P1234567`). Tokens matching
`vporag-P<7digits>` are auto-registered on first use — no admin action required.

If the MCP server is unreachable, the agent automatically falls back to the local inline scripts
using the data files from step 3.

---

## What KiroTriageAgent.md does

A single self-contained rule that turns the Kiro agent into a VPO triage assistant:

- **Search behaviour** — MCP tools first (`search_kb`, `search_jira`); inline local scripts as fallback
- **Triage workflow** — term extraction, search, hypothesis, query tool selection (SPL / Kibana / DQL)
- **Response template** — hypothesis, queries, related docs, Jira tickets, mitigation paths, work note
- **Auto-learn protocol** — confirmation gate, synthesis format, MCP and local fallback paths
- **Inline local scripts** — KB search (full 8-phase PowerShell logic) and Jira search (Python/SQLite)
  written to `$env:TEMP` at runtime — no external `.ps1` or `.py` files needed

---

## Configurations to update per engineer

| Variable | What to set |
|----------|------------|
| `KB_DIR` | Path to your local `JSON/` directory (WSL or Windows path) |
| `JIRA_DB` | Path to your local `jira_local.db` SQLite file |
| `LEARN_DB` | Path to `chunks.learned.jsonl` — typically `<KB_DIR>\detail\chunks.learned.jsonl` |
| MCP Bearer token | `vporag-P<7digits>` in `mcp.json` — your employee ID |

The MCP server address (`http://192.168.1.29:8000`) only changes if the server moves.

---

## Keeping the rule up to date

| Source file | What it feeds into the rule |
|-------------|----------------------------|
| `.amazonq/rules/TriageAssistant.md` | Workflow, response template, learn protocol, hard rules |
| `.amazonq/rules/memory-bank/tech.md` | MCP server address, search level profiles, Jira schema |
| `Searches/Scripts/Search-DomainAware.ps1` | Inline KB search logic |
| `Searches/Scripts/query_local_db.py` | Inline Jira search logic |
