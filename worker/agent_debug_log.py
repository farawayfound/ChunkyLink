# -*- coding: utf-8 -*-
"""Session NDJSON logger for debug mode (repo root: debug-de7fc2.log)."""
from __future__ import annotations

import json
import os
import time

_here = os.path.dirname(os.path.abspath(__file__))
_repo = os.path.abspath(os.path.join(_here, ".."))
# Full checkout: worker/ sits next to backend/. Docker image: only /app (worker files).
_ROOT = _repo if os.path.isdir(os.path.join(_repo, "backend")) else _here
_LOG_PATH = os.path.join(_ROOT, "debug-de7fc2.log")
_SESSION = "de7fc2"


def agent_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    run_id: str = "pre-fix",
) -> None:
    line = {
        "sessionId": _SESSION,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass
