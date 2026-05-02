#!/bin/bash
# /usr/local/bin/vporag-deploy
# Owned by root, executable by vpomac via passwordless sudo.
# Copies staged tool files from /tmp and restarts vporag-mcp.
# Usage: sudo vporag-deploy [search_kb] [search_jira] [server] [config_max_results=N] [kill_builds]

set -e
TOOLS_DIR="/srv/vpo_rag/mcp_server/tools"
MCP_DIR="/srv/vpo_rag/mcp_server"
OWNER="vporag:vporag"

deployed=0

for arg in "$@"; do
    case "$arg" in
        search_kb)
            cp /tmp/search_kb.py "$TOOLS_DIR/search_kb.py"
            chown "$OWNER" "$TOOLS_DIR/search_kb.py"
            echo "OK: search_kb.py deployed"
            deployed=1
            ;;
        search_jira)
            cp /tmp/search_jira.py "$TOOLS_DIR/search_jira.py"
            chown "$OWNER" "$TOOLS_DIR/search_jira.py"
            echo "OK: search_jira.py deployed"
            deployed=1
            ;;
        server)
            cp /tmp/server.py "$MCP_DIR/server.py"
            chown "$OWNER" "$MCP_DIR/server.py"
            echo "OK: server.py deployed"
            deployed=1
            ;;
        config_max_results=*)
            val="${arg#config_max_results=}"
            if grep -q '^MCP_MAX_RESULTS' "$MCP_DIR/config.py"; then
                sed -i "s/^MCP_MAX_RESULTS.*$/MCP_MAX_RESULTS = $val/" "$MCP_DIR/config.py"
            else
                echo "" >> "$MCP_DIR/config.py"
                echo "# MCP output cap — max chunks per search_kb call (Amazon Q enforces 100K char limit)" >> "$MCP_DIR/config.py"
                echo "MCP_MAX_RESULTS = $val" >> "$MCP_DIR/config.py"
            fi
            chown "$OWNER" "$MCP_DIR/config.py"
            echo "OK: MCP_MAX_RESULTS set to $val"
            deployed=1
            ;;
        kill_builds)
            pkill -KILL -f 'build_index.py' 2>/dev/null || true
            rm -f /tmp/vporag_build.pid
            echo "OK: all build_index.py processes killed, PID file cleared"
            deployed=1
            ;;
        restart_only)
            deployed=1  # no file copy, just proceed to restart
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [ "$deployed" -eq 0 ]; then
    echo "Usage: sudo vporag-deploy [search_kb] [search_jira] [server] [config_max_results=N] [kill_builds]" >&2
    exit 1
fi

# Guard: refuse to restart if an index build is running
PID_FILE="/tmp/vporag_build.pid"
if [ -f "$PID_FILE" ]; then
    BUILD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$BUILD_PID" ] && kill -0 "$BUILD_PID" 2>/dev/null; then
        echo "SKIPPED: index build is running (PID $BUILD_PID) -- files deployed, restart deferred." >&2
        echo "Restart manually after the build completes: sudo systemctl restart vporag-mcp vporag-dashboard"
        exit 0
    fi
fi

systemctl restart vporag-mcp vporag-dashboard
sleep 2
systemctl is-active vporag-mcp vporag-dashboard
