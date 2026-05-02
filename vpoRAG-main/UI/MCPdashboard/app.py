# -*- coding: utf-8 -*-
"""MCP Dashboard — web UI for viewing MCP server access logs and usage trends."""
from flask import Flask, render_template, jsonify, request
import json, os, subprocess, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'vporag-mcp-dash')

# ── Config ────────────────────────────────────────────────────────────────────
_REPO_ROOT   = Path(__file__).parent.parent.parent
_SSH_KEY     = str(Path.home() / '.ssh' / 'vporag_key')
_SSH_HOST    = 'vpomac@192.168.1.29'
_REMOTE_LOG  = '/srv/vpo_rag/JSON/logs/mcp_access.log'
_SSH_OPTS    = ['-i', _SSH_KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2']
_MAX_LINES   = int(os.environ.get('MCP_DASH_MAX_LINES', '5000'))


def _fetch_log_lines(max_lines: int = _MAX_LINES) -> list[str]:
    """Pull the last N lines of mcp_access.log from the server via SSH."""
    cmd = ['ssh'] + _SSH_OPTS + [_SSH_HOST,
           f'tail -n {max_lines} {_REMOTE_LOG} 2>/dev/null || echo ""']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return [l for l in result.stdout.splitlines() if l.strip()]


def _parse_events(lines: list[str]) -> list[dict]:
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/events')
def get_events():
    """Return raw events with optional filtering."""
    limit    = int(request.args.get('limit', 200))
    event    = request.args.getlist('event')      # filter by event type (multi)
    client   = request.args.get('client', '')      # filter by client_ip
    since    = request.args.get('since', '')       # ISO timestamp lower bound

    try:
        lines  = _fetch_log_lines()
        events = _parse_events(lines)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if event:
        events = [e for e in events if e.get('event') in event]
    if client:
        events = [e for e in events if
                  client.lower() in (e.get('client_ip') or '').lower() or
                  client.lower() in (e.get('user_id') or '').lower()]
    if since:
        events = [e for e in events if e.get('timestamp', '') >= since]

    # Most recent first
    events.sort(key=lambda e: e.get('timestamp', ''), reverse=True)
    return jsonify({'events': events[:limit], 'total': len(events)})


@app.route('/api/stats')
def get_stats():
    """Aggregate statistics for the dashboard overview."""
    try:
        lines  = _fetch_log_lines()
        events = _parse_events(lines)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    tool_events = [e for e in events if e.get('event') in ('search_kb', 'search_jira', 'build_index')]
    errors      = [e for e in events if e.get('event') == 'tool_error']

    # Calls per tool
    calls_by_tool: dict[str, int] = defaultdict(int)
    for e in tool_events:
        calls_by_tool[e['event']] += 1

    # Calls per client IP + user_id
    calls_by_client: dict[str, int] = defaultdict(int)
    for e in tool_events:
        ip = e.get('client_ip', 'unknown')
        uid = e.get('user_id', '')
        label = f"{uid} ({ip})" if uid and uid != 'anonymous' else ip
        calls_by_client[label] += 1

    # Avg duration per tool
    durations: dict[str, list[int]] = defaultdict(list)
    for e in tool_events:
        if 'duration_ms' in e:
            durations[e['event']].append(e['duration_ms'])
    avg_duration = {t: round(sum(v) / len(v)) for t, v in durations.items() if v}

    # Calls per day (last 30 days) — total and per tool
    calls_by_day: dict[str, int] = defaultdict(int)
    calls_by_day_by_tool: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in tool_events:
        ts = e.get('timestamp', '')
        if ts:
            calls_by_day[ts[:10]] += 1
            calls_by_day_by_tool[e['event']][ts[:10]] += 1

    # search_kb level distribution
    level_dist: dict[str, int] = defaultdict(int)
    for e in events:
        if e.get('event') == 'search_kb' and 'level' in e:
            level_dist[e['level']] += 1

    # search_kb avg chunks returned
    kb_chunks = [e.get('chunks_returned', 0) for e in events if e.get('event') == 'search_kb']
    avg_chunks = round(sum(kb_chunks) / len(kb_chunks), 1) if kb_chunks else 0

    # search_jira source distribution
    jira_sources: dict[str, int] = defaultdict(int)
    for e in events:
        if e.get('event') == 'search_jira' and 'source' in e:
            jira_sources[e['source']] += 1

    # Most recent activity
    last_event = max(tool_events, key=lambda e: e.get('timestamp', ''), default=None)

    return jsonify({
        'total_calls':     len(tool_events),
        'total_errors':    len(errors),
        'calls_by_tool':   dict(calls_by_tool),
        'calls_by_client': dict(calls_by_client),
        'avg_duration_ms': avg_duration,
        'calls_by_day':    dict(sorted(calls_by_day.items())),
        'calls_by_day_by_tool': {t: dict(sorted(v.items())) for t, v in calls_by_day_by_tool.items()},
        'level_dist':      dict(level_dist),
        'avg_chunks':      avg_chunks,
        'jira_sources':    dict(jira_sources),
        'last_activity':   last_event.get('timestamp') if last_event else None,
        'log_lines_read':  len(lines),
    })


@app.route('/api/errors')
def get_errors():
    """Return tool_error events."""
    try:
        lines  = _fetch_log_lines()
        events = _parse_events(lines)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    errors = [e for e in events if e.get('event') == 'tool_error']
    errors.sort(key=lambda e: e.get('timestamp', ''), reverse=True)
    return jsonify({'errors': errors[:200], 'total': len(errors)})


@app.route('/api/server-status')
def server_status():
    """Check if the MCP server process is active via systemctl."""
    try:
        cmd = ['ssh'] + _SSH_OPTS + [_SSH_HOST, 'systemctl is-active vporag-mcp']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        active = result.stdout.strip() == 'active'
        return jsonify({'active': active, 'status': result.stdout.strip()})
    except Exception as e:
        return jsonify({'active': False, 'status': 'unreachable', 'error': str(e)})


if __name__ == '__main__':
    print("=" * 60)
    print("vpoRAG MCP Dashboard")
    print("=" * 60)
    print(f"MCP Host:  {_SSH_HOST}")
    print(f"Log file:  {_REMOTE_LOG}")
    print(f"\nStarting server at http://localhost:5001")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5001, debug=True)
