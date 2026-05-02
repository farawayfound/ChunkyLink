# vpoRAG MCP Server — Ansible Deployment

Automates the full server setup from `MCP-Server-Plan.md` Phases 1–4, eliminating every
manual hiccup encountered in the original installation session.

## Prerequisites (Windows, one-time)

1. Run the SSH key setup script — enters the password **once**, never again:
   ```powershell
   powershell -File Ansible\MCP\setup_ssh_key.ps1
   ```

2. Install Ansible on the **server** (the playbook runs locally on the server via localhost):
   ```bash
   ssh -i ~/.ssh/vporag_key vpomac@192.168.1.29
   sudo apt-get install -y ansible
   ```

3. Copy and fill in secrets:
   ```
   copy Ansible\MCP\secrets.yml.example Ansible\MCP\secrets.yml
   # edit secrets.yml with real values, then encrypt:
   ansible-vault encrypt Ansible\MCP\secrets.yml
   ```

## Run (from the server, targeting localhost)

```bash
# Copy playbook to server
scp -i ~/.ssh/vporag_key -r Ansible/MCP vpomac@192.168.1.29:/tmp/mcp_ansible
scp -i ~/.ssh/vporag_key -r mcp_server   vpomac@192.168.1.29:/tmp/mcp_ansible/mcp_server
scp -i ~/.ssh/vporag_key -r indexers     vpomac@192.168.1.29:/tmp/mcp_ansible/indexers
scp -i ~/.ssh/vporag_key -r Searches/Connectors vpomac@192.168.1.29:/tmp/mcp_ansible/Searches/Connectors

# SSH in and run
ssh -i ~/.ssh/vporag_key vpomac@192.168.1.29
cd /tmp/mcp_ansible
ansible-playbook -i inventory.ini site.yml --ask-vault-pass -e @secrets.yml
```

The playbook is fully **idempotent** — safe to re-run after any change.

## What Each Role Does

| Role | Responsibility |
|---|---|
| `base` | apt packages (git, curl, tesseract, libgl1, libglib2), `vporag` service user, `/srv/vpo_rag` at 755 |
| `odbc` | Microsoft GPG key (no-TTY), apt repo, `msodbcsql18` (only version on Ubuntu 24.04) |
| `directories` | Full data/output directory tree owned by `vporag` |
| `python_env` | venv created **as vporag**, all requirements, spaCy 3.8 + model, renders `indexers/config.py` |
| `mysql` | Installs MySQL server, creates `vporag_jira` DB + `vporag` user, applies schema (idempotent) |
| `systemd` | `vporag-mcp.service` unit with Jira creds as env vars, enable + start |
| `deploy` | Syncs `mcp_server/` app files, renders `mcp_server/config.py` from template, syncs `indexers/` and `Searches/Connectors/` |

## What Gets Rendered from Templates

| Template | Destination | Why template, not copy |
|---|---|---|
| `python_env/templates/indexer_config.py.j2` | `/srv/vpo_rag/indexers/config.py` | Linux paths, OCR worker count |
| `deploy/templates/mcp_config.py.j2` | `/srv/vpo_rag/mcp_server/config.py` | Paths, secrets, Jira SQL settings |
| `systemd/templates/vporag-mcp.service.j2` | `/etc/systemd/system/vporag-mcp.service` | Jira creds as env vars |

## Key Variables (`group_vars/mcp_server.yml`)

| Variable | Default | Notes |
|---|---|---|
| `srv_dir` | `/srv/vpo_rag` | Root of all server paths |
| `odbc_package` | `msodbcsql18` | Only version available on Ubuntu 24.04 |
| `odbc_driver_name` | `ODBC Driver 18 for SQL Server` | Must match `Searches/config.py` |
| `spacy_version` | `3.8.4` | 3.7.x incompatible with Python 3.12 |
| `indexer_ocr_workers` | `8` | Half of Xeon's 16 cores |
| `mysql_db` | `vporag_jira` | Remote MySQL database name (on MCP server) |
| `mysql_user` | `vporag` | MySQL user (password via secrets.yml) |
| `jira_primary_source` | `mysql` | `mysql` (local, always reachable) \| `sql` (Charter VPN required) \| `csv` |
| `jira_search_both_sources` | `false` | Merge primary + CSV results |
| `jira_sql_server` | `VM0PWVPTSPL000` | Override in secrets.yml if different |
| `mcp_auth_token` | `changeme` | **Always override via secrets.yml** |
| `mcp_max_results` | `5` | Max chunks per search_kb call (Amazon Q 100K output limit) |

## Secrets (`secrets.yml`, never committed)

```yaml
sudo_password: "vpomac007"
mcp_auth_token: "replace-with-real-token"
jira_user: "replace-with-jira-username"
jira_pass: "replace-with-jira-password"
mysql_pass: "replace-with-mysql-password"
```

> **Charter VPN note:** `jira_primary_source` defaults to `mysql` (local DB, always reachable).
> To use the live Jira SQL server (`VM0PWVPTSPL000`), connect to Charter VPN first and override:
> `ansible-playbook ... -e jira_primary_source=sql`

## Hiccups Eliminated

| Chat hiccup | How the playbook fixes it |
|---|---|
| SSH hung 20+ min on password prompt | `setup_ssh_key.ps1` sets up key auth first |
| `%USERPROFILE%` not expanding in PowerShell | `setup_ssh_key.ps1` uses `$env:USERPROFILE` |
| `sudo` needing TTY for password | Ansible `become` passes password via `ansible_become_pass` |
| `gpg` failing on `/dev/tty` | `odbc` role uses `--batch --no-tty` flags |
| `msodbcsql17` not available on Ubuntu 24.04 | `odbc_package: msodbcsql18` in `group_vars` |
| venv owned by `vporag`, pip run as `vpomac` | All venv tasks use `become_user: vporag` |
| spaCy 3.7.2 ABI mismatch with Python 3.12 | `requirements.server.txt` pins `spacy>=3.8.0,<3.9.0` |
| Linux keyring/D-Bus unavailable headless | Jira creds injected as systemd `Environment=` vars |
| `chmod 777` on `/srv/vpo_rag` caused deletion | All directory tasks use mode `0755` |
| `mcp_server/config.py` had hardcoded local paths | Rendered from `mcp_config.py.j2` template |
| `indexers/` and `Searches/Connectors/` not deployed | `deploy` role syncs both |
| `FastMCP.run()` rejected `host`/`port` kwargs | `host`/`port` passed to `FastMCP()` constructor |
| Duplicate tool name warnings (`run`) | Each tool registered with explicit `name=` parameter |
| `streamable-http` transport serves on `/mcp` endpoint | `server.py` uses `streamable-http` transport; VS Code `mcp.json` `serverUrl` points to `/mcp` |
| `amazonQ.mcp.servers` in `settings.json` has no effect | Amazon Q reads `%APPDATA%\Code\User\mcp.json` with `mcpServers` key, not `settings.json` |
| Amazon Q MCP tool output exceeds 100K char limit | `search_kb` strips heavy fields and caps results at `MCP_MAX_RESULTS = 5` |
| `PARALLEL_OCR_WORKERS = 4` undersized for Xeon | `indexer_ocr_workers: 8` in `group_vars` |

## After Deployment — VS Code MCP Registration

Amazon Q reads MCP config from `%APPDATA%\Code\User\mcp.json` (NOT `settings.json`).
Add this once on each engineer's machine via the Amazon Q chat panel:

1. Open Amazon Q chat panel -> click **+** (Add MCP Server)
2. Fill in: Name=`vpoRAG`, Scope=`Global`, Transport=`http`, URL=`http://192.168.1.29:8000/mcp`, Timeout=`0`
3. Restart VS Code

Or manually create/edit `%APPDATA%\Code\User\mcp.json`:
```json
{
    "mcpServers": {
        "vpoRAG": {
            "serverUrl": "http://192.168.1.29:8000/mcp"
        }
    }
}
```

Verify: `python mcp_server/scripts/test_mcp.py` — expected `10 passed, 0 failed`.

## After Deployment — Load Source Documents and Build Index

Source documents are not in git and must be copied manually:
```powershell
# From Windows — copy source docs to server
scp -i $env:USERPROFILE\.ssh\vporag_key -r "C:\path\to\source_docs\*" vpomac@192.168.1.29:/tmp/source_docs/
ssh -i $env:USERPROFILE\.ssh\vporag_key vpomac@192.168.1.29 "sudo -u vporag cp -r /tmp/source_docs/* /srv/vpo_rag/source_docs/"
```

Then trigger a build via the MCP `build_index` tool or directly:
```bash
ssh -i ~/.ssh/vporag_key vpomac@192.168.1.29
sudo -u vporag /srv/vpo_rag/mcp_server/scripts/run_build.sh
```
