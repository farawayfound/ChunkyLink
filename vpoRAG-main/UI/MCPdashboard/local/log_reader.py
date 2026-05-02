# -*- coding: utf-8 -*-
"""SshLogReader — fetches mcp_access.log from the MCP server via SSH."""
import subprocess, json, re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from base.log_reader import LogReader

_SSH_KEY    = str(Path.home() / '.ssh' / 'vporag_key')
_SSH_HOST   = 'vpomac@192.168.1.29'
_REMOTE_LOG = '/srv/vpo_rag/JSON/logs/mcp_access.log'
_DETAIL_DIR = '/srv/vpo_rag/JSON/detail'
_LEARNED    = f'{_DETAIL_DIR}/chunks.learned.jsonl'
_SSH_OPTS   = ['-i', _SSH_KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
               '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2']


_DPS_CSV_DIR  = '/srv/samba/share/dpstriageCSV'
_RCA_CSV_DIR  = '/srv/samba/share/postrcaCSV'
_INGEST_DPS   = '/srv/vpo_rag/mcp_server/scripts/ingest_jira_csv.py'
_INGEST_RCA   = '/srv/vpo_rag/mcp_server/scripts/ingest_postrca_csv.py'
_VENV_PY      = '/srv/vpo_rag/venv/bin/python'


def _ssh(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(['ssh'] + _SSH_OPTS + [_SSH_HOST, cmd],
                         capture_output=True, text=True, timeout=timeout)


class SshLogReader(LogReader):
    """Reads the remote log file over SSH — used when running on Windows."""

    def fetch_lines(self, max_lines: int = 5000) -> list[str]:
        remote_cmd = (
            f'for f in $(ls {_REMOTE_LOG}.* 2>/dev/null | sort); do cat "$f"; done; '
            f'cat {_REMOTE_LOG} 2>/dev/null'
        )
        result = _ssh(remote_cmd)
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        return lines[-max_lines:]

    def check_server_status(self) -> dict:
        try:
            result = _ssh('systemctl is-active vporag-mcp', timeout=12)
            active = result.stdout.strip() == 'active'
            return {'active': active, 'status': result.stdout.strip()}
        except Exception as e:
            return {'active': False, 'status': 'unreachable', 'error': str(e)}

    def read_learned_chunks(self) -> list[str]:
        try:
            result = _ssh(f'cat {_LEARNED} 2>/dev/null')
            return [l for l in result.stdout.splitlines() if l.strip()]
        except Exception:
            return []

    def run_git_log(self) -> str:
        try:
            result = _ssh(
                f'git -C {_DETAIL_DIR} log --format="%H|%ai|%s" -- chunks.learned.jsonl 2>&1'
            )
            return result.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_show(self, commit: str) -> str:
        try:
            result = _ssh(
                f'git -C {_DETAIL_DIR} show --unified=0 {commit} -- chunks.learned.jsonl 2>&1'
            )
            return result.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_show_file(self, commit: str) -> str:
        try:
            result = _ssh(
                f'git -C {_DETAIL_DIR} show {commit}:chunks.learned.jsonl 2>&1'
            )
            return result.stdout
        except Exception as e:
            return f'ERROR: {e}'

    def run_git_op(self, args: list[str]) -> dict:
        git_args = ' '.join(f'"{a}"' for a in args)
        try:
            result = _ssh(f'git -C {_DETAIL_DIR} {git_args} 2>&1', timeout=30)
            return {'ok': result.returncode == 0, 'output': result.stdout}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def restore_learned_to_commit(self, action: str, commit: str) -> dict:
        """Safely restore chunks.learned.jsonl via SSH without git revert."""
        try:
            if action == 'rollback_to':
                target = commit
            elif action == 'remove_single':
                target = f'{commit}^'
            elif action == 'forward_to_latest':
                target = 'HEAD'
            else:
                return {'ok': False, 'output': f'unknown action: {action}'}

            label = commit[:7] if commit else 'HEAD'
            msg = {
                'rollback_to':       f'rollback: restore to {label}',
                'remove_single':     f'remove: revert single commit {label}',
                'forward_to_latest': 'restore: forward to latest',
            }[action]

            # Single SSH call: show file at target, write it, stage, commit
            cmd = (
                f'git -C {_DETAIL_DIR} show {target}:chunks.learned.jsonl'
                f' > {_LEARNED} &&'
                f' git -C {_DETAIL_DIR} add chunks.learned.jsonl &&'
                f' git -C {_DETAIL_DIR} commit -m \'{msg}\' --allow-empty 2>&1'
            )
            result = _ssh(cmd, timeout=30)
            ok = result.returncode == 0
            commit_hash = ''
            for ln in result.stdout.splitlines():
                m = re.search(r'\b([0-9a-f]{7,})\b', ln)
                if m:
                    commit_hash = m.group(1)
                    break
            return {'ok': ok, 'commit': commit_hash, 'output': result.stdout}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def list_source_files(self) -> list[dict]:
        try:
            result = _ssh(
                'for f in /srv/vpo_rag/source_docs/*; do '
                '[ -f "$f" ] && echo "$(basename "$f")|$(wc -c < "$f")|$(date -r "$f" +%Y-%m-%dT%H:%M:%SZ)"; '
                'done 2>/dev/null'
            )
            out = []
            for line in result.stdout.splitlines():
                parts = line.strip().split('|')
                if len(parts) == 3:
                    out.append({'name': parts[0], 'size_bytes': int(parts[1].strip()), 'modified_ts': parts[2]})
            return out
        except Exception:
            return []

    def delete_source_file(self, filename: str) -> dict:
        # Sanitise — no path traversal
        safe = Path(filename).name
        try:
            result = _ssh(f'rm -f /srv/vpo_rag/source_docs/{safe!r} 2>&1')
            return {'ok': result.returncode == 0, 'output': result.stdout.strip()}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def upload_source_file(self, filename: str, data: bytes) -> dict:
        import tempfile, os
        safe = Path(filename).name
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe).suffix) as tf:
            tf.write(data)
            tmp = tf.name
        try:
            scp = subprocess.run(
                ['scp'] + _SSH_OPTS + [tmp, f'{_SSH_HOST}:/srv/vpo_rag/source_docs/{safe}'],
                capture_output=True, timeout=120
            )
            if scp.returncode != 0:
                return {'ok': False, 'output': scp.stderr.decode(errors='replace')}
            # Fix ownership
            _ssh(f'chown vporag:vporag /srv/vpo_rag/source_docs/{safe!r} 2>&1')
            return {'ok': True, 'output': f'Uploaded {safe}'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}
        finally:
            os.unlink(tmp)

    def download_source_file(self, filename: str) -> tuple[bytes, str]:
        import mimetypes, tempfile, os
        safe = Path(filename).name
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe).suffix) as tf:
            tmp = tf.name
        try:
            r = subprocess.run(
                ['scp'] + _SSH_OPTS + [f'{_SSH_HOST}:/srv/vpo_rag/source_docs/{safe}', tmp],
                capture_output=True, timeout=120
            )
            if r.returncode != 0:
                raise FileNotFoundError(safe)
            data = Path(tmp).read_bytes()
            mime = mimetypes.guess_type(safe)[0] or 'application/octet-stream'
            return data, mime
        finally:
            os.unlink(tmp)

    def download_csv_file(self, table: str, filename: str) -> bytes:
        import tempfile, os
        safe     = Path(filename).name
        dest_dir = _DPS_CSV_DIR if table == 'dpstriage' else _RCA_CSV_DIR
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tf:
            tmp = tf.name
        try:
            r = subprocess.run(
                ['scp'] + _SSH_OPTS + [f'{_SSH_HOST}:{dest_dir}/{safe}', tmp],
                capture_output=True, timeout=60
            )
            if r.returncode != 0:
                raise FileNotFoundError(safe)
            return Path(tmp).read_bytes()
        finally:
            os.unlink(tmp)

    def list_csv_files(self) -> dict:
        out = {}
        for table, d in (('dpstriage', _DPS_CSV_DIR), ('postrca', _RCA_CSV_DIR)):
            result = _ssh(
                f'for f in {d}/*.csv; do '
                f'[ -f "$f" ] && echo "$(basename "$f")|$(wc -c < "$f")|$(date -r "$f" +%Y-%m-%dT%H:%M:%SZ)"; '
                f'done 2>/dev/null'
            )
            files = []
            for line in result.stdout.splitlines():
                parts = line.strip().split('|')
                if len(parts) == 3:
                    files.append({'name': parts[0], 'size_bytes': int(parts[1].strip()), 'modified_ts': parts[2]})
            out[table] = sorted(files, key=lambda f: f['modified_ts'], reverse=True)
        return out

    def upload_csv_file(self, table: str, filename: str, data: bytes) -> dict:
        import tempfile, os
        if table not in ('dpstriage', 'postrca'):
            return {'ok': False, 'output': 'invalid table'}
        dest_dir = _DPS_CSV_DIR if table == 'dpstriage' else _RCA_CSV_DIR
        ingest   = _INGEST_DPS  if table == 'dpstriage' else _INGEST_RCA
        safe     = Path(filename).name
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tf:
            tf.write(data)
            tmp = tf.name
        try:
            scp = subprocess.run(
                ['scp'] + _SSH_OPTS + [tmp, f'{_SSH_HOST}:{dest_dir}/{safe}'],
                capture_output=True, timeout=60
            )
            if scp.returncode != 0:
                return {'ok': False, 'output': scp.stderr.decode(errors='replace')}
            result = _ssh(f'MYSQL_PASS=$(grep MYSQL_PASS /etc/vporag/mcp.env | cut -d= -f2) {_VENV_PY} {ingest} 2>&1', timeout=120)
            return {'ok': result.returncode == 0, 'output': result.stdout.strip()[-2000:]}
        except Exception as e:
            return {'ok': False, 'output': str(e)}
        finally:
            os.unlink(tmp)

    def trigger_build(self, force_full: bool, user_id: str) -> dict:
        flag = '--full ' if force_full else ''
        try:
            result = _ssh(
                f'nohup /srv/vpo_rag/mcp_server/scripts/run_build.sh {flag}--user={user_id} '
                f'> /tmp/dashboard_build.log 2>&1 & echo $!',
                timeout=15
            )
            pid = result.stdout.strip()
            return {'ok': True, 'output': f'Build started (PID {pid})'}
        except Exception as e:
            return {'ok': False, 'output': str(e)}

    def get_build_status(self) -> dict:
        import tempfile, os
        script = r"""
import subprocess, json, os, re, time
from pathlib import Path
BUILD_LOG = Path('/tmp/dashboard_build.log')
result = {
    'running': False, 'pid': None, 'start_time': None, 'elapsed_s': None,
    'cpu_pct': None, 'rss_mb': None, 'files_processed': 0, 'files_total': 0,
    'files_remaining': 0, 'current_file': None, 'force_full': None,
    'user_id': None, 'trigger': 'dashboard', 'log_lines': 0, 'last_event': None,
}
if BUILD_LOG.exists():
    lines = BUILD_LOG.read_text(encoding='utf-8', errors='replace').splitlines()
    result['log_lines'] = len(lines)
    for line in lines:
        m = re.search(r'--user=(\S+)', line)
        if m: result['user_id'] = m.group(1)
        if 'Force full rebuild' in line: result['force_full'] = True
        m = re.search(r'Processing (\d+) files', line)
        if m: result['files_total'] = int(m.group(1))
        m = re.search(r'Processing \[auto\] .+/([^/]+)$', line)
        if m: result['current_file'] = m.group(1)
        m = re.search(r'Start:\s+(.+)', line)
        if m: result['start_time'] = m.group(1).strip()
    result['files_processed'] = sum(1 for l in lines if 'Processing [auto]' in l)
    result['files_remaining'] = max(0, result['files_total'] - result['files_processed'])
    out = subprocess.run(['pgrep','-f','build_index.py'], capture_output=True, text=True, timeout=3)
    pids = [int(p) for p in out.stdout.split() if p.strip()]
    if pids:
        pid = pids[0]
        result['running'] = True; result['pid'] = pid
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            for sl in status.splitlines():
                if sl.startswith('VmRSS:'): result['rss_mb'] = round(int(sl.split()[1])/1024,1)
        except: pass
        try:
            stat = Path(f'/proc/{pid}/stat').read_text().split()
            hz = os.sysconf('SC_CLK_TCK')
            boot = int([l for l in Path('/proc/stat').read_text().splitlines() if l.startswith('btime')][0].split()[1])
            start_epoch = boot + int(stat[21])/hz
            elapsed = time.time() - start_epoch
            result['elapsed_s'] = round(elapsed)
            result['cpu_pct'] = round((int(stat[13])+int(stat[14]))/hz/elapsed*100,1) if elapsed>0 else 0
        except: pass
    else:
        result['last_event'] = 'completed' if any('BUILD COMPLETE' in l for l in lines) else ('failed' if lines else None)
print(json.dumps(result))
"""
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as tf:
            tf.write(script)
            tmp = tf.name
        try:
            scp = subprocess.run(
                ['scp'] + _SSH_OPTS + [tmp, f'{_SSH_HOST}:/tmp/_build_status.py'],
                capture_output=True, timeout=15
            )
            if scp.returncode != 0:
                return {'running': False, 'last_event': 'error'}
            result = _ssh('/srv/vpo_rag/venv/bin/python /tmp/_build_status.py 2>/dev/null', timeout=15)
            return json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as e:
            return {'running': False, 'last_event': 'error', 'error': str(e)}
        finally:
            os.unlink(tmp)

    def read_index_files(self) -> list[dict]:
        try:
            result = _ssh(
                f'for f in {_DETAIL_DIR}/chunks.*.jsonl; do '
                f'[ -f "$f" ] && echo "$f|$(wc -c < "$f")|$(wc -l < "$f")"; done 2>/dev/null'
            )
            out = []
            for line in result.stdout.splitlines():
                parts = line.strip().split('|')
                if len(parts) == 3:
                    name = parts[0].split('/')[-1]
                    out.append({'name': name, 'size_bytes': int(parts[1].strip()), 'line_count': int(parts[2].strip())})
            return out
        except Exception:
            return []

    def delete_learned_chunk(self, chunk_id: str, user_id: str) -> dict:
        """Remove a chunk by ID via SSH patch script."""
        import tempfile, os
        payload = json.dumps({'chunk_id': chunk_id, 'user_id': user_id})
        script = (
            'import json,subprocess\n'
            'from pathlib import Path\n'
            f'p = Path("{_LEARNED}")\n'
            'payload = json.loads(__import__("sys").argv[1])\n'
            'lines = p.read_text(encoding="utf-8").splitlines(keepends=True)\n'
            'out, removed = [], False\n'
            'for line in lines:\n'
            '    if line.strip():\n'
            '        try:\n'
            '            if json.loads(line).get("id") == payload["chunk_id"]:\n'
            '                removed = True; continue\n'
            '        except: pass\n'
            '    out.append(line)\n'
            'if removed:\n'
            '    p.write_text("".join(out), encoding="utf-8")\n'
            f'    subprocess.run(["git","-C","{_DETAIL_DIR}","add","chunks.learned.jsonl"])\n'
            f'    r=subprocess.run(["git","-C","{_DETAIL_DIR}","commit","-m",f\'delete: {{payload[\"user_id\"]}} [{{payload[\"chunk_id\"]}}]\'],capture_output=True,text=True)\n'
            '    import re; m=re.search(r"\\b([0-9a-f]{7,})\\b",r.stdout)\n'
            '    print(json.dumps({"ok":True,"commit":m.group(1) if m else ""}))\n'
            'else: print(json.dumps({"ok":False,"output":"chunk not found"}))\n'
        )
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as tf:
            tf.write(script)
            tmp = tf.name
        try:
            scp = subprocess.run(
                ['scp'] + _SSH_OPTS + [tmp, f'{_SSH_HOST}:/tmp/_learn_delete.py'],
                capture_output=True, timeout=15
            )
            if scp.returncode != 0:
                return {'ok': False, 'output': 'scp failed'}
            result = _ssh(
                f"/srv/vpo_rag/venv/bin/python /tmp/_learn_delete.py '{payload}' 2>&1"
            )
            try:
                return json.loads(result.stdout.strip().splitlines()[-1])
            except Exception:
                return {'ok': False, 'output': result.stdout}
        finally:
            os.unlink(tmp)

    def download_jira_db(self, table) -> tuple[bytes, str]:
        """Dump both Jira MySQL tables into a SQLite .db via SSH and return (bytes, filename)."""
        import tempfile, os, datetime
        filename = f'jira_local_{datetime.date.today().isoformat()}.db'
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tf:
            tmp = tf.name
        try:
            script = (
                'import sqlite3, subprocess, json, os\n'
                'from pathlib import Path\n'
                'MYSQL_PASS = subprocess.check_output(["sh","-c","grep MYSQL_PASS /etc/vporag/mcp.env | cut -d= -f2"]).decode().strip()\n'
                'import sys; sys.path.insert(0, "/srv/vpo_rag")\n'
                'db_path = "/tmp/_jira_export.db"\n'
                'conn = sqlite3.connect(db_path)\n'
                'try:\n'
                '    import mysql.connector\n'
                '    my = mysql.connector.connect(host="127.0.0.1",user="jira_user",password=MYSQL_PASS,database="jira_db")\n'
                '    cur = my.cursor()\n'
                '    for tbl in ("dpstriage_tickets","postrca_tickets"):\n'
                '        cur.execute(f"SELECT * FROM {tbl}")\n'
                '        cols = [d[0] for d in cur.description]\n'
                '        rows = cur.fetchall()\n'
                '        conn.execute(f"CREATE TABLE IF NOT EXISTS {tbl} ({\',\'.join(cols)})"  )\n'
                '        conn.executemany(f"INSERT OR REPLACE INTO {tbl} VALUES ({\',\'.join([\'?\']*len(cols))})", rows)\n'
                '    conn.commit()\n'
                '    my.close()\n'
                'finally: conn.close()\n'
                'print("ok")\n'
            )
            with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as sf:
                sf.write(script)
                stmp = sf.name
            try:
                subprocess.run(['scp'] + _SSH_OPTS + [stmp, f'{_SSH_HOST}:/tmp/_jira_dump.py'], capture_output=True, timeout=15)
                result = _ssh('/srv/vpo_rag/venv/bin/python /tmp/_jira_dump.py 2>&1', timeout=60)
                if 'ok' not in result.stdout:
                    raise RuntimeError(result.stdout[:200])
                r = subprocess.run(['scp'] + _SSH_OPTS + [f'{_SSH_HOST}:/tmp/_jira_export.db', tmp], capture_output=True, timeout=60)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.decode(errors='replace'))
                return Path(tmp).read_bytes(), filename
            finally:
                os.unlink(stmp)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def download_index_zip(self) -> bytes:
        """Return a zip of all chunks.*.jsonl files from the server detail directory."""
        import tempfile, os, zipfile, io
        result = _ssh(
            f'for f in {_DETAIL_DIR}/chunks.*.jsonl; do [ -f "$f" ] && echo "$f"; done 2>/dev/null'
        )
        paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for remote_path in paths:
                name = remote_path.split('/')[-1]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as tf:
                    tmp = tf.name
                try:
                    r = subprocess.run(
                        ['scp'] + _SSH_OPTS + [f'{_SSH_HOST}:{remote_path}', tmp],
                        capture_output=True, timeout=60
                    )
                    if r.returncode == 0:
                        zf.write(tmp, name)
                finally:
                    os.unlink(tmp)
        return buf.getvalue()

    def write_learned_chunk_edit(self, chunk_id: str, new_text: str,
                                  new_tags: list, new_title: str, user_id: str) -> dict:
        """Edit a learned chunk via SSH: SCP a patch script, run it remotely."""
        import tempfile, os
        payload = json.dumps({
            'chunk_id': chunk_id, 'new_text': new_text,
            'new_tags': new_tags, 'new_title': new_title, 'user_id': user_id,
        })
        script = (
            'import json,sys,datetime,re,subprocess\n'
            'from pathlib import Path\n'
            f'p = Path("{_LEARNED}")\n'
            'payload = json.loads(sys.argv[1])\n'
            'lines = p.read_text(encoding="utf-8").splitlines(keepends=True)\n'
            'out = []\n'
            'updated = False\n'
            'for line in lines:\n'
            '    if not line.strip(): out.append(line); continue\n'
            '    try:\n'
            '        rec = json.loads(line)\n'
            '        if rec.get("id") == payload["chunk_id"]:\n'
            '            rec["text_raw"] = payload["new_text"]\n'
            '            rec["text"] = rec["text"].split("\\n",1)[0]+"\\n"+payload["new_text"]\n'
            '            rec["tags"] = payload["new_tags"]\n'
            '            rec["metadata"]["title"] = payload["new_title"]\n'
            '            rec["metadata"]["edited_by"] = payload["user_id"]\n'
            '            rec["metadata"]["edited_ts"] = datetime.datetime.utcnow().isoformat()+"Z"\n'
            '            out.append(json.dumps(rec,ensure_ascii=False)+"\\n")\n'
            '            updated = True\n'
            '        else: out.append(line)\n'
            '    except: out.append(line)\n'
            'if updated:\n'
            '    p.write_text("".join(out),encoding="utf-8")\n'
            f'    subprocess.run(["git","-C","{_DETAIL_DIR}","add","chunks.learned.jsonl"])\n'
            f'    r=subprocess.run(["git","-C","{_DETAIL_DIR}","commit","-m",f\'edit: {{payload[\"user_id\"]}} [{{payload[\"chunk_id\"]}}]\'],capture_output=True,text=True)\n'
            '    m=re.search(r"\\b([0-9a-f]{7,})\\b",r.stdout)\n'
            '    print(json.dumps({"ok":True,"commit":m.group(1) if m else ""}))\n'
            'else: print(json.dumps({"ok":False,"output":"chunk not found"}))\n'
        )
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as tf:
            tf.write(script)
            tmp = tf.name
        try:
            scp = subprocess.run(
                ['scp'] + _SSH_OPTS + [tmp, f'{_SSH_HOST}:/tmp/_learn_edit.py'],
                capture_output=True, timeout=15
            )
            if scp.returncode != 0:
                return {'ok': False, 'output': 'scp failed'}
            result = _ssh(
                f"/srv/vpo_rag/venv/bin/python /tmp/_learn_edit.py '{payload}' 2>&1"
            )
            try:
                return json.loads(result.stdout.strip().splitlines()[-1])
            except Exception:
                return {'ok': False, 'output': result.stdout}
        finally:
            os.unlink(tmp)
