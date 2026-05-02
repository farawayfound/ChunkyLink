#!/bin/bash
# Nightly KB full rebuild — only runs if source files have changed since last build.
# Cron (19:00 MDT = 7:00 PM MT):
#   0 19 * * * /srv/vpo_rag/mcp_server/scripts/nightly_build.sh >> /srv/vpo_rag/JSON/logs/nightly_build.log 2>&1

VENV_PYTHON="/srv/vpo_rag/venv/bin/python"
INDEXER="/srv/vpo_rag/indexers/build_index.py"
DETAIL_DIR="/srv/vpo_rag/JSON/detail"
SOURCE_DIR="/srv/vpo_rag/source_docs"
STATE_FILE="/srv/vpo_rag/JSON/state/processing_state.json"
LOG="/srv/vpo_rag/JSON/logs/nightly_build.log"
ACCESS_LOG="/srv/vpo_rag/JSON/logs/mcp_access.log"
STAMP_FILE="/srv/vpo_rag/JSON/state/nightly_source_stamp"

echo "=== nightly_build.sh start: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# ── Change detection ──────────────────────────────────────────────────────────
# Compute a lightweight fingerprint of source_docs: sorted list of
# "filename size mtime" lines. If it matches the last-run stamp, skip.
CURRENT_STAMP=$(find "$SOURCE_DIR" -maxdepth 1 -type f \
    -printf '%f %s %T@\n' 2>/dev/null | sort)

if [ -f "$STAMP_FILE" ]; then
    LAST_STAMP=$(cat "$STAMP_FILE")
    if [ "$CURRENT_STAMP" = "$LAST_STAMP" ]; then
        echo "No changes detected in source_docs — skipping build."
        echo "=== nightly_build.sh skipped: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
        exit 0
    fi
    echo "Changes detected in source_docs — running incremental build."
else
    echo "No stamp file found — running build (first nightly run or state cleared)."
fi

START=$(date +%s)
EXIT_CODE=1  # default — overwritten on clean exit

# ── Always write access log on exit (clean or killed) ────────────────────────
_write_access_log() {
    local end=$(date +%s)
    PY_SCRIPT=$(mktemp /tmp/nightly_log_XXXXXX.py)
    cat > "$PY_SCRIPT" << 'PYEOF'
import json, datetime, uuid, re, os
log_file   = os.environ['BUILD_LOG']
access_log = os.environ['ACCESS_LOG']
exit_code  = int(os.environ['EXIT_CODE'])
elapsed_ms = int(os.environ['ELAPSED_MS'])
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
completed = 'Combined processing complete' in log_text
now = datetime.datetime.utcnow()
record = {
    'timestamp':          now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z',
    'event':              'build_index',
    'trigger':            'cron',
    'force_full':         True,
    'exit_code':          exit_code,
    'completed':          completed,
    'duration_ms':        elapsed_ms,
    'files_processed':    files_processed,
    'chunks_by_category': chunks_by_category or None,
    'peak_rss_mb':        peak_rss_mb,
    'user_id':            'cron',
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
        'error':      f'Nightly build did not complete — exit_code={exit_code}, files_processed={files_processed}',
        'user_id':    'cron',
        'trigger':    'cron',
        'request_id': uuid.uuid4().hex[:12],
    }
    with open(access_log, 'a') as f:
        f.write(json.dumps(err) + '\n')
PYEOF
    BUILD_LOG="$LOG" ACCESS_LOG="$ACCESS_LOG" EXIT_CODE="$EXIT_CODE" \
        ELAPSED_MS="$(( ($(date +%s) - START) * 1000 ))" \
        $VENV_PYTHON "$PY_SCRIPT"
    rm -f "$PY_SCRIPT"
}
trap '_write_access_log' EXIT

# ── Run full rebuild — delete state file first, direct redirect, no tee/pipe ──
echo "Deleting processing state for full rebuild..."
rm -f "/srv/vpo_rag/JSON/state/processing_state.json"
cd /srv/vpo_rag/indexers
/usr/bin/time -v $VENV_PYTHON "$INDEXER" >> "$LOG" 2>&1
EXIT_CODE=$?

# ── Update stamp only on success ──────────────────────────────────────────────
if [ $EXIT_CODE -eq 0 ]; then
    echo "$CURRENT_STAMP" > "$STAMP_FILE"
    echo "Source stamp updated."
else
    echo "Build exited with code $EXIT_CODE — stamp NOT updated (will retry tomorrow)."
fi

# ── Push learned file to GitLab if remote is configured ──────────────────────
if git -C "$DETAIL_DIR" remote get-url origin > /dev/null 2>&1; then
    echo "Pushing chunks.learned.jsonl to GitLab..."
    git -C "$DETAIL_DIR" push origin main
else
    echo "No GitLab remote configured — skipping push."
fi

echo "=== nightly_build.sh done: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
# trap EXIT fires here
