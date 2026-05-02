// app.js — entry point: shared utilities + init
// Modules loaded before this file: pager.js, overview.js, events.js, errors.js, jiradb.js, jsonindex.js, learned.js

// ── Shared utilities ──────────────────────────────────────────────────────────

function showTab(name, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(name + '-tab').classList.add('active');
    btn.classList.add('active');
}

function fmt(ts) {
    if (!ts) return '\u2014';
    if (ts.endsWith('Z')) return ts.replace('T', ' ').replace('Z', ' UTC');
    return ts.replace('T', ' ').replace(/[+-]\d{4}$/, ' MT');
}

function fmtTerms(e) {
    if (e.terms && e.terms.length) return e.terms.join(', ');
    if (e.event === 'build_index') {
        const type    = e.force_full ? 'full rebuild' : 'incremental';
        const trigger = e.trigger ? ` [${e.trigger}]` : '';
        const files   = e.files_processed != null ? ` \u2014 ${e.files_processed} file${e.files_processed !== 1 ? 's' : ''} processed` : '';
        return `${type}${trigger}${files}`;
    }
    return '\u2014';
}

function fmtResult(e) {
    if (e.event === 'search_kb')   return `${e.chunks_returned ?? '?'} chunks (${e.level ?? ''})`;
    if (e.event === 'search_jira') return `dps=${e.dps_rows ?? '?'} rca=${e.rca_rows ?? '?'} [${e.source ?? '?'}] mode=${e.mode ?? '?'}`;
    if (e.event === 'build_index') {
        if (!e.chunks_by_category) return `exit ${e.exit_code ?? '?'}`;
        const parts = Object.entries(e.chunks_by_category).map(([k, v]) => `${k}:${v}`);
        return `exit ${e.exit_code ?? '?'} \u2014 ${parts.join(' \u00b7 ')}`;
    }
    if (e.event === 'learn')       return `${e.chunk_id ?? '?'} [${e.category ?? '?'}]`;
    if (e.event === 'request_end') return `HTTP ${e.http_status ?? '?'}`;
    return '\u2014';
}

function _fmtBytes(b) {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b/1024).toFixed(1)} KB`;
    return `${(b/1048576).toFixed(1)} MB`;
}

function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

// ── Server status ─────────────────────────────────────────────────────────────

async function loadServerStatus() {
    const badge = document.getElementById('server-status');
    try {
        const r = await fetch('/api/server-status');
        const d = await r.json();
        badge.textContent = d.active ? '\u25cf Active' : `\u25cf ${d.status}`;
        badge.className   = 'status-badge ' + (d.active ? 'status-active' : 'status-inactive');
    } catch {
        badge.textContent = '\u25cf Unreachable';
        badge.className   = 'status-badge status-inactive';
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function refreshAll() {
    await Promise.all([loadServerStatus(), loadStats(), loadEvents(), loadErrors(), loadJiraDb(), loadIndexTab(), loadLearned()]);
}

refreshAll();
