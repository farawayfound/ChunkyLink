// modules/learned.js — Learned KB tab

let _learnedChart    = null;
let _learnedPage     = 1;
let _learnedPerPage  = 10;
let _learnedAll      = [];
let _learnedSort     = { col: null, dir: 'asc' };
let _learnedFilter   = { category: null };
let _learnedSearch   = { user_id: '', ticket_key: '', title: '' };
let _learnedCatVals  = [];
let _pendingRollback = null;
let _pendingDeleteId = null;
let _historyEntries  = [];

async function loadLearned() {
    await Promise.all([loadLearnedStats(), loadLearnedChunks(), loadLearnedHistory()]);
}

async function loadLearnedStats() {
    try {
        const r = await fetch('/api/learned/stats');
        const d = await r.json();
        if (d.error) { document.getElementById('learned-overview').innerHTML = `<span class="muted">${d.error}</span>`; return; }

        document.getElementById('learned-overview').innerHTML = `
            <div class="stat-row"><span>Total chunks</span><span class="stat-val">${d.chunk_count ?? 0}</span></div>
            <div class="stat-row"><span>File size</span><span class="stat-val">${_fmtBytes(d.file_size_bytes ?? 0)}</span></div>
            <div class="stat-row"><span>Last learned</span><span class="stat-val">${fmt(d.last_ts)}</span></div>
        `;

        const kpiEl = document.getElementById('kpi-learned');
        if (kpiEl) kpiEl.textContent = d.chunk_count ?? 0;

        const byDay = d.by_day || {};
        const days  = Object.keys(byDay).sort().slice(-8);
        if (_learnedChart) _learnedChart.destroy();
        _learnedChart = new Chart(document.getElementById('chart-learned-daily'), {
            type: 'bar',
            data: {
                labels: days,
                datasets: [{ label: 'Chunks added', data: days.map(d => byDay[d]), backgroundColor: '#a78bfa' }],
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { title: items => items[0].label } },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxRotation: 45 } },
                    y: { beginAtZero: true, ticks: { stepSize: 1, color: '#64748b' } },
                },
            },
        });
    } catch (e) {
        document.getElementById('learned-overview').innerHTML = `<span class="muted">Error: ${e}</span>`;
    }
}

function _buildLearnedToolbar() {
    const el = document.getElementById('learned-toolbar');
    if (!el) return;
    const catChecks = _learnedCatVals.map(v => {
        const chk = !_learnedFilter.category || _learnedFilter.category.has(v) ? 'checked' : '';
        return '<label><input type=\x22checkbox\x22 value=\x22' + v + '\x22 ' + chk + ' onchange=\x22_learnedFilterChange()\x22> ' + (v||'(blank)') + '</label>';
    }).join('');
    el.innerHTML = '<div class=\x22pager-toolbar\x22>' +
        '<div class=\x22pager-filter-wrap\x22><button class=\x22pager-filter-btn\x22 onclick=\x22_pagerTogglePanel(\x27lf-panel-cat\x27,event)\x22>Category \u25be</button>' +
        '<div class=\x22pager-filter-panel\x22 id=\x22lf-panel-cat\x22>' + catChecks + '</div></div>' +
        '<div class=\x22pager-search-wrap\x22><div class=\x22pager-search-label\x22>User</div>' +
        '<input type=\x22text\x22 placeholder=\x22Search user...\x22 oninput=\x22_learnedSearchChange(\x27user_id\x27,this.value)\x22></div>' +
        '<div class=\x22pager-search-wrap\x22><div class=\x22pager-search-label\x22>Ticket</div>' +
        '<input type=\x22text\x22 placeholder=\x22Search ticket...\x22 oninput=\x22_learnedSearchChange(\x27ticket_key\x27,this.value)\x22></div>' +
        '<div class=\x22pager-search-wrap\x22><div class=\x22pager-search-label\x22>Title</div>' +
        '<input type=\x22text\x22 placeholder=\x22Search title...\x22 oninput=\x22_learnedSearchChange(\x27title\x27,this.value)\x22></div>' +
        '</div>';
}

function _learnedFilterChange() {
    const panel = document.getElementById('lf-panel-cat');
    const checked = new Set([...panel.querySelectorAll('input:checked')].map(i => i.value));
    _learnedFilter.category = checked.size === _learnedCatVals.length ? null : checked;
    _learnedPage = 1; loadLearnedChunks();
}

function _learnedSearchChange(key, val) {
    _learnedSearch[key] = val; _learnedPage = 1; loadLearnedChunks();
}

async function loadLearnedChunks() {
    try {
        const r = await fetch(`/api/learned/chunks?page=${_learnedPage}&per_page=${_learnedPerPage}`);
        const d = await r.json();
        if (d.error) { document.getElementById('learned-tbody').innerHTML = `<tr><td colspan="7" class="muted center">${d.error}</td></tr>`; return; }

        _learnedAll = d;
        document.getElementById('learned-chunk-count').textContent =
            `${d.total} chunk${d.total !== 1 ? 's' : ''} \u2014 page ${_learnedPage} of ${Math.max(1, Math.ceil(d.total / _learnedPerPage))}`;

        if (!_learnedCatVals.length && d.chunks && d.chunks.length) {
            _learnedCatVals = [...new Set(d.chunks.map(c => c.category || ''))].sort();
            _buildLearnedToolbar();
        }

        let chunks = d.chunks || [];
        if (_learnedFilter.category) chunks = chunks.filter(c => _learnedFilter.category.has(c.category || ''));
        if (_learnedSearch.user_id)    chunks = chunks.filter(c => (c.user_id||'').toLowerCase().includes(_learnedSearch.user_id.toLowerCase()));
        if (_learnedSearch.ticket_key) chunks = chunks.filter(c => (c.ticket_key||'').toLowerCase().includes(_learnedSearch.ticket_key.toLowerCase()));
        if (_learnedSearch.title)      chunks = chunks.filter(c => (c.title||'').toLowerCase().includes(_learnedSearch.title.toLowerCase()));

        if (_learnedSort.col) {
            const k = _learnedSort.col, dir = _learnedSort.dir === 'asc' ? 1 : -1;
            chunks = [...chunks].sort((a, b) => String(a[k] ?? '').localeCompare(String(b[k] ?? '')) * dir);
        }

        window._learnedChunkMap = window._learnedChunkMap || {};
        chunks.forEach(c => { window._learnedChunkMap[c.id] = c; });

        const rows = chunks.map(c => {
            const rowId  = 'lc-' + c.id.replace(/[^a-zA-Z0-9]/g, '_');
            const safeId = c.id.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
            const titleHtml   = (c.title   || '\u2014').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            const previewHtml = (c.preview || '\u2014').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            return `
            <tr>
                <td class="mono">${fmt(c.session_ts)}</td>
                <td>${c.user_id || '\u2014'}</td>
                <td>${c.ticket_key ? `<span class="badge badge-search_jira">${c.ticket_key}</span>` : '\u2014'}</td>
                <td><span class="badge badge-${c.category || 'general'}">${c.category || '\u2014'}</span></td>
                <td class="truncate" style="max-width:120px" title="${titleHtml}">${titleHtml}</td>
                <td class="truncate muted" style="max-width:160px">${previewHtml}</td>
                <td style="white-space:nowrap">
                    <button class="btn btn-sm btn-ghost ev-expand-btn" title="Expand" onclick="toggleLearnedDetail('${rowId}')">&#x25BC;</button>
                    <button class="btn btn-sm btn-ghost" title="Edit" onclick="openEditById('${safeId}')">&#x270E;</button>
                    <button class="btn btn-sm btn-danger" title="Delete" onclick="confirmDeleteChunkById('${safeId}')">&#x1F5D1;</button>
                </td>
            </tr>
            <tr id="${rowId}" class="ev-detail-row" style="display:none">
                <td colspan="7"><pre class="ev-detail-pre" id="${rowId}-body"></pre></td>
            </tr>`;
        }).join('');
        document.getElementById('learned-tbody').innerHTML = rows ||
            '<tr><td colspan="7" class="muted center">No learned chunks yet</td></tr>';

        const pages = Math.max(1, Math.ceil(d.total / _learnedPerPage));
        let pg = '';
        if (pages > 1) {
            pg += `<button class="pg-btn" onclick="_learnedPage=1;loadLearnedChunks()" ${_learnedPage===1?'disabled':''}>«</button>`;
            pg += `<button class="pg-btn" onclick="_learnedPage--;loadLearnedChunks()" ${_learnedPage===1?'disabled':''}>‹</button>`;
            for (let p = Math.max(1,_learnedPage-3); p <= Math.min(pages,_learnedPage+3); p++)
                pg += `<button class="pg-btn ${p===_learnedPage?'pg-active':''}" onclick="_learnedPage=${p};loadLearnedChunks()">${p}</button>`;
            pg += `<button class="pg-btn" onclick="_learnedPage++;loadLearnedChunks()" ${_learnedPage===pages?'disabled':''}>›</button>`;
            pg += `<button class="pg-btn" onclick="_learnedPage=${pages};loadLearnedChunks()" ${_learnedPage===pages?'disabled':''}>»</button>`;
        }
        document.getElementById('learned-pagination').innerHTML = pg;

        document.querySelectorAll('#learned-table th[data-sort-key]').forEach(th => {
            th.removeAttribute('data-sort-dir');
            if (th.dataset.sortKey === _learnedSort.col) th.setAttribute('data-sort-dir', _learnedSort.dir);
            th.onclick = () => {
                const k = th.dataset.sortKey;
                if (_learnedSort.col === k) { _learnedSort.dir = _learnedSort.dir === 'asc' ? 'desc' : 'asc'; }
                else { _learnedSort.col = k; _learnedSort.dir = 'asc'; }
                loadLearnedChunks();
            };
        });
    } catch (e) {
        document.getElementById('learned-tbody').innerHTML = `<tr><td colspan="7" class="muted center">Error: ${e}</td></tr>`;
    }
}

// ── History pager ─────────────────────────────────────────────────────────────

const _historyPager = makePager(
    'learned-history-tbody', 'learned-history-pagination', 'learned-history-count', 10,
    (e) => {
        const isHead = e._idx === 0;
        const rowId  = `hist-${e.commit}`;
        return `
        <tr>
            <td class="mono">${e.commit.slice(0, 7)}</td>
            <td class="mono">${fmt(e.timestamp)}</td>
            <td class="truncate">${e.message}</td>
            <td style="white-space:nowrap">
                ${!isHead ? `<button class="btn btn-sm btn-ghost" onclick="confirmRollback('rollback_to', '${e.commit}', 'Roll back to: ${e.message.replace(/'/g,"\\'").replace(/"/g,'&quot;')} (${e.commit.slice(0,7)})')">Rollback here</button>` : '<span class="muted">HEAD</span>'}
                <button class="btn btn-sm btn-ghost ev-expand-btn" style="margin-left:24px" title="Show chunk detail" onclick="toggleHistCommit('${rowId}', '${e.commit}', this)">&#x25BC;</button>
            </td>
        </tr>
        <tr id="${rowId}" class="ev-detail-row" style="display:none">
            <td colspan="4" style="padding:0"><div id="${rowId}-body"><span class="muted" style="padding:10px 14px;display:block">Loading...</span></div></td>
        </tr>`;
    },
    '<tr><td colspan="4" class="muted center">No history yet</td></tr>'
);

async function loadLearnedHistory() {
    try {
        const r = await fetch('/api/learned/history');
        const d = await r.json();
        if (d.error) return;
        _historyEntries = d.history || [];
        const hasRollback = _historyEntries.length > 0 && _historyEntries[0].message.startsWith('rollback:');
        document.getElementById('btn-restore-latest').style.display = hasRollback ? '' : 'none';
        _historyPager.load(_historyEntries.map((e, i) => ({ ...e, _idx: i })), 'learned-history-table');
    } catch (e) {
        document.getElementById('learned-history-tbody').innerHTML =
            `<tr><td colspan="4" class="muted center">Error: ${e}</td></tr>`;
    }
}

async function toggleHistCommit(rowId, commit, btn) {
    const row  = document.getElementById(rowId);
    const body = document.getElementById(rowId + '-body');
    if (!row) return;
    const visible = row.style.display !== 'none';
    row.style.display = visible ? 'none' : '';
    btn.innerHTML = visible ? '&#x25BC;' : '&#x25B2;';
    if (visible || body.dataset.loaded) return;
    body.dataset.loaded = '1';
    try {
        const r = await fetch(`/api/learned/history/${commit}`);
        const d = await r.json();
        if (d.error) { body.innerHTML = `<span class="muted">Error: ${d.error}</span>`; return; }

        const snap = d.snapshot || {};
        const total = snap.total || 0;
        const byCat = snap.by_category || {};
        const catBadges = Object.entries(byCat)
            .sort((a, b) => b[1] - a[1])
            .map(([cat, n]) => `<span class="badge badge-${cat}" style="margin-right:4px">${cat}: ${n}</span>`)
            .join('');
        const statsHtml = `
            <div style="padding:8px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                <span style="font-size:12px;color:var(--muted);font-weight:600">KB at this commit:</span>
                <span style="font-weight:700;color:var(--accent)">${total} chunk${total !== 1 ? 's' : ''}</span>
                <span style="color:var(--border)">|</span>
                ${catBadges || '<span class="muted">no data</span>'}
            </div>`;

        let chunkHtml = '';
        if (!d.chunks || !d.chunks.length) {
            chunkHtml = `<div style="padding:10px 14px"><span class="muted">No chunk data in diff (rollback or merge commit).</span></div>`;
        } else {
            chunkHtml = d.chunks.map(c => {
                const title    = c.metadata?.title || '';
                const ticket   = c.metadata?.ticket_key || '';
                const user     = c.metadata?.user_id || '';
                const category = (c.tags || [])[0] || '';
                const text     = (c.text_raw || c.text || '').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                return `<div style="padding:10px 14px">
                    <div style="margin-bottom:6px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                        ${title ? `<strong>${title.replace(/</g,'&lt;')}</strong>` : ''}
                        ${ticket ? `<span class="badge badge-search_jira">${ticket}</span>` : ''}
                        ${category ? `<span class="badge badge-${category}">${category}</span>` : ''}
                        ${user ? `<span class="muted" style="font-size:11px">${user}</span>` : ''}
                    </div>
                    <pre style="margin:0;font-family:'Courier New',monospace;font-size:11px;color:#94a3b8;white-space:pre-wrap;word-break:break-all">${text}</pre>
                </div>`;
            }).join('<hr style="border-color:var(--border);margin:0">');
        }
        body.innerHTML = statsHtml + chunkHtml;
    } catch(e) {
        body.innerHTML = `<span class="muted">Error: ${e}</span>`;
    }
}

function toggleHistoryPanel() {
    const body = document.getElementById('learned-history-body');
    body.style.display = body.style.display === 'none' ? '' : 'none';
}

function toggleLearnedDetail(rowId) {
    const row  = document.getElementById(rowId);
    const body = document.getElementById(rowId + '-body');
    if (!row) return;
    const visible = row.style.display !== 'none';
    row.style.display = visible ? 'none' : '';
    const btn = row.previousElementSibling && row.previousElementSibling.querySelector('.ev-expand-btn');
    if (btn) btn.innerHTML = visible ? '&#x25BC;' : '&#x25B2;';
    if (!visible && body && !body.dataset.loaded) {
        body.dataset.loaded = '1';
        const c = window._learnedChunkMap && window._learnedChunkMap[
            Object.keys(window._learnedChunkMap).find(k =>
                'lc-' + k.replace(/[^a-zA-Z0-9]/g, '_') === rowId)
        ];
        body.textContent = c ? JSON.stringify(c, null, 2) : '(no data)';
    }
}

// ── Edit ──────────────────────────────────────────────────────────────────────

function openEditById(chunkId) {
    const c = window._learnedChunkMap && window._learnedChunkMap[chunkId];
    if (!c) { alert('Chunk not found \u2014 try refreshing.'); return; }
    openEdit(c);
}

function openEdit(chunk) {
    document.getElementById('edit-chunk-id').value  = chunk.id;
    document.getElementById('edit-title').value     = chunk.title || '';
    document.getElementById('edit-tags').value      = (chunk.tags || []).join(', ');
    document.getElementById('edit-text').value      = chunk.text_raw || '';
    document.getElementById('edit-inline-panel').style.display = '';
    document.getElementById('edit-inline-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeInlineEdit() {
    document.getElementById('edit-inline-panel').style.display = 'none';
}

async function submitEdit() {
    const id    = document.getElementById('edit-chunk-id').value;
    const text  = document.getElementById('edit-text').value.trim();
    const title = document.getElementById('edit-title').value.trim();
    const tags  = document.getElementById('edit-tags').value.split(',').map(t => t.trim()).filter(Boolean);
    if (!text) { alert('Text cannot be empty'); return; }
    try {
        const r = await fetch(`/api/learned/chunk/${encodeURIComponent(id)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, title, tags, user_id: 'dashboard' }),
        });
        const d = await r.json();
        if (!d.ok) { alert(`Edit failed: ${d.output || d.error}`); return; }
        closeInlineEdit();
        await loadLearned();
    } catch (e) {
        alert(`Edit error: ${e}`);
    }
}

// ── Delete ────────────────────────────────────────────────────────────────────

function confirmDeleteChunkById(chunkId) {
    const c = window._learnedChunkMap && window._learnedChunkMap[chunkId];
    confirmDeleteChunk(chunkId, (c && c.title) || chunkId);
}

function confirmDeleteChunk(chunkId, label) {
    _pendingDeleteId = chunkId;
    document.getElementById('delete-inline-msg').innerHTML =
        `Delete chunk: <strong>${String(label).replace(/</g,'&lt;')}</strong>?<br><span class="muted" style="font-size:12px">This cannot be undone. The chunk will be removed from the KB immediately.</span>`;
    document.getElementById('delete-inline-panel').style.display = '';
    document.getElementById('delete-inline-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeInlineDelete() {
    document.getElementById('delete-inline-panel').style.display = 'none';
    _pendingDeleteId = null;
}

async function executeDeleteChunk() {
    if (!_pendingDeleteId) return;
    const id = _pendingDeleteId;
    closeInlineDelete();
    try {
        const r = await fetch(`/api/learned/chunk/${encodeURIComponent(id)}`, { method: 'DELETE' });
        const d = await r.json();
        if (!d.ok) { alert(`Delete failed: ${d.output || d.error}`); return; }
        await loadLearned();
    } catch (e) {
        alert(`Delete error: ${e}`);
    }
}

// ── Rollback ──────────────────────────────────────────────────────────────────

function confirmRollback(action, commit, label) {
    _pendingRollback = { action, commit };
    const msgs = {
        rollback_to:       `This will revert chunks.learned.jsonl to the state at commit <strong>${commit.slice(0,7)}</strong>.<br><em>${label}</em>`,
        remove_single:     `This will remove the chunk: <strong>${label}</strong>`,
        forward_to_latest: `This will restore chunks.learned.jsonl to the latest state.`,
    };
    document.getElementById('rollback-modal-msg').innerHTML = msgs[action] || label;
    document.getElementById('rollback-confirm-btn').onclick = executeRollback;
    document.getElementById('rollback-modal').style.display = 'flex';
}

async function executeRollback() {
    if (!_pendingRollback) return;
    closeModal('rollback-modal');
    const { action, commit } = _pendingRollback;
    _pendingRollback = null;
    try {
        const r = await fetch('/api/learned/rollback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, commit }),
        });
        const d = await r.json();
        if (!d.ok) { alert(`Rollback failed: ${d.output || d.error}`); return; }
        await loadLearned();
    } catch (e) {
        alert(`Rollback error: ${e}`);
    }
}

async function learnedRollback(action, commit) {
    confirmRollback(action, commit, action === 'forward_to_latest' ? 'Restore to latest' : commit);
}
