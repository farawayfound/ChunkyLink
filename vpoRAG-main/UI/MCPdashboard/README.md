# MCP Dashboard

Observability dashboard for the vpoRAG MCP server. Displays usage trends, event logs, and errors sourced from `mcp_access.log`.

## Access

| Mode | URL | When to use |
|---|---|---|
| **Server (always-on)** | `http://192.168.1.29:5001` | Any machine on the MCP server LAN — no local setup required |
| **Local (Windows)** | `http://localhost:5001` | Off-LAN access or local development |

The server deployment runs as a persistent systemd service (`vporag-dashboard`) and starts automatically on boot.

## Local Launch (Windows)

```
UI/MCPdashboard/RUN_DASHBOARD.bat
```

Requires `~/.ssh/vporag_key` with owner-only ACL (`CHTR\P3315113:(F)` only — no `BUILTIN\Administrators`, no `SYSTEM`). The local mode reads the log file from the server via SSH.

## Architecture

```
UI/MCPdashboard/
├── base/
│   ├── log_reader.py      # Abstract LogReader — fetch_lines(), check_server_status()
│   └── app_factory.py     # create_app(reader) — all Flask routes (single implementation)
├── local/
│   ├── log_reader.py      # SshLogReader(LogReader) — fetches log via SSH subprocess
│   └── run.py             # Windows entry point → localhost:5001
├── remote/
│   ├── log_reader.py      # LocalLogReader(LogReader) — reads log file directly from disk
│   ├── run.py             # Server entry point → 0.0.0.0:5001
│   └── vporag-dashboard.service
├── templates/index.html   # Shared UI (used by both modes)
└── static/app.js, style.css
```

All Flask routes live once in `base/app_factory.py`. The only difference between local and server deployments is which `LogReader` implementation is injected — `SshLogReader` on Windows, `LocalLogReader` on the server.

## Dashboard Features

- **KPI bar**: total calls, KB searches, Jira searches, index builds, errors, avg chunks returned
- **Overview tab**: calls-per-day line chart (per tool + total), tool distribution doughnut, search level distribution, Jira source breakdown, avg duration per tool, calls by client/user
- **Event Log tab**: paginated event table with column filters (event type multi-select, user, terms/details); `request_start` and `request_end` unchecked by default
- **Errors tab**: `tool_error` events with type, message, user, terms, and duration

## Updating the Server Deployment

After modifying any dashboard file locally, deploy via `Setup\Deploy-ToMCP.bat` — **never use raw scp/ssh commands**:

```
# Deploy specific files (most common — deploy only what changed)
Setup\Deploy-ToMCP.bat UI/MCPdashboard/templates/index.html UI/MCPdashboard/static/app.js

# Deploy all dashboard files
Setup\Deploy-ToMCP.bat UI/MCPdashboard/templates/index.html UI/MCPdashboard/static/app.js UI/MCPdashboard/static/style.css UI/MCPdashboard/base/app_factory.py

# Restart services only (no file upload)
Setup\Deploy-ToMCP.bat
```

The deploy script handles SCP, mv, chown, and service restart automatically. Both `vporag-mcp` and `vporag-dashboard` are restarted on every deploy.

**From executeBash (preferred — avoids cmd.exe argument parsing issues):**
```
powershell -ExecutionPolicy Bypass -Command "& 'Setup\Deploy-ToMCP.ps1' -Files @('UI/MCPdashboard/templates/index.html','UI/MCPdashboard/static/app.js') -RestartService"
```

**If the deploy hangs:** retry the identical command once — transient SSH hangs are normal.

**After restart:** the MCP session token becomes invalid — expect a `Session not found` error on the first MCP tool call; retry once.

## Server Service Management

```bash
# Check status
systemctl status vporag-dashboard

# Restart
sudo systemctl restart vporag-dashboard

# View logs
journalctl -u vporag-dashboard -n 50 --no-pager
```

Service file: `/etc/systemd/system/vporag-dashboard.service`  
Source: `UI/MCPdashboard/remote/vporag-dashboard.service`

## Dependencies

- Flask 3.0.0 — installed in `/srv/vpo_rag/venv/` on the server
- No additional dependencies for the server deployment
- Windows local mode requires SSH access via `vporag_key`
