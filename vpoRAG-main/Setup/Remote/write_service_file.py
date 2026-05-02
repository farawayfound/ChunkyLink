import keyring, sys

u = keyring.get_password("vpoRAG_Jira", "username")
p = keyring.get_password("vpoRAG_Jira", "password")

if not u or not p:
    sys.exit("Credentials not found in keyring")

# systemd EnvironmentFile format: KEY=VALUE, no quoting needed, # escapes not required
# Values are taken literally up to end of line — safe for any password content
env_file = f"JIRA_USER={u}\nJIRA_PASS={p}\nMCP_AUTH_TOKEN=changeme\nPYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring\n"

with open("vporag-mcp.env.tmp", "w", newline="\n") as f:
    f.write(env_file)

# Service file references /etc/vporag/mcp.env — no credentials inline
svc = """\
[Unit]
Description=vpoRAG MCP Server
After=network.target

[Service]
User=vporag
WorkingDirectory=/srv/vpo_rag/mcp_server
ExecStart=/srv/vpo_rag/venv/bin/python server.py
Restart=on-failure
RestartSec=5

# Credentials and settings loaded from EnvironmentFile — safe for special characters
EnvironmentFile=/etc/vporag/mcp.env

[Install]
WantedBy=multi-user.target
"""

with open("vporag-mcp.service.tmp", "w", newline="\n") as f:
    f.write(svc)

print(f"Written — user={u} pass_len={len(p)}")
