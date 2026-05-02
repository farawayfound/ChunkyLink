# -*- coding: utf-8 -*-
"""
MCP stdio-to-HTTP proxy — bridges Amazon Q's stdio transport to the vpoRAG HTTP server.
Amazon Q launches this process; it forwards all JSON-RPC messages to the remote server.
"""
import sys, json, threading, uuid
import requests

SERVER_URL = "http://192.168.1.29:8000/mcp"
TIMEOUT    = 30

session_id  = None
session_lock = threading.Lock()

def _headers(extra=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        h["mcp-session-id"] = session_id
    if extra:
        h.update(extra)
    return h

def _parse_sse(text):
    """Extract the first data: line from an SSE response."""
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return None

def _send(msg):
    global session_id
    try:
        r = requests.post(SERVER_URL, json=msg, headers=_headers(), timeout=TIMEOUT)
        # Capture session id from initialize response
        if not session_id and "mcp-session-id" in r.headers:
            with session_lock:
                session_id = r.headers["mcp-session-id"]
        ct = r.headers.get("Content-Type", "")
        if "text/event-stream" in ct:
            result = _parse_sse(r.text)
        else:
            result = r.json() if r.text.strip() else None
        return result
    except Exception as e:
        return {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}

def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        result = _send(msg)
        if result is not None:
            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
