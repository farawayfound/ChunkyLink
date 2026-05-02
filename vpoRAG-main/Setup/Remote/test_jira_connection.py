#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test MySQL jira_db connection from server environment."""
import os, sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Searches" / "Connectors"))
sys.path.insert(0, str(_repo / "Searches"))

print(f"MYSQL_USER: {os.environ.get('MYSQL_USER', 'NOT SET')}")
print(f"MYSQL_PASS set: {bool(os.environ.get('MYSQL_PASS'))} (len={len(os.environ.get('MYSQL_PASS',''))})")
print(f"MYSQL_DB: {os.environ.get('MYSQL_DB', 'NOT SET')}")

import jira_query

print("\nTesting count query for 'playback'...")
try:
    r = jira_query.query_jira_mysql(["playback"], mode="count")
    print(f"  count result: {r}")
except Exception as ex:
    print(f"  FAILED: {ex}"); sys.exit(1)

print("\nTesting top query for 'playback' (limit 3)...")
try:
    r = jira_query.query_jira_mysql(["playback"], mode="top", limit=3)
    print(f"  dpstriage hits: {len(r['dpstriage'])}, postrca hits: {len(r['postrca'])}")
    if r["dpstriage"]:
        print(f"  sample: {r['dpstriage'][0]['Key']} — {r['dpstriage'][0]['Summary'][:60]}")
except Exception as ex:
    print(f"  FAILED: {ex}"); sys.exit(1)

print("\nAll tests passed.")
