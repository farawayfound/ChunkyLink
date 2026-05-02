#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Install the vporag-deploy wrapper and passwordless sudo rule for vpomac.
Run once on the server as root:
    sudo python3 /srv/vpo_rag/Setup/Remote/setup_deploy_sudo.py
"""
import subprocess, sys, os, stat
from pathlib import Path

WRAPPER_SRC  = Path(__file__).parent / "vporag-deploy.sh"
WRAPPER_DEST = Path("/usr/local/bin/vporag-deploy")
SUDOERS_FILE = Path("/etc/sudoers.d/vpomac-deploy")
SUDOERS_RULE = "vpomac ALL=(ALL) NOPASSWD: /usr/local/bin/vporag-deploy\n"

# Install wrapper
WRAPPER_DEST.write_text(WRAPPER_SRC.read_text())
WRAPPER_DEST.chmod(0o755)
os.chown(WRAPPER_DEST, 0, 0)  # root:root
print(f"OK: {WRAPPER_DEST} installed")

# Install sudoers rule
SUDOERS_FILE.write_text(SUDOERS_RULE)
SUDOERS_FILE.chmod(0o440)

result = subprocess.run(["visudo", "-c", "-f", str(SUDOERS_FILE)], capture_output=True, text=True)
if result.returncode != 0:
    print(f"ERROR: sudoers syntax check failed:\n{result.stderr}")
    SUDOERS_FILE.unlink()
    sys.exit(1)

print(f"OK: {SUDOERS_FILE} installed and validated")
print("vpomac can now run 'sudo vporag-deploy' without a password.")
