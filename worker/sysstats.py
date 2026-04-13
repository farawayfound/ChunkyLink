# -*- coding: utf-8 -*-
"""Worker-side system stats snapshot.

Mirrors backend/sysstats.py — kept as a separate file so the worker stays
a standalone process without any backend imports. If you change the
snapshot schema, update both modules in lockstep.
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
