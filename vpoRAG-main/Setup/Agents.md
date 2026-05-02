# Setup — AI Agent Context

## Structure

### (root)
Scripts run from the project root on the developer's local machine:
- `sync_local_db.py` — pull Jira ticket data from remote MySQL (MCP server) into local SQLite mirror (`Searches/jira_local.db`). Run: `python Setup/sync_local_db.py`
- `Sync-JSONIndex.ps1` — sync the 7 category JSONL files from the MCP server to local `JSON/detail/`. Run: `powershell -Command "& 'Setup\Sync-JSONIndex.ps1'"`
- `Deploy-MCPServer.ps1` — deploy updated MCP tool files to the server and restart the service. Reads sudo password from Windows Credential Manager (`cmdkey /add:vporag_deploy /user:vpomac /pass:<password>`). Run: `powershell -File Setup\Deploy-MCPServer.ps1`

### Local/
Scripts run on the developer's local machine:
- `check_deps.py` — verify all requirements.txt packages are installed. Run: `python Setup/Local/check_deps.py`
- `setup_local.py` — create `.venv`, install requirements, download spaCy model, render `indexers/config.py` and `Searches/config.ps1`. Run: `python Setup/Local/setup_local.py`

### Remote/
Scripts run on the Linux MCP server (`/srv/vpo_rag/`):
- `bootstrap_server.py` — **full server setup from scratch** (see below). Run once as root on a blank machine.
- `setup_deploy_sudo.py` — install `vporag-deploy` wrapper + passwordless sudoers rule for vpomac. Called automatically by `bootstrap_server.py`.
- `vporag-deploy.sh` — server-side deploy wrapper invoked via `sudo vporag-deploy <args>`. Installed to `/usr/local/bin/vporag-deploy` by `setup_deploy_sudo.py`.
- `write_service_file.py` — generate systemd service + env file from keyring credentials (legacy — superseded by `bootstrap_server.py`).
- `fix_env_file.py` — rewrite `/etc/vporag/mcp.env` with safely-quoted JIRA_PASS.
- `setup_mysql_creds.py` — reset MySQL jira_user password and update mcp.env.
- `test_jira_connection.py` — validate MySQL jira_db connection from server environment.

### Unimplemented/
Placeholder code only. Not functional, tested, or maintained.
- `chat_rag.py` — Qdrant + Ollama vector DB chat (placeholder)
- `create_collections.py` — Qdrant collection setup (placeholder)
- `ingest_json.py` — JSONL ingestion into Qdrant (placeholder)

vpoRAG uses Amazon Q's native context via local PowerShell searches — no vector DB required.
See `../JSON/Agents.md` for the actual search workflow.

---

## Bootstrapping a New Server

### Prerequisites
- Ubuntu 24.04, Python 3.12+
- Repo cloned to `/srv/vpo_rag`: `git clone <repo_url> /srv/vpo_rag`
- Internet access for apt/pip

### One-command bootstrap
```bash
sudo python3 /srv/vpo_rag/Setup/Remote/bootstrap_server.py \
    --mysql-pass <jira_user_password> \
    --mysql-root-pass <mysql_root_password>
```

### What it does (in order)
1. Installs system packages (python3-venv, mysql-server)
2. Creates `vporag` system user, sets ownership of `/srv/vpo_rag`
3. Creates venv at `/srv/vpo_rag/venv`, installs all Python dependencies
4. Writes `/etc/vporag/mcp.env` with `MYSQL_PASS` only (auth tokens live in `config.py`)
5. Copies `mcp_server/config.example.py` → `mcp_server/config.py` (skips if exists)
6. Installs and enables `vporag-mcp` systemd service
7. Installs `vporag-deploy` wrapper + passwordless sudoers rule for vpomac
8. Runs MySQL schema setup (`mcp_server/scripts/setup_remote_mysql_schema.sql`)
9. Starts the service

### After bootstrap
- Store vpomac sudo password in Windows Credential Manager: `cmdkey /add:vporag_deploy /user:vpomac /pass:<password>`
- Future code deploys: `powershell -File Setup\Deploy-MCPServer.ps1`
- Drop Jira CSV exports into Samba shares to populate the ticket database
- Trigger index build via the `build_index` MCP tool or `sudo vporag-deploy`

### What is NOT in the repo (must be provided at bootstrap time)
| Secret | Where it goes | How to set |
|--------|--------------|------------|
| MySQL jira_user password | `/etc/vporag/mcp.env` → `MYSQL_PASS` | `--mysql-pass` arg |
| MySQL root password | Used once for schema setup only | `--mysql-root-pass` arg |
| Per-user auth tokens | `mcp_server/config.py` → `AUTH_TOKENS` dict | Edit `config.py` after bootstrap; tokens matching `vporag-P<7digits>` auto-register on first use |
| vpomac sudo password | Windows Credential Manager `vporag_deploy` | `cmdkey /add:vporag_deploy ...` |
