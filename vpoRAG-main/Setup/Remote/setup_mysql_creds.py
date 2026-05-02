#!/usr/bin/env python3
"""Reset jira_user MySQL password and add MYSQL_* vars to /etc/vporag/mcp.env."""
import getpass, subprocess, sys
NEW_PASS = getpass.getpass("New MySQL jira_user password: ")
if not NEW_PASS:
    sys.exit("Password cannot be empty")

# Reset the MySQL password via root (auth_socket — no password needed with sudo)
result = subprocess.run(
    ["mysql", "-e",
     f"ALTER USER 'jira_user'@'localhost' IDENTIFIED BY '{NEW_PASS}'; FLUSH PRIVILEGES;"],
    capture_output=True, text=True
)
if result.returncode != 0:
    sys.exit(f"MySQL error: {result.stderr}")
print(f"MySQL jira_user password reset (length: {len(NEW_PASS)})")

# Append MySQL vars to /etc/vporag/mcp.env
env_path = "/etc/vporag/mcp.env"
with open(env_path, "r") as f:
    content = f.read()

# Remove any existing MYSQL_ lines then append fresh ones
lines = [l for l in content.splitlines() if not l.startswith("MYSQL_")]
lines += [
    f"MYSQL_HOST=localhost",
    f"MYSQL_PORT=3306",
    f"MYSQL_DB=jira_db",
    f"MYSQL_USER=jira_user",
    f"MYSQL_PASS={NEW_PASS}",
]
with open(env_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print("Updated /etc/vporag/mcp.env with MYSQL_* vars")
