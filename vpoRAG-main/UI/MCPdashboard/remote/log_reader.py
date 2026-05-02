# -*- coding: utf-8 -*-
"""LocalLogReader — reads mcp_access.log directly from disk (server deployment)."""
import subprocess, json, os, re, time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from base.log_reader import LogReader

_LOG_PATH     = Path('/srv/vpo_rag/JSON/logs/mcp_access.log')
_DETAIL_DIR   = Path('/srv/vpo_rag/JSON/detail')
_LEARNED_FILE = _DETAIL_DIR / 'chunks.learned.jsonl'
_GIT_OPTS     = ['-C', str(_DETAIL_DIR)]
_BUILD_LOG    = Path('/tmp/dashboard_build.log')
_BUILD_PID    = Path('/tmp/vporag_build.pid')


_BUILD_LOG_DIR = Path('/srv/vpo_rag/JSON/logs')


def _find_active_build_log() -> Path | None:
    """Return the most recently modified build_YYYYMMDD_HHMMSS.log file."""
    candidates = sorted(
        _BUILD_LOG_DIR.glob('build_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9].log'),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _parse_build_status() -> dict:
    """Read /tmp/dashboard_build.log (header) + dated build log (progress) and /proc."""
    result = {
        'running': False, 'pid': None, 'start_time': None, 'elapsed_s': None,
        'cpu_pct': None, 'cores_used': None, 'rss_mb': None,
        'files_processed': 0, 'files_total': 0,
        'files_remaining': 0, 'current_file': None, 'force_full': None,
        'user_id': None, 'trigger': None, 'log_lines': 0, 'last_event': None,
    }
    if not _BUILD_LOG.exists():
        return result

    try:
        header_lines = _BUILD_LOG.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return result

    # Merge header with the dated build log (which has live progress during a run)
    dated_log = _find_active_build_log()
    if dated_log:
        try:
            dated_lines = dated_log.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            dated_lines = []
    else:
        dated_lines = []

    lines = header_lines + [l for l in dated_lines if l not in set(header_lines)]

    result['log_lines'] = len(lines)

    # Parse log for metadata
    for line in lines:
        m = re.search(r'--user=(\S+)', line)
        if m:
            result['user_id'] = m.group(1)
        if re.search(r'Force full[: ]+true', line, re.IGNORECASE) or 'Force full rebuild' in line:
            result['force_full'] = True
        if not result['trigger']:
            result['trigger'] = 'dashboard'
        m = re.search(r'Processing (\d+) files \((\d+) new', line)
        if m:
            result['files_total'] = int(m.group(1))
        m = re.search(r'Processing \[auto\] .+/([^/]+)$', line)
        if m:
            result['current_file'] = m.group(1).strip()
        m = re.search(r'Start:\s+(.+)', line)
        if m:
            result['start_time'] = m.group(1).strip()

    if result['force_full'] is None:
        result['force_full'] = False

    # Count completed files — "Completed [prof] filename" fires exactly once per file
    result['files_processed'] = sum(1 for l in lines if re.search(r'Completed \[\w+\]', l))
    result['files_remaining'] = max(0, result['files_total'] - result['files_processed'])

    # Determine build phase for accurate progress weighting
    # Phases: extraction(0) → cross_ref(1) → writing(2) → done(3)
    xref_total   = 0
    xref_done    = False
    writing_done = False
    for line in lines:
        m = re.search(r'Building cross-references for (\d+)', line)
        if m:
            xref_total = int(m.group(1))
        if re.search(r'Average related chunks per chunk', line):
            xref_done = True
        if re.search(r'Writing (all|new) chunks by category', line):
            writing_done = True  # writing started
        if re.search(r'Combined processing complete', line):
            writing_done = True

    # Count xref progress via "Processing new chunk N/" log lines
    xref_processed = 0
    for line in lines:
        m = re.search(r'Processing new chunk (\d+)/', line)
        if m:
            xref_processed = int(m.group(1))

    if xref_done or writing_done:
        result['phase'] = 'writing'
        result['phase_pct'] = 100
        result['xref_total'] = xref_total
        result['xref_processed'] = xref_total
    elif xref_total > 0:
        result['phase'] = 'cross_ref'
        result['phase_pct'] = round(xref_processed / xref_total * 100) if xref_total else 0
        result['xref_total'] = xref_total
        result['xref_processed'] = xref_processed
    else:
        result['phase'] = 'extraction'
        result['phase_pct'] = round(result['files_processed'] / result['files_total'] * 100) if result['files_total'] else 0
        result['xref_total'] = 0
        result['xref_processed'] = 0

    # Check if a PID file exists — means a build was started by run_build.sh
    pid_from_file = None
    if _BUILD_PID.exists():
        try:
            pid_from_file = int(_BUILD_PID.read_text().strip())
        except (OSError, ValueError):
            pass

    # Find the Python build_index.py process (highest RSS among matches)
    try:
        out = subprocess.run(
            ['pgrep', '-f', 'build_index.py'],
            capture_output=True, text=True, timeout=3
        )
        pids = [int(p) for p in out.stdout.split() if p.strip()]
    except Exception:
        pids = []

    if pids:
        pid = pids[0]
        result['running'] = True
        result['pid'] = pid

        # Instantaneous CPU% — sample entire process tree (parent + children) twice 500ms apart
        try:
            hz = os.sysconf('SC_CLK_TCK')

            def _get_tree_pids(root_pid):
                tree = [root_pid]
                try:
                    children_raw = Path(f'/proc/{root_pid}/task/{root_pid}/children').read_text().split()
                    for cpid in children_raw:
                        tree.extend(_get_tree_pids(int(cpid)))
                except OSError:
                    for entry in Path('/proc').iterdir():
                        if not entry.name.isdigit():
                            continue
                        try:
                            for sl in (entry / 'status').read_text().splitlines():
                                if sl.startswith('PPid:') and int(sl.split()[1]) == root_pid:
                                    tree.append(int(entry.name))
                        except OSError:
                            pass
                return tree

            def _read_cpu_ticks(p):
                parts = Path(f'/proc/{p}/stat').read_text().split()
                return int(parts[13]) + int(parts[14])

            tree_pids = _get_tree_pids(pid)

            # Sum RSS across entire process tree (main + all workers)
            total_rss_kb = 0
            for p in tree_pids:
                try:
                    for sl in Path(f'/proc/{p}/status').read_text().splitlines():
                        if sl.startswith('VmRSS:'):
                            total_rss_kb += int(sl.split()[1])
                            break
                except OSError:
                    pass
            result['rss_mb'] = round(total_rss_kb / 1024, 1) if total_rss_kb > 0 else None
            ticks1 = {}
            for p in tree_pids:
                try:
                    ticks1[p] = _read_cpu_ticks(p)
                except OSError:
                    pass
            time.sleep(0.5)
            total_delta = 0
            cores_active = 0
            for p in list(ticks1):
                try:
                    delta = _read_cpu_ticks(p) - ticks1[p]
                    pct_p = delta / hz / 0.5 * 100
                    total_delta += delta
                    if pct_p >= 5.0:
                        cores_active += 1
                except OSError:
                    pass
            num_cpus = os.cpu_count() or 1
            raw_cpu = round(total_delta / hz / 0.5 * 100 / num_cpus, 1)
            result['cpu_pct']    = min(raw_cpu, 100.0)
            result['cores_used'] = cores_active

            parts = Path(f'/proc/{pid}/stat').read_text().split()
            starttime = int(parts[21])
            boot_time = int([l for l in Path('/proc/stat').read_text().splitlines()
                             if l.startswith('btime')][0].split()[1])
            start_epoch = boot_time + starttime / hz
            result['elapsed_s'] = round(time.time() - start_epoch)
        except Exception:
            pass
    else:
        # Authoritative source: most recent build_index event in the access log.
        # exit_code >= 128 = killed by signal (143=SIGTERM, 137=SIGKILL).
        # Only fall back to log-text string matching if no access log entry exists.
        last_build_event = None
        try:
            build_events = [
                json.loads(l) for l in _LOG_PATH.read_text(encoding='utf-8').splitlines()
                if l.strip() and '"build_index"' in l
            ]
            if build_events:
                last_build_event = max(build_events, key=lambda e: e.get('timestamp', ''))
        except Exception:
            pass

        if last_build_event is not None:
            exit_code    = last_build_event.get('exit_code')
            log_complete = last_build_event.get('completed', False)
            if exit_code is not None and exit_code >= 128:
                result['last_event'] = 'failed'   # killed by signal
            elif log_complete and exit_code == 0:
                result['last_event'] = 'completed'
            else:
                result['last_event'] = 'failed' if lines else None
        else:
            # No access log entry — fall back to build log string match
            completed = any('=== BUILD COMPLETE ===' in l for l in lines)
            result['last_event'] = 'completed' if completed else ('failed' if lines else None)

        # If PID file exists but process is gone and build didn't complete — it was killed
        # hard (SIGKILL) and the EXIT trap never fired. Write the access log entry now.
        if pid_from_file and result['last_event'] != 'completed' and lines:
            _write_killed_event(result)
            _BUILD_PID.unlink(missing_ok=True)

    return result


def _write_killed_event(status: dict) -> None:
    """Write a BuildKilled access log entry when run_build.sh's EXIT trap couldn't fire."""
    import uuid
    try:
        now = __import__('datetime').datetime.utcnow()
        record = {
            'timestamp':       now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z',
            'event':           'tool_error',
            'tool':            'build_index',
            'error_type':      'BuildKilled',
            'error':           f'Build killed externally (SIGKILL/service restart) — '
                               f'{status["files_processed"]} of {status["files_total"]} files completed',
            'user_id':         status.get('user_id') or 'unknown',
            'trigger':         status.get('trigger') or 'unknown',
            'force_full':      status.get('force_full'),
            'files_processed': status.get('files_processed', 0),
            'request_id':      uuid.uuid4().hex[:12],
        }
        with open(str(_LOG_PATH), 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
    except Exception:
        pass


_SOURCE_DOCS  = Path('/srv/vpo_rag/source_docs')
_DPS_CSV_DIR  = Path('/srv/samba/share/dpstriageCSV')
_RCA_CSV_DIR  = Path('/srv/samba/share/postrcaCSV')
_INGEST_DPS   = Path('/srv/vpo_rag/mcp_server/scripts/ingest_jira_csv.py')
_INGEST_RCA   = Path('/srv/vpo_rag/mcp_server/scripts/ingest_postrca_csv.py')
_VENV_PY      = '/srv/vpo_rag/venv/bin/python'


class LocalLogReader(LogReader):
    """Reads the log file directly — used when running on the MCP server."""

    def fetch_lines(self, max_lines: int = 5000) -> list[str]:
        log_dir = _LOG_PATH.parent
        files = sorted(log_dir.glob(_LOG_PATH.name + '.*')) + ([_LOG_PATH] if _LOG_PATH.exists() else [])
        lines: list[str] = []
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    lines.extend(l.rstrip('\n') for l in fh if l.strip())
            except OSError:
                pass
        return lines[-max_lines:]

    def check_server_status(self) -> dict:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'vporag-mcp'],
                capture_output=True, text=True, timeout=5
            )
            active = result.stdout.strip() == 'active'
            return {'active': active, 'status': result.stdout.strip()}
        except Exception as e:
            return {'active': False, 'status': 'unreachable', 'error': str(e)}

    def read_learned_chunks(self) -> list[str]:
        if not _LEARNED_FILE.exists():
            return []
        with open(_LEARNED_FILE, encoding='utf-8') as f:
            return [l.rstrip('\n') for l in f if l.strip()]

    def run_git_log(self) -> str:
        try:
            r = subprocess.run(
                ['git'] + _GIT_OPTS + ['log', '--format=%H|%ai|%s', '--', 'chunks.learned.jsonl'],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_show(self, commit: str) -> str:
        try:
            r = subprocess.run(
                ['git'] + _GIT_OPTS + ['show', '--unified=0', commit, '--', 'chunks.learned.jsonl'],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_show_file(self, commit: str) -> str:
        try:
            r = subprocess.run(
                ['git'] + _GIT_OPTS + ['show', f'{commit}:chunks.learned.jsonl'],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_op(self, args: list[str]) -> dict:
        try:
            r = subprocess.run(
                ['git'] + _GIT_OPTS + args,
                capture_output=True, text=True, timeout=30
            )
            return {'ok': r.returncode == 0, 'output': r.stdout + r.stderr}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def restore_learned_to_commit(self, action: str, commit: str) -> dict:
        """Restore chunks.learned.jsonl to a prior state by writing file content
        directly — never uses git revert, so conflict markers are impossible."""
        import re
        try:
            # Determine which commit's file content to restore
            if action == 'rollback_to':
                target = commit          # restore to exact state at this commit
            elif action == 'remove_single':
                target = f'{commit}^'   # restore to parent (i.e. before this commit)
            elif action == 'forward_to_latest':
                target = 'HEAD'         # restore to current HEAD
            else:
                return {'ok': False, 'output': f'unknown action: {action}'}

            # Get the file content at the target commit
            r = subprocess.run(
                ['git'] + _GIT_OPTS + ['show', f'{target}:chunks.learned.jsonl'],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0:
                return {'ok': False, 'output': r.stderr or f'git show {target} failed'}

            # Write directly — no merge, no conflict possible
            _LEARNED_FILE.write_text(r.stdout, encoding='utf-8')

            # Stage and commit
            stage = subprocess.run(
                ['git'] + _GIT_OPTS + ['add', 'chunks.learned.jsonl'],
                capture_output=True, text=True, timeout=10
            )
            if stage.returncode != 0:
                return {'ok': False, 'output': stage.stderr}

            label = commit[:7] if commit else 'HEAD'
            msg = {
                'rollback_to':       f'rollback: restore to {label}',
                'remove_single':     f'remove: revert single commit {label}',
                'forward_to_latest': 'restore: forward to latest',
            }[action]

            ci = subprocess.run(
                ['git'] + _GIT_OPTS + ['commit', '-m', msg, '--allow-empty'],
                capture_output=True, text=True, timeout=10
            )
            commit_hash = ''
            for ln in ci.stdout.splitlines():
                m = re.search(r'\b([0-9a-f]{7,})\b', ln)
                if m:
                    commit_hash = m.group(1)
                    break
            return {'ok': ci.returncode == 0, 'commit': commit_hash,
                    'output': ci.stdout + ci.stderr}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def list_source_files(self) -> list[dict]:
        out = []
        for f in sorted(_SOURCE_DOCS.iterdir()):
            if f.is_file():
                stat = f.stat()
                import datetime
                out.append({
                    'name': f.name,
                    'size_bytes': stat.st_size,
                    'modified_ts': datetime.datetime.utcfromtimestamp(stat.st_mtime).strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
        return out

    def delete_source_file(self, filename: str) -> dict:
        safe = Path(filename).name
        target = _SOURCE_DOCS / safe
        try:
            target.unlink()
            return {'ok': True, 'output': f'Deleted {safe}'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def upload_source_file(self, filename: str, data: bytes) -> dict:
        safe = Path(filename).name
        target = _SOURCE_DOCS / safe
        try:
            target.write_bytes(data)
            return {'ok': True, 'output': f'Uploaded {safe}'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def download_source_file(self, filename: str) -> tuple[bytes, str]:
        import mimetypes
        safe   = Path(filename).name
        target = _SOURCE_DOCS / safe
        if not target.exists():
            raise FileNotFoundError(safe)
        mime = mimetypes.guess_type(safe)[0] or 'application/octet-stream'
        return target.read_bytes(), mime

    def download_csv_file(self, table: str, filename: str) -> bytes:
        safe     = Path(filename).name
        dest_dir = _DPS_CSV_DIR if table == 'dpstriage' else _RCA_CSV_DIR
        target   = dest_dir / safe
        if not target.exists():
            raise FileNotFoundError(safe)
        return target.read_bytes()

    def list_csv_files(self) -> dict:
        import datetime
        out = {}
        for table, d in (('dpstriage', _DPS_CSV_DIR), ('postrca', _RCA_CSV_DIR)):
            files = []
            for f in sorted(d.glob('*.csv'), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = f.stat()
                files.append({
                    'name': f.name,
                    'size_bytes': stat.st_size,
                    'modified_ts': datetime.datetime.utcfromtimestamp(stat.st_mtime).strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
            out[table] = files
        return out

    def upload_csv_file(self, table: str, filename: str, data: bytes) -> dict:
        if table not in ('dpstriage', 'postrca'):
            return {'ok': False, 'output': 'invalid table'}
        dest_dir = _DPS_CSV_DIR if table == 'dpstriage' else _RCA_CSV_DIR
        ingest   = _INGEST_DPS  if table == 'dpstriage' else _INGEST_RCA
        safe     = Path(filename).name
        try:
            (dest_dir / safe).write_bytes(data)
        except Exception as e:
            return {'ok': False, 'output': str(e)}
        try:
            env = {**os.environ}
            result = subprocess.run(
                [_VENV_PY, str(ingest)],
                capture_output=True, text=True, timeout=120, env=env
            )
            return {'ok': result.returncode == 0, 'output': (result.stdout + result.stderr).strip()[-2000:]}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def kill_build(self) -> dict:
        """Kill the running build by sending SIGTERM then SIGKILL to the PID from the PID file."""
        import signal
        pid = None
        if _BUILD_PID.exists():
            try:
                pid = int(_BUILD_PID.read_text().strip())
            except (OSError, ValueError):
                pass
        if pid is None:
            # Fall back to pgrep
            try:
                out = subprocess.run(['pgrep', '-f', 'build_index.py'], capture_output=True, text=True, timeout=3)
                pids = [int(p) for p in out.stdout.split() if p.strip()]
                pid = pids[0] if pids else None
            except Exception:
                pass
        if pid is None:
            return {'ok': False, 'output': 'No running build found'}
        try:
            os.kill(pid, signal.SIGTERM)
            import time; time.sleep(2)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # already dead after SIGTERM
            _BUILD_PID.unlink(missing_ok=True)
            return {'ok': True, 'output': f'Killed build PID {pid}'}
        except ProcessLookupError:
            _BUILD_PID.unlink(missing_ok=True)
            return {'ok': False, 'output': f'PID {pid} not found — build may have already finished'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def trigger_build(self, force_full: bool, user_id: str) -> dict:
        flag = '--full ' if force_full else ''
        log  = '/tmp/dashboard_build.log'
        cmd  = f'nohup /srv/vpo_rag/mcp_server/scripts/run_build.sh {flag}--user={user_id} > {log} 2>&1 &'
        try:
            subprocess.Popen(
                ['bash', '-c', cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            return {'ok': True, 'output': 'Build started'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def get_build_status(self) -> dict:
        return _parse_build_status()

    def read_index_files(self) -> list[dict]:
        out = []
        for f in sorted(_DETAIL_DIR.glob('chunks.*.jsonl')):
            try:
                stat = f.stat()
                out.append({'name': f.name, 'size_bytes': stat.st_size, 'line_count': sum(1 for l in f.open(encoding='utf-8') if l.strip())})
            except OSError:
                pass
        return out

    def download_jira_db(self, table) -> tuple[bytes, str]:
        """Dump both MySQL tables into a fresh SQLite .db and return the bytes."""
        import sqlite3, datetime, tempfile, os
        mysql_pass = os.environ.get('MYSQL_PASS', '')
        try:
            import pymysql as mysql_connector
        except ImportError:
            raise RuntimeError('PyMySQL not installed')

        _COLUMNS = [
            'Key', 'Issue_id', 'Status', 'Assignee', 'Summary', 'Description',
            'Created', 'Updated', 'Priority', 'Platform_Affected', 'Root_Cause',
            'Resolution_Category', 'Requesting_Organization', 'Environment_HE_Controller',
            'Customer_Type', 'Customer_Impact', 'Last_Comment', 'Resolution_Mitigation',
            'Vertical',
        ]
        _DDL = """
            CREATE TABLE IF NOT EXISTS {table} (
                Key TEXT PRIMARY KEY,
                Issue_id TEXT, Status TEXT, Assignee TEXT, Summary TEXT, Description TEXT,
                Created TEXT, Updated TEXT, Priority TEXT, Platform_Affected TEXT,
                Root_Cause TEXT, Resolution_Category TEXT, Requesting_Organization TEXT,
                Environment_HE_Controller TEXT, Customer_Type TEXT, Customer_Impact TEXT,
                Last_Comment TEXT, Resolution_Mitigation TEXT, Vertical TEXT
            )
        """
        _SYNC_LOG_DDL = """
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at TEXT, remote_host TEXT, table_name TEXT,
                rows_synced INTEGER, duration_sec REAL, status TEXT, error TEXT
            )
        """

        def _dt(v):
            if v is None: return None
            from datetime import datetime as dt
            return v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, dt) else str(v)

        remote = mysql_connector.connect(
            host='localhost', port=3306,
            user='jira_user', password=mysql_pass,
            database='jira_db', connect_timeout=10,
        )
        try:
            # Build SQLite in a temp file (sqlite3 in-memory can't be read as bytes easily)
            tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            tmp.close()
            con = sqlite3.connect(tmp.name)
            cur = con.cursor()
            for t in ('dpstriage', 'postrca'):
                cur.execute(_DDL.format(table=t))
            cur.execute(_SYNC_LOG_DDL)
            con.commit()

            rcur = remote.cursor()
            cols_sql = ', '.join(f'`{c}`' for c in _COLUMNS)
            ph = ', '.join(['?'] * len(_COLUMNS))
            col_names = ', '.join(_COLUMNS)
            now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            for t in ('dpstriage', 'postrca'):
                rcur.execute(f'SELECT {cols_sql} FROM {t}')
                rows = rcur.fetchall()
                update_set = ', '.join(f'{c}=excluded.{c}' for c in _COLUMNS if c != 'Key')
                for row in rows:
                    cur.execute(
                        f'INSERT INTO {t} ({col_names}) VALUES ({ph}) '
                        f'ON CONFLICT(Key) DO UPDATE SET {update_set}',
                        tuple(_dt(v) for v in row)
                    )
                con.commit()
                cur.execute(
                    'INSERT INTO sync_log (synced_at, remote_host, table_name, rows_synced, duration_sec, status) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (now, 'localhost', t, len(rows), 0.0, 'ok')
                )
                con.commit()

            rcur.close()
            con.close()

            data = Path(tmp.name).read_bytes()
            filename = f'jira_local_{datetime.date.today().isoformat()}.db'
            return data, filename
        finally:
            remote.close()
            try: os.unlink(tmp.name)
            except Exception: pass

    def download_index_zip(self) -> bytes:
        """Zip all chunks.*.jsonl files from the detail directory."""
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(_DETAIL_DIR.glob('chunks.*.jsonl')):
                zf.write(f, f.name)
        return buf.getvalue()

    def delete_learned_chunk(self, chunk_id: str, user_id: str) -> dict:
        """Remove a chunk by ID from chunks.learned.jsonl and commit."""
        if not _LEARNED_FILE.exists():
            return {'ok': False, 'output': 'learned file not found'}
        lines = _LEARNED_FILE.read_text(encoding='utf-8').splitlines(keepends=True)
        new_lines = []
        removed = False
        for line in lines:
            if line.strip():
                try:
                    if json.loads(line).get('id') == chunk_id:
                        removed = True
                        continue
                except Exception:
                    pass
            new_lines.append(line)
        if not removed:
            return {'ok': False, 'output': f'chunk {chunk_id} not found'}
        _LEARNED_FILE.write_text(''.join(new_lines), encoding='utf-8')
        result = self.run_git_op(['add', 'chunks.learned.jsonl'])
        if not result['ok']:
            return result
        result = self.run_git_op(['commit', '-m', f'delete: {user_id} [{chunk_id}]'])
        import re
        commit = ''
        for ln in result['output'].splitlines():
            m = re.search(r'\b([0-9a-f]{7,})\b', ln)
            if m:
                commit = m.group(1)
                break
        return {'ok': result['ok'], 'commit': commit, 'output': result['output']}

    def write_learned_chunk_edit(self, chunk_id: str, new_text: str,
                                  new_tags: list, new_title: str, user_id: str) -> dict:
        """In-place edit of a learned chunk by ID. Returns {'ok': bool, 'commit': str}."""
        if not _LEARNED_FILE.exists():
            return {'ok': False, 'output': 'learned file not found'}
        lines = _LEARNED_FILE.read_text(encoding='utf-8').splitlines(keepends=True)
        updated = False
        new_lines = []
        for line in lines:
            if not line.strip():
                new_lines.append(line)
                continue
            try:
                rec = json.loads(line)
                if rec.get('id') == chunk_id:
                    rec['text_raw'] = new_text
                    rec['text'] = rec['text'].split('\n', 1)[0] + '\n' + new_text
                    rec['tags'] = new_tags
                    rec['metadata']['title'] = new_title
                    rec['metadata']['edited_by'] = user_id
                    import datetime
                    rec['metadata']['edited_ts'] = datetime.datetime.utcnow().isoformat() + 'Z'
                    new_lines.append(json.dumps(rec, ensure_ascii=False) + '\n')
                    updated = True
                else:
                    new_lines.append(line)
            except Exception:
                new_lines.append(line)
        if not updated:
            return {'ok': False, 'output': f'chunk {chunk_id} not found'}
        _LEARNED_FILE.write_text(''.join(new_lines), encoding='utf-8')
        result = self.run_git_op(['add', 'chunks.learned.jsonl'])
        if not result['ok']:
            return result
        result = self.run_git_op(['commit', '-m', f'edit: {user_id} [{chunk_id}]'])
        import re
        commit = ''
        for ln in result['output'].splitlines():
            m = re.search(r'\b([0-9a-f]{7,})\b', ln)
            if m:
                commit = m.group(1)
                break
        return {'ok': result['ok'], 'commit': commit, 'output': result['output']}
