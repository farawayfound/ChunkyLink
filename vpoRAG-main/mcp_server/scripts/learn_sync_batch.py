# -*- coding: utf-8 -*-
"""
learn_sync_batch.py — server-side batch runner for Sync-LearnedChunks.ps1.

Reads a JSONL file of locally-learned chunks, runs each through the
LearnEngine pipeline (full Gate 1 + Gate 2 + merge), and prints a JSON
array of per-chunk results to stdout.

Usage (run as vporag):
    /srv/vpo_rag/venv/bin/python /tmp/learn_sync_batch.py /tmp/sync_batch.jsonl
"""
import json, sys
from pathlib import Path

sys.path.insert(0, "/srv/vpo_rag/mcp_server")
sys.path.insert(0, "/srv/vpo_rag/indexers")

from tools.learn_local import LocalLearnEngine

_engine = LocalLearnEngine()
_batch_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None

if not _batch_file or not _batch_file.exists():
    print(json.dumps({"error": f"batch file not found: {_batch_file}"}))
    sys.exit(1)

results = []
with open(_batch_file, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        try:
            chunk = json.loads(line)
        except Exception as e:
            results.append({"status": "error", "reason": f"malformed JSON: {e}"})
            continue

        text       = chunk.get("text_raw") or chunk.get("text", "")
        ticket_key = chunk.get("metadata", {}).get("ticket_key", "")
        category   = (chunk.get("tags") or ["auto"])[0]
        tags       = chunk.get("tags", [])
        title      = chunk.get("metadata", {}).get("title", "")
        user_id    = chunk.get("metadata", {}).get("user_id", "sync")
        local_id   = chunk.get("id", "")

        result = _engine.process(text, ticket_key, category, tags, title, user_id)
        result["local_id"] = local_id
        results.append(result)

print(json.dumps(results, ensure_ascii=False))
