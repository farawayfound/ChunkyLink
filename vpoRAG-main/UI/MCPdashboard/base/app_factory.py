# -*- coding: utf-8 -*-
"""App factory — creates the Flask app with all routes, injecting a LogReader implementation."""
from flask import Flask, render_template, jsonify, request, send_file
import json, io
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .log_reader import LogReader

_MT = timezone(timedelta(hours=-6))  # MST; change to -7 for MDT

def _to_mt(ts: str) -> str:
    """Convert an ISO-8601 timestamp string to Mountain Time."""
    if not ts:
        return ts
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.astimezone(_MT).strftime('%Y-%m-%dT%H:%M:%S%z')
    except Exception:
        return ts

def _localise(event: dict) -> dict:
    if 'timestamp' in event:
        event = {**event, 'timestamp': _to_mt(event['timestamp'])}
    return event

_SHARED_ROOT = Path(__file__).parent.parent   # UI/MCPdashboard/


def create_app(reader: LogReader) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(_SHARED_ROOT / 'templates'),
        static_folder=str(_SHARED_ROOT / 'static'),
    )
    app.config['SECRET_KEY'] = 'vporag-mcp-dash'

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _events(max_lines=5000):
        return [_localise(json.loads(l)) for l in reader.fetch_lines(max_lines) if l.strip()]

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/events')
    def get_events():
        limit  = int(request.args.get('limit', 200))
        events = request.args.getlist('event')
        client = request.args.get('client', '')
        since  = request.args.get('since', '')
        try:
            all_ev = _events()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        if events:
            all_ev = [e for e in all_ev if e.get('event') in events]
        if client:
            all_ev = [e for e in all_ev if
                      client.lower() in (e.get('client_ip') or '').lower() or
                      client.lower() in (e.get('user_id') or '').lower()]
        if since:
            all_ev = [e for e in all_ev if e.get('timestamp', '') >= since]

        all_ev.sort(key=lambda e: e.get('timestamp', ''), reverse=True)
        return jsonify({'events': all_ev[:limit], 'total': len(all_ev)})

    @app.route('/api/stats')
    def get_stats():
        try:
            lines  = reader.fetch_lines()
            all_ev = [_localise(json.loads(l)) for l in lines if l.strip()]
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        tool_events  = [e for e in all_ev if e.get('event') in ('search_kb', 'search_jira', 'build_index', 'learn')]
        http_events  = [e for e in all_ev if e.get('event') == 'request_end']
        errors       = [e for e in all_ev if e.get('event') in ('tool_error', 'search_kb_warning', 'search_jira_warning')]

        calls_by_tool: dict[str, int] = defaultdict(int)
        for e in tool_events:
            calls_by_tool[e['event']] += 1

        calls_by_client: dict[str, int] = defaultdict(int)
        for e in tool_events:
            ip  = e.get('client_ip', 'unknown')
            uid = e.get('user_id', '')
            calls_by_client[f"{uid} ({ip})" if uid and uid != 'anonymous' else ip] += 1

        durations: dict[str, list[int]] = defaultdict(list)
        for e in tool_events:
            if 'duration_ms' in e:
                durations[e['event']].append(e['duration_ms'])
        avg_duration = {t: round(sum(v) / len(v)) for t, v in durations.items() if v}

        calls_by_day: dict[str, int] = defaultdict(int)
        calls_by_day_by_tool: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for e in tool_events:
            ts = e.get('timestamp', '')
            if ts:
                calls_by_day[ts[:10]] += 1
                calls_by_day_by_tool[e['event']][ts[:10]] += 1
        # Ensure days with only HTTP activity still appear on the chart
        for e in http_events:
            ts = e.get('timestamp', '')
            if ts:
                calls_by_day.setdefault(ts[:10], 0)
                calls_by_day_by_tool['request_end'].setdefault(ts[:10], 0)
                calls_by_day_by_tool['request_end'][ts[:10]] += 1

        level_dist: dict[str, int] = defaultdict(int)
        for e in all_ev:
            if e.get('event') == 'search_kb' and 'level' in e:
                level_dist[e['level']] += 1

        kb_chunks  = [e.get('chunks_returned', 0) for e in all_ev if e.get('event') == 'search_kb']
        avg_chunks = round(sum(kb_chunks) / len(kb_chunks), 1) if kb_chunks else 0

        jira_sources: dict[str, int] = defaultdict(int)
        for e in all_ev:
            if e.get('event') == 'search_jira' and 'source' in e:
                jira_sources[e['source']] += 1

        last_event = max(tool_events, key=lambda e: e.get('timestamp', ''), default=None)

        return jsonify({
            'total_calls':          len(tool_events),
            'total_errors':         len(errors),
            'calls_by_tool':        dict(calls_by_tool),
            'calls_by_client':      dict(calls_by_client),
            'avg_duration_ms':      avg_duration,
            'calls_by_day':         dict(sorted(calls_by_day.items())),
            'calls_by_day_by_tool': {t: dict(sorted(v.items())) for t, v in calls_by_day_by_tool.items()},
            'level_dist':           dict(level_dist),
            'avg_chunks':           avg_chunks,
            'jira_sources':         dict(jira_sources),
            'last_activity':        last_event.get('timestamp') if last_event else None,
            'log_lines_read':       len(lines),
            'all_tool_events':      tool_events,
            'all_http_events':      http_events,
            'all_errors':           errors,
        })

    @app.route('/api/errors')
    def get_errors():
        try:
            all_ev = _events()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        _ERROR_EVENTS = ('tool_error', 'search_kb_warning', 'search_jira_warning', 'csv_ingest')
        errors = sorted(
            [e for e in all_ev if e.get('event') in _ERROR_EVENTS
             and (e.get('event') != 'csv_ingest' or e.get('status') == 'fail')],
            key=lambda e: e.get('timestamp', ''), reverse=True
        )
        return jsonify({'errors': errors[:200], 'total': len(errors)})

    @app.route('/api/jira-db')
    def get_jira_db():
        try:
            all_ev = _events()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        ingests = sorted(
            [e for e in all_ev if e.get('event') == 'csv_ingest'],
            key=lambda e: e.get('timestamp', ''), reverse=True
        )
        return jsonify({'ingests': ingests[:200], 'total': len(ingests)})

    @app.route('/api/server-status')
    def server_status():
        return jsonify(reader.check_server_status())

    # ── Learned KB routes ─────────────────────────────────────────────────────

    @app.route('/api/index/stats')
    def index_stats():
        try:
            all_ev = _events()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

        builds = sorted(
            [e for e in all_ev if e.get('event') == 'build_index'],
            key=lambda e: e.get('timestamp', ''), reverse=True
        )

        files = reader.read_index_files()
        total_chunks = sum(f['line_count'] for f in files)
        total_bytes  = sum(f['size_bytes'] for f in files)

        # Category breakdown from file names: chunks.<category>.jsonl
        categories = []
        for f in files:
            name = f['name']  # e.g. chunks.troubleshooting.jsonl
            parts = name.split('.')
            cat = parts[1] if len(parts) >= 3 else name
            categories.append({
                'category':   cat,
                'chunks':     f['line_count'],
                'size_bytes': f['size_bytes'],
            })

        return jsonify({
            'categories':   categories,
            'total_chunks': total_chunks,
            'total_bytes':  total_bytes,
            'builds':       builds[:200],
            'total_builds': len(builds),
        })

    @app.route('/api/index/files', methods=['GET'])
    def index_list_files():
        try:
            return jsonify({'files': reader.list_source_files()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/files/<path:filename>', methods=['GET'])
    def index_download_file(filename):
        safe = Path(filename).name
        if not safe or safe.startswith('.'):
            return jsonify({'error': 'invalid filename'}), 400
        try:
            data, mime = reader.download_source_file(safe)
            return send_file(io.BytesIO(data), download_name=safe, as_attachment=True, mimetype=mime)
        except FileNotFoundError:
            return jsonify({'error': 'file not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/files/<path:filename>', methods=['DELETE'])
    def index_delete_file(filename):
        safe = Path(filename).name
        if not safe or safe.startswith('.'):
            return jsonify({'error': 'invalid filename'}), 400
        try:
            result = reader.delete_source_file(safe)
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/files', methods=['POST'])
    def index_upload_file():
        if 'file' not in request.files:
            return jsonify({'error': 'no file in request'}), 400
        f = request.files['file']
        safe = Path(f.filename).name
        allowed = {'.pdf', '.txt', '.docx', '.pptx', '.csv'}
        if not safe or Path(safe).suffix.lower() not in allowed:
            return jsonify({'error': f'unsupported file type — allowed: {allowed}'}), 400
        try:
            result = reader.upload_source_file(safe, f.read())
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/build-status')
    def index_build_status():
        try:
            return jsonify(reader.get_build_status())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/build/kill', methods=['POST'])
    def index_kill_build():
        try:
            result = reader.kill_build()
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/index/build', methods=['POST'])
    def index_trigger_build():
        data       = request.get_json(force=True) or {}
        force_full = bool(data.get('force_full', False))
        user_id    = str(data.get('user_id', 'dashboard'))[:20]
        try:
            result = reader.trigger_build(force_full, user_id)
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ── Jira CSV routes ───────────────────────────────────────────────────────

    # Required columns per table — must all be present in the CSV header
    _CSV_REQUIRED = {
        'dpstriage': {
            'Issue key', 'Issue id', 'Summary', 'Status', 'Updated', 'Created',
            'Custom field (Resolution Category)', 'Custom field (Last Comment)',
        },
        'postrca': {
            'Issue key', 'Issue id', 'Summary', 'Status', 'Updated', 'Created',
            'Custom field (Resolution / Mitigation Solution)',
        },
    }

    @app.route('/api/jira/csv-files')
    def jira_csv_files():
        try:
            return jsonify(reader.list_csv_files())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/jira/csv-download/<table>/<path:filename>')
    def jira_csv_download(table, filename):
        if table not in ('dpstriage', 'postrca'):
            return jsonify({'error': 'invalid table'}), 400
        safe = Path(filename).name
        if not safe or safe.startswith('.'):
            return jsonify({'error': 'invalid filename'}), 400
        try:
            data = reader.download_csv_file(table, safe)
            return send_file(io.BytesIO(data), download_name=safe, as_attachment=True, mimetype='text/csv')
        except FileNotFoundError:
            return jsonify({'error': 'file not found'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/jira/csv-upload', methods=['POST'])
    def jira_csv_upload():
        import csv, io
        table = request.form.get('table', '').strip().lower()
        if table not in ('dpstriage', 'postrca'):
            return jsonify({'ok': False, 'error': 'table must be dpstriage or postrca'}), 400
        if 'file' not in request.files:
            return jsonify({'ok': False, 'error': 'no file in request'}), 400
        f    = request.files['file']
        safe = Path(f.filename).name
        if not safe.lower().endswith('.csv'):
            return jsonify({'ok': False, 'error': 'file must be a .csv'}), 400
        data = f.read()
        # Server-side column validation
        try:
            text    = data.decode('utf-8-sig', errors='replace')
            reader_ = csv.DictReader(io.StringIO(text))
            headers = set(reader_.fieldnames or [])
            required = _CSV_REQUIRED[table]
            missing  = required - headers
            if missing:
                return jsonify({
                    'ok': False,
                    'error': f'Missing required columns: {sorted(missing)}',
                    'found_columns': sorted(headers),
                }), 422
        except Exception as e:
            return jsonify({'ok': False, 'error': f'CSV parse error: {e}'}), 422
        try:
            result = reader.upload_csv_file(table, safe, data)
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/jira/db-download')
    def jira_db_download():
        try:
            data, filename = reader.download_jira_db(None)
            return send_file(io.BytesIO(data), download_name=filename,
                             as_attachment=True, mimetype='application/x-sqlite3')
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/index/download')
    def index_download_zip():
        try:
            data = reader.download_index_zip()
            import datetime
            filename = f'vporag_index_{datetime.date.today().isoformat()}.zip'
            return send_file(io.BytesIO(data), download_name=filename,
                             as_attachment=True, mimetype='application/zip')
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/stats')
    def learned_stats():
        try:
            lines = reader.read_learned_chunks()
            chunks = [json.loads(l) for l in lines if l.strip()]
            file_size = sum(len(l.encode('utf-8')) for l in lines)
            by_day: dict[str, int] = defaultdict(int)
            for c in chunks:
                ts = c.get('metadata', {}).get('session_ts', '')
                if ts:
                    by_day[ts[:10]] += 1
            return jsonify({
                'chunk_count': len(chunks),
                'file_size_bytes': file_size,
                'by_day': dict(sorted(by_day.items())),
                'last_ts': max((c.get('metadata', {}).get('session_ts', '') for c in chunks), default=None),
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/chunks')
    def learned_chunks():
        page     = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        try:
            lines  = reader.read_learned_chunks()
            chunks = []
            for l in lines:
                if l.strip():
                    try:
                        chunks.append(json.loads(l))
                    except Exception:
                        pass
            chunks.sort(key=lambda c: c.get('metadata', {}).get('session_ts', ''), reverse=True)
            total  = len(chunks)
            start  = (page - 1) * per_page
            sliced = chunks[start:start + per_page]
            # Slim for table display
            rows = [{
                'id':         c.get('id', ''),
                'title':      c.get('metadata', {}).get('title', '')[:80],
                'preview':    (c.get('text_raw') or c.get('text', ''))[:120].replace('\n', ' '),
                'category':   (c.get('tags') or [''])[0],
                'tags':       c.get('tags', []),
                'ticket_key': c.get('metadata', {}).get('ticket_key', ''),
                'user_id':    c.get('metadata', {}).get('user_id', ''),
                'session_ts': _to_mt(c.get('metadata', {}).get('session_ts', '')),
                'text_raw':   c.get('text_raw') or c.get('text', ''),
            } for c in sliced]
            return jsonify({'chunks': rows, 'total': total, 'page': page, 'per_page': per_page})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/history/<commit>')
    def learned_commit_detail(commit):
        """Return the chunk added by this commit plus KB snapshot stats at that point."""
        if not commit.replace('-', '').isalnum():
            return jsonify({'error': 'invalid commit'}), 400
        try:
            raw = reader.run_git_show(commit)
            # Parse added lines from the diff
            chunks_added = []
            for line in raw.splitlines():
                if line.startswith('+{') or line.startswith('+  {'):
                    try:
                        chunks_added.append(json.loads(line[1:]))
                    except Exception:
                        pass
            # Get full file state at this commit for snapshot stats
            snapshot_raw = reader.run_git_show_file(commit)
            total = 0
            by_category = defaultdict(int)
            for line in snapshot_raw.splitlines():
                if not line.strip():
                    continue
                try:
                    c = json.loads(line)
                    total += 1
                    cat = (c.get('tags') or ['general'])[0]
                    by_category[cat] += 1
                except Exception:
                    pass
            return jsonify({
                'commit':      commit,
                'chunks':      chunks_added,
                'snapshot':    {'total': total, 'by_category': dict(by_category)},
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/history')
    def learned_history():
        try:
            raw = reader.run_git_log()
            entries = []
            for line in raw.splitlines():
                if '|' not in line:
                    continue
                parts = line.split('|', 2)
                if len(parts) == 3:
                    entries.append({
                        'commit':    parts[0].strip(),
                        'timestamp': _to_mt(parts[1].strip()),
                        'message':   parts[2].strip(),
                    })
            return jsonify({'history': entries})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/rollback', methods=['POST'])
    def learned_rollback():
        data   = request.get_json(force=True) or {}
        action = data.get('action', 'rollback_to')   # rollback_to | forward_to_latest | remove_single
        commit = data.get('commit', '')
        if not commit and action != 'forward_to_latest':
            return jsonify({'error': 'commit is required'}), 400
        try:
            result = reader.restore_learned_to_commit(
                action=action,
                commit=commit,
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/chunk/<path:chunk_id>', methods=['DELETE'])
    def learned_delete_chunk(chunk_id):
        user_id = request.args.get('user_id', 'dashboard')
        try:
            result = reader.delete_learned_chunk(chunk_id, user_id)
            return jsonify(result), (200 if result['ok'] else 500)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/learned/chunk/<path:chunk_id>', methods=['PUT'])
    def learned_edit_chunk(chunk_id):
        data     = request.get_json(force=True) or {}
        new_text = data.get('text', '').strip()
        new_tags = data.get('tags', [])
        new_title = data.get('title', '').strip()
        user_id  = data.get('user_id', 'dashboard')
        if not new_text:
            return jsonify({'error': 'text is required'}), 400
        try:
            result = reader.write_learned_chunk_edit(chunk_id, new_text, new_tags, new_title, user_id)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return app
