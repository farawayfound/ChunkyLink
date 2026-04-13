# -*- coding: utf-8 -*-
"""System resource snapshot for the admin dashboard.

Shared between the backend (macmini local stats) and the worker (nanobot
stats published to Redis). Keeping the snapshot format in one module ensures
both sides stay in sync.
"""
from __future__ import annotations

import platform
import socket
import time
from typing import Any

import psutil


_BOOT_TIME = psutil.boot_time()


def _safe_load_avg() -> list[float] | None:
    try:
        return list(psutil.getloadavg())
    except (AttributeError, OSError):
        return None


def _top_processes(limit: int = 10) -> list[dict[str, Any]]:
    """Return the top N processes by CPU percent.

    psutil.cpu_percent() returns 0.0 on the first call per process, so we
    prime it, sleep briefly, then read again. This is the cheapest way to
    get meaningful per-process CPU numbers.
    """
    procs = list(psutil.process_iter(["pid", "name", "username"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.2)

    rows: list[dict[str, Any]] = []
    ncpu = psutil.cpu_count(logical=True) or 1
    for p in procs:
        try:
            cpu = p.cpu_percent(None) / ncpu
            mem = p.memory_percent()
            rows.append({
                "pid": p.pid,
                "name": p.info.get("name") or "",
                "user": p.info.get("username") or "",
                "cpu": round(cpu, 1),
                "mem": round(mem, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    rows.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
    return rows[:limit]


def snapshot(disk_path: str = "/", top_n: int = 10) -> dict[str, Any]:
    """Return a resource snapshot suitable for JSON serialization."""
    vm = psutil.virtual_memory()
    try:
        du = psutil.disk_usage(disk_path)
    except OSError:
        du = psutil.disk_usage("/")

    return {
        "host": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "timestamp": time.time(),
        "uptime_sec": int(time.time() - _BOOT_TIME),
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.2),
            "per_core": psutil.cpu_percent(interval=None, percpu=True),
            "count": psutil.cpu_count(logical=True) or 0,
            "load_avg": _safe_load_avg(),
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        },
        "disk": {
            "path": disk_path,
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
        },
        "processes": _top_processes(top_n),
    }
