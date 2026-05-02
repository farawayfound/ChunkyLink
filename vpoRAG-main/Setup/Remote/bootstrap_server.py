#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap a blank Ubuntu 24.04 server for vpoRAG MCP.
Run once as root (or a user with sudo) on the target machine:

    sudo python3 bootstrap_server.py [--mysql-pass <pass>] [--mysql-root-pass <pass>]

Assumes:
  - Ubuntu 24.04, Python 3.12+
  - Repo already cloned to /srv/vpo_rag  (git clone <repo> /srv/vpo_rag)
  - Internet access for apt/pip

Steps performed:
  1. Create vporag system user
  2. Create venv and install Python dependencies
  3. Create /etc/vporag/mcp.env with MYSQL_PASS
  4. Copy config.example.py -> config.py (AUTH_TOKENS dict lives here)
  5. Install systemd service (vporag-mcp)
  6. Install deploy wrapper + sudoers rule for vpomac
  7. Set up MySQL jira_db schema
  8. Enable and start the service
"""
import argparse, os, shutil, subprocess, sys, textwrap
from pathlib import Path

REPO_DIR    = Path("/srv/vpo_rag")
VENV        = REPO_DIR / "venv"
MCP_DIR     = REPO_DIR / "mcp_server"
ENV_DIR     = Path("/etc/vporag")
ENV_FILE    = ENV_DIR / "mcp.env"
SERVICE_SRC = MCP_DIR / "vporag-mcp.service"
SERVICE_DST = Path("/etc/systemd/system/vporag-mcp.service")
PYTHON      = VENV / "bin" / "python"


def run(cmd, **kwargs):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, **kwargs)
    if result.returncode != 0:
        sys.exit(f"FAILED (exit {result.returncode}): {cmd}")
    return result


def step(n, title):
    print(f"\n[{n}] {title}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-pass",      default="Jira007!!", help="MySQL jira_user password")
    parser.add_argument("--mysql-root-pass", default="",          help="MySQL root password (for schema setup)")
    parser.add_argument("--skip-mysql",      action="store_true", help="Skip MySQL schema setup")
    parser.add_argument("--skip-apt",        action="store_true", help="Skip apt package installation")
    args = parser.parse_args()

    if os.geteuid() != 0:
        sys.exit("Must run as root: sudo python3 bootstrap_server.py")

    if not REPO_DIR.exists():
        sys.exit(f"Repo not found at {REPO_DIR}. Clone it first:\n  git clone <repo_url> {REPO_DIR}")

    # ── 1. System packages ────────────────────────────────────────────────────
    step(1, "Installing system packages")
    if not args.skip_apt:
        run("apt-get update -qq")
        run("apt-get install -y -qq python3-venv python3-pip mysql-server libmysqlclient-dev")
    else:
        print("  Skipped (--skip-apt)")

    # ── 2. vporag system user ─────────────────────────────────────────────────
    step(2, "Creating vporag system user")
    r = subprocess.run("id vporag", shell=True, capture_output=True)
    if r.returncode != 0:
        run("useradd --system --no-create-home --shell /usr/sbin/nologin vporag")
    else:
        print("  vporag user already exists")
    run(f"chown -R vporag:vporag {REPO_DIR}")

    # ── 3. Python venv + dependencies ─────────────────────────────────────────
    step(3, "Creating venv and installing dependencies")
    if not VENV.exists():
        run(f"python3 -m venv {VENV}")
    run(f"{VENV}/bin/pip install -q --upgrade pip")
    run(f"{VENV}/bin/pip install -q -r {MCP_DIR}/requirements.txt")
    run(f"{VENV}/bin/pip install -q -r {REPO_DIR}/requirements.txt")

    # ── 4. /etc/vporag/mcp.env ────────────────────────────────────────────────
    step(4, "Writing /etc/vporag/mcp.env")
    ENV_DIR.mkdir(mode=0o750, exist_ok=True)
    env_content = textwrap.dedent(f"""\
        MYSQL_PASS={args.mysql_pass}
        PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring
    """)
    ENV_FILE.write_text(env_content)
    ENV_FILE.chmod(0o640)
    run(f"chown root:vporag {ENV_FILE}")
    print(f"  Written: {ENV_FILE}")

    # ── 5. config.py from example ─────────────────────────────────────────────
    step(5, "Installing mcp_server/config.py from config.example.py")
    config_dst = MCP_DIR / "config.py"
    if config_dst.exists():
        print("  config.py already exists — skipping (delete manually to reset)")
    else:
        shutil.copy(MCP_DIR / "config.example.py", config_dst)
        run(f"chown vporag:vporag {config_dst}")
        print(f"  Written: {config_dst}")

    # ── 6. systemd service ────────────────────────────────────────────────────
    step(6, "Installing systemd service")
    shutil.copy(SERVICE_SRC, SERVICE_DST)
    run("systemctl daemon-reload")
    run("systemctl enable vporag-mcp")
    print(f"  Installed: {SERVICE_DST}")

    # ── 7. Deploy wrapper + sudoers ───────────────────────────────────────────
    step(7, "Installing deploy wrapper and sudoers rule")
    run(f"python3 {REPO_DIR}/Setup/Remote/setup_deploy_sudo.py")

    # ── 8. MySQL schema ───────────────────────────────────────────────────────
    step(8, "Setting up MySQL jira_db schema")
    if args.skip_mysql:
        print("  Skipped (--skip-mysql)")
    else:
        sql_script = REPO_DIR / "mcp_server/scripts/setup_remote_mysql_schema.sql"
        if args.mysql_root_pass:
            run(f"mysql -u root -p{args.mysql_root_pass} < {sql_script}")
        else:
            print("  No --mysql-root-pass provided — attempting passwordless root login")
            run(f"mysql -u root < {sql_script}")
        # Set jira_user password
        run(f"mysql -u root {'-p'+args.mysql_root_pass if args.mysql_root_pass else ''} "
            f"-e \"ALTER USER 'jira_user'@'localhost' IDENTIFIED BY '{args.mysql_pass}'; FLUSH PRIVILEGES;\"")
        print(f"  jira_user password set")

    # ── 9. Start service ──────────────────────────────────────────────────────
    step(9, "Starting vporag-mcp service")
    run("systemctl start vporag-mcp")
    run("systemctl status vporag-mcp --no-pager -l")

    print("\n=== Bootstrap complete ===")
    print("Next steps:")
    print("  1. Drop Jira CSV exports into /srv/samba/share/dpstriageCSV/ and /srv/samba/share/postrcaCSV/")
    print("  2. Run the indexer: sudo vporag-deploy  (or trigger via build_index MCP tool)")
    print("  3. From Windows: run Setup\\Deploy-MCPServer.ps1 for future code deploys")
    print(f"  4. MCP endpoint: http://<server-ip>:8000/mcp")


if __name__ == "__main__":
    main()
