#!/bin/bash
ACCESS_LOG="/srv/vpo_rag/JSON/logs/mcp_access.log"
STATE_FILE="/srv/vpo_rag/JSON/state/processing_state.json"
PID_FILE="/tmp/vporag_build.pid"
BUILD_TIMEOUT=36000  # 10 hour hard cap
FORCE_FULL=false
RUN_USER=""

# Parse flags
for arg in "$@"; do
    case $arg in
        -f|--full) FORCE_FULL=true ;;
        --user=*)  RUN_USER="${arg#--user=}" ;;
    esac
done

# Require --user
if [ -z "$RUN_USER" ]; then
    echo "ERROR: --user is required. Usage: run_build.sh [--full] --user=P<7digits>" >&2
    exit 1
fi

# ── Single-build enforcement: kill any existing build ────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Killing existing build PID $OLD_PID (new build requested by $RUN_USER)" >&2
        kill -TERM "$OLD_PID" 2>/dev/null
        sleep 2
        kill -KILL "$OLD_PID" 2>/dev/null
        # Log the kill to access log
        /srv/vpo_rag/venv/bin/python3 - <<PYEOF
import json, datetime, uuid
now = datetime.datetime.utcnow()
record = {
    'timestamp':  now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z',
    'event':      'tool_error',
    'tool':       'build_index',
    'error_type': 'BuildKilled',
    'error':      f'Killed PID ${OLD_PID} — new build requested by ${RUN_USER}',
    'user_id':    '${RUN_USER}',
    'trigger':    'manual',
    'request_id': uuid.uuid4().hex[:12],
}
with open('${ACCESS_LOG}', 'a') as f:
    f.write(json.dumps(record) + '\n')
PYEOF
    fi
    rm -f "$PID_FILE"
fi

# Force full rebuild if requested
if [ "$FORCE_FULL" = true ]; then
    echo "Force full rebuild requested — deleting processing state..."
    rm -f "$STATE_FILE"
fi

# Detect full rebuild (state file absent at start)
if [ ! -f "$STATE_FILE" ]; then
    FORCE_FULL=true
fi

LOG="/srv/vpo_rag/JSON/logs/build_$(date +%Y%m%d_%H%M%S).log"
START=$(date +%s)
EXIT_CODE=1   # default — overwritten on clean exit

# ── Always write access log event on exit (clean finish OR kill) ──────────────
_write_access_log() {
    local end=$(date +%s)
    PY_LOG_SCRIPT=$(mktemp /tmp/build_log_XXXXXX.py)
    cat > "$PY_LOG_SCRIPT" << 'PYEOF'
import json, datetime, uuid, re, os
log_file   = os.environ['BUILD_LOG']
access_log = os.environ['ACCESS_LOG']
force_full = os.environ['FORCE_FULL'] == 'true'
exit_code  = int(os.environ['EXIT_CODE'])
elapsed_ms = int(os.environ['ELAPSED_MS'])
who        = os.environ['WHO']
try:
    log_text = open(log_file).read()
except Exception:
    log_text = ''
files_processed = 0
chunks_by_category = {}
peak_rss_mb = None
for line in log_text.splitlines():
    m = re.search(r'Processed (\d+) files?', line)
    if m:
        files_processed = int(m.group(1))
    m = re.search(r'Wrote (\d+) chunks to chunks\.([\w]+)\.jsonl', line)
    if m:
        chunks_by_category[m.group(2)] = int(m.group(1))
    m = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', line)
    if m:
        peak_rss_mb = round(int(m.group(1)) / 1024, 1)
completed = '=== BUILD COMPLETE ===' in log_text
now = datetime.datetime.utcnow()
record = {
    'timestamp':          now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z',
    'event':              'build_index',
    'trigger':            'manual',
    'force_full':         force_full,
    'exit_code':          exit_code,
    'completed':          completed,
    'duration_ms':        elapsed_ms,
    'files_processed':    files_processed,
    'chunks_by_category': chunks_by_category or None,
    'peak_rss_mb':        peak_rss_mb,
    'user_id':            who,
    'request_id':         uuid.uuid4().hex[:12],
}
with open(access_log, 'a') as f:
    f.write(json.dumps(record) + '\n')
if not completed:
    err = {
        'timestamp':  record['timestamp'],
        'event':      'tool_error',
        'tool':       'build_index',
        'error_type': 'BuildKilled' if exit_code != 0 else 'BuildFailed',
        'error':      f'Build did not complete — exit_code={exit_code}, files_processed={files_processed}, duration_ms={elapsed_ms}',
        'user_id':    who,
        'trigger':    'manual',
        'force_full': force_full,
        'request_id': uuid.uuid4().hex[:12],
    }
    with open(access_log, 'a') as f:
        f.write(json.dumps(err) + '\n')
PYEOF
    BUILD_LOG="$LOG" ACCESS_LOG="$ACCESS_LOG" FORCE_FULL="$FORCE_FULL" EXIT_CODE="$EXIT_CODE" \
        ELAPSED_MS="$(( ($(date +%s) - START) * 1000 ))" WHO="$RUN_USER" \
        /srv/vpo_rag/venv/bin/python3 "$PY_LOG_SCRIPT"
    rm -f "$PY_LOG_SCRIPT"
}
trap '_write_access_log' EXIT

# ── Write header directly to log (no tee — avoids pipe buffer deadlock) ───────
{
    echo "=== vpoRAG Index Build ==="
    echo "Start:       $(date)"
    echo "Host:        $(hostname)"
    echo "CPUs:        $(nproc)"
    echo "RAM:         $(free -h | awk '/^Mem/{print $2}')"
    echo "Source docs: $(ls /srv/vpo_rag/source_docs/ | wc -l) files"
    echo "Force full:  $FORCE_FULL"
    echo "User:        $RUN_USER"
    echo ""
} >> "$LOG" 2>&1

# Also write header to dashboard_build.log for live monitor
{
    echo "=== vpoRAG Index Build ==="
    echo "Start:       $(date)"
    echo "Force full:  $FORCE_FULL"
    echo "--user=$RUN_USER"
} > /tmp/dashboard_build.log 2>&1

# ── Run indexer — redirect directly, NO tee, NO pipe ─────────────────────────
cd /srv/vpo_rag/indexers
/usr/bin/time -v /srv/vpo_rag/venv/bin/python build_index.py >> "$LOG" 2>&1 &
BUILD_PID=$!
echo "$BUILD_PID" > "$PID_FILE"
echo "Build PID: $BUILD_PID" >> "$LOG"

# Wait with hard timeout
SECONDS_WAITED=0
while kill -0 "$BUILD_PID" 2>/dev/null; do
    sleep 5
    SECONDS_WAITED=$((SECONDS_WAITED + 5))
    if [ $SECONDS_WAITED -ge $BUILD_TIMEOUT ]; then
        echo "" >> "$LOG"
        echo "=== BUILD TIMEOUT after ${BUILD_TIMEOUT}s — killing PID $BUILD_PID ===" >> "$LOG"
        kill -TERM "$BUILD_PID" 2>/dev/null
        sleep 2
        kill -KILL "$BUILD_PID" 2>/dev/null
        EXIT_CODE=124
        rm -f "$PID_FILE"
        break
    fi
done

if [ $SECONDS_WAITED -lt $BUILD_TIMEOUT ]; then
    wait "$BUILD_PID"
    EXIT_CODE=$?
    rm -f "$PID_FILE"
fi

# Append log to dashboard_build.log so monitor can read it
cat "$LOG" >> /tmp/dashboard_build.log 2>/dev/null

END=$(date +%s)
ELAPSED=$((END - START))
MINS=$((ELAPSED / 60))
SECS=$((ELAPSED % 60))

{
    echo ""
    echo "=== BUILD COMPLETE ==="
    echo "End:     $(date)"
    echo "Elapsed: ${MINS}m ${SECS}s (${ELAPSED}s total)"
    echo ""
    echo "=== OUTPUT FILES ==="
    for f in /srv/vpo_rag/JSON/detail/chunks.*.jsonl; do
        [ -f "$f" ] || continue
        echo "  $(basename $f): $(wc -l < $f) chunks ($(du -sh $f | cut -f1))"
    done
    echo ""
    echo "Log: $LOG"
} >> "$LOG" 2>&1

# Sync final log to dashboard_build.log
cat "$LOG" > /tmp/dashboard_build.log 2>/dev/null

# trap EXIT fires here — writes access log event
