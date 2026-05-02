from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import subprocess
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime

# UI/Indexer/app.py → repo root is three levels up
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from indexers import config

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'vporag-dev-only-change-in-prod')
socketio = SocketIO(app, cors_allowed_origins="*")

_REPO_ROOT = Path(__file__).parent.parent.parent

@app.route('/')
def index():
    return render_template('index.html')

def parse_config():
    """Parse config.py into structured sections and fields"""
    config_path = _REPO_ROOT / 'indexers' / 'config.py'
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    sections = []
    current_section = None
    pending_comments = []
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('# ========='):
            if current_section:
                sections.append(current_section)
            section_name = stripped.replace('# =========', '').replace('=========', '').strip()
            current_section = {'name': section_name, 'fields': []}
            pending_comments = []
        
        elif stripped.startswith('#') and not stripped.startswith('# ===') and current_section:
            comment = stripped.lstrip('#').strip()
            if comment and not comment.startswith('-*-'):
                pending_comments.append(comment)
        
        elif '=' in stripped and not stripped.startswith('#') and current_section:
            match = re.match(r'^([A-Z_]+)\s*=\s*(.+)$', stripped)
            if match:
                current_section['fields'].append({
                    'name': match.group(1),
                    'value': match.group(2),
                    'comment': ' '.join(pending_comments) if pending_comments else ''
                })
                pending_comments = []
        
        elif not stripped:
            pending_comments = []
    
    if current_section:
        sections.append(current_section)
    
    return sections

def rebuild_config(sections):
    """Rebuild config.py from structured sections"""
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""',
        'Centralized Configuration for vpoRAG Indexer',
        'All paths and parameters are defined here.',
        '',
        'NOTE: DOC_PROFILES and CONTENT_TAGS are dynamically used by the indexing system.',
        'Modifying these will automatically update document classification and tagging behavior.',
        '"""',
        ''
    ]
    
    for section in sections:
        lines.append(f"# ========= {section['name']} =========")
        for field in section['fields']:
            if field.get('comment'):
                for comment_line in field['comment'].split('. '):
                    if comment_line.strip():
                        lines.append(f"# {comment_line.strip()}")
            lines.append(f"{field['name']} = {field['value']}")
            lines.append('')
    
    return '\n'.join(lines)

@app.route('/api/config', methods=['GET'])
def get_config():
    sections = parse_config()
    return jsonify({'sections': sections})

@app.route('/api/config', methods=['POST'])
def save_config():
    sections = request.json.get('sections', [])
    content = rebuild_config(sections)
    config_path = _REPO_ROOT / 'indexers' / 'config.py'
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'saved'})

@app.route('/api/stats')
def stats():
    try:
        state_path = Path(config.OUT_DIR) / 'state' / 'processing_state.json'
        state = {}
        if state_path.exists():
            with open(state_path, 'r') as f:
                state = json.load(f)
        
        detail_dir = Path(config.OUT_DIR) / 'detail'
        chunk_counts = {}
        total_chunks = 0
        
        if detail_dir.exists():
            for jsonl_file in detail_dir.glob('chunks.*.jsonl'):
                if jsonl_file.name == 'chunks.jsonl':
                    continue
                category = jsonl_file.stem.replace('chunks.', '')
                count = sum(1 for _ in open(jsonl_file, 'r', encoding='utf-8'))
                chunk_counts[category] = count
                total_chunks += count
        
        src_dir = Path(config.SRC_DIR)
        file_count = len(list(src_dir.rglob('*.*'))) if src_dir.exists() else 0
        
        log_path = Path(config.OUT_DIR) / 'logs' / 'build_index.log'
        last_build = 'Never'
        if log_path.exists():
            last_build = datetime.fromtimestamp(log_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            'src_dir': config.SRC_DIR,
            'out_dir': config.OUT_DIR,
            'file_count': file_count,
            'total_chunks': total_chunks,
            'chunk_counts': chunk_counts,
            'last_build': last_build,
            'state': state
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _run_script(script_path, done_msg):
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(script_path.parent)
    )
    for line in proc.stdout:
        socketio.emit('log', {'data': line.rstrip()})
    proc.wait()
    socketio.emit('log', {'data': f'\n=== {done_msg} (exit {proc.returncode}) ==='})
    socketio.emit('build_complete', {'status': 'done', 'code': proc.returncode})

@app.route('/api/build', methods=['POST'])
def build_index():
    socketio.start_background_task(
        _run_script, _REPO_ROOT / 'indexers' / 'build_index.py', 'Build completed')
    return jsonify({'status': 'started'})

@app.route('/api/rebuild', methods=['POST'])
def rebuild_all():
    def run_rebuild():
        state_path = Path(config.OUT_DIR) / 'state' / 'processing_state.json'
        if state_path.exists():
            state_path.unlink()
            socketio.emit('log', {'data': '=== Deleted processing state, forcing full rebuild ==='})
        _run_script(_REPO_ROOT / 'indexers' / 'build_index.py', 'Rebuild completed')
    socketio.start_background_task(run_rebuild)
    return jsonify({'status': 'started'})

@app.route('/api/build-incremental', methods=['POST'])
def build_incremental():
    socketio.start_background_task(
        _run_script, _REPO_ROOT / 'indexers' / 'scripts' / 'build_index_incremental.py',
        'Incremental indexing completed')
    return jsonify({'status': 'started'})

@app.route('/api/build-crossrefs-incremental', methods=['POST'])
def build_crossrefs_incremental():
    socketio.start_background_task(
        _run_script, _REPO_ROOT / 'indexers' / 'scripts' / 'build_cross_references_incremental.py',
        'Incremental cross-reference build completed')
    return jsonify({'status': 'started'})

@app.route('/api/logs')
def get_logs():
    log_path = Path(config.OUT_DIR) / 'logs' / 'build_index.log'
    if log_path.exists():
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return jsonify({'logs': ''.join(lines[-500:])})
    return jsonify({'logs': 'No logs available'})

if __name__ == '__main__':
    print("=" * 60)
    print("vpoRAG Control Panel")
    print("=" * 60)
    print(f"Source Directory: {config.SRC_DIR}")
    print(f"Output Directory: {config.OUT_DIR}")
    print(f"\nStarting server at http://localhost:5000")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
