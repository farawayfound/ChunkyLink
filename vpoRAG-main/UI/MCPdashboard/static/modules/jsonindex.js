// modules/jsonindex.js — JSON Index tab

let _buildMonitorTimer = null;

const _buildPager = makePager('index-build-tbody', 'build-pagination', null, 10, e => {
    const rowId      = `bi-${(e.timestamp || '').replace(/[^a-zA-Z0-9]/g, '_')}`;
    const isOk       = (e.exit_code ?? 0) === 0;
    const typeBadge  = e.force_full
        ? `<span class="badge badge-build-full">Full</span>`
        : `<span class="badge badge-build-incr">Incremental</span>`;
    const trigBadge  = e.trigger ? `<span class="badge badge-build-trigger">${e.trigger}</span>` : '\u2014';
    const exitBadge  = isOk
        ? `<span class="badge badge-ingest-pass">${e.exit_code ?? 0}</span>`
        : `<span class="badge badge-ingest-fail">${e.exit_code ?? '?'}</span>`;
    const catSummary = e.chunks_by_category
        ? Object.entries(e.chunks_by_category).map(([k, v]) => `${k}:${v}`).join(' \u00b7 ') : '\u2014';
    const detail = JSON.stringify(e, null, 2);
    return `<tr>
        <td class="mono">${fmt(e.timestamp)}</td>
        <td>${typeBadge}</td>
        <td>${trigBadge}</td>
        <td>${e.user_id || '\u2014'}</td>
        <td>${e.files_processed != null ? e.files_processed : '\u2014'}</td>
        <td>${e.duration_ms != null ? e.duration_ms.toLocaleString() + ' ms' : '\u2014'}</td>
        <td>${exitBadge}</td>
        <td class="truncate muted" style="font-size:11px">${catSummary}</td>
        <td><button class="btn btn-sm btn-ghost ev-expand-btn" onclick="toggleEvDetail('${rowId}')">&#x25BC;</button></td>
    </tr>
    <tr id="${rowId}" class="ev-detail-row" style="display:none">
        <td colspan="9"><pre class="ev-detail-pre">${detail.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre></td>
    </tr>`;
}, '<tr><td colspan="9" class="muted center">No build events recorded yet</td></tr>',
{ toolbarId: 'build-toolbar',
  filters:  [{ key: 'type', label: 'Type' }, { key: 'trigger', label: 'Trigger' }, { key: 'exit_code', label: 'Exit' }],
  searches: [{ key: 'user_id', label: 'User' }, { key: 'categories', label: 'Categories' }] });

function _normBuildRows(rows) {
    return rows.map(e => Object.assign({}, e, {
        type:       e.force_full ? 'full' : 'incremental',
        categories: e.chunks_by_category
            ? Object.entries(e.chunks_by_category).map(([k,v]) => `${k}:${v}`).join(' ') : '',
    }));
}

const _srcPager = makePager('src-file-tbody', 'src-pagination', 'src-file-count', 20, f => {
    const escapedName = f.name.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    return '<tr>' +
        '<td class=\x22truncate\x22 style=\x22max-width:400px\x22 title=\x22' + escapedName + '\x22>' + escapedName + '</td>' +
        '<td style=\x22text-align:right;color:var(--muted);font-size:11px\x22>' + _fmtBytes(f.size_bytes) + '</td>' +
        '<td class=\x22mono\x22 style=\x22color:var(--muted)\x22>' + (f.modified_ts ? f.modified_ts.replace('T',' ').replace('Z','') : '\u2014') + '</td>' +
        '<td style=\x22white-space:nowrap\x22>' +
        '<a class=\x22btn btn-sm btn-ghost\x22 href=\x22/api/index/files/' + encodeURIComponent(f.name) + '\x22 download=\x22' + escapedName + '\x22 style=\x22margin-right:8px\x22>&#x2B07; Download</a>' +
        '<button class=\x22btn btn-sm btn-danger src-delete-btn\x22 data-filename=\x22' + escapedName + '\x22 title=\x22Delete\x22>&#x1F5D1;</button>' +
        '</td></tr>';
}, '<tr><td colspan=\x224\x22 class=\x22muted center\x22>No source files found</td></tr>',
{ toolbarId: 'src-toolbar',
  searches: [{ key: 'name', label: 'Filename' }] });

document.addEventListener('click', async e => {
    const btn = e.target.closest('.src-delete-btn');
    if (!btn) return;
    const filename = btn.dataset.filename;
    if (!confirm(`Delete "${filename}" from source_docs?\n\nNote: a FULL rebuild is required to remove this file's chunks from the index — an incremental build will not purge them.`)) return;
    btn.disabled = true;
    try {
        const r = await fetch(`/api/index/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const d = await r.json();
        if (!d.ok) { alert(`Delete failed: ${d.output || d.error}`); btn.disabled = false; return; }
        await _loadSourceFiles();
    } catch (ex) {
        alert(`Error: ${ex}`); btn.disabled = false;
    }
});

async function loadIndexTab() {
    await Promise.all([_loadIndexStats(), _loadSourceFiles(), _loadBuildMonitor()]);
}

async function _loadBuildMonitor() {
    try {
        const r = await fetch('/api/index/build-status');
        const d = await r.json();
        if (d.error) { document.getElementById('build-monitor-body').innerHTML = `<span class="muted">${d.error}</span>`; return; }
        _renderBuildMonitor(d);
        clearTimeout(_buildMonitorTimer);
        if (d.running) _buildMonitorTimer = setTimeout(_loadBuildMonitor, 5000);
    } catch (e) {
        document.getElementById('build-monitor-body').innerHTML = `<span class="muted">Error: ${e}</span>`;
    }
}

function _renderBuildMonitor(d) {
    const badge = document.getElementById('build-monitor-badge');
    const body  = document.getElementById('build-monitor-body');

    if (d.running) {
        badge.innerHTML = '<span class="badge badge-build_index" style="animation:pulse 1.5s infinite">&#9679; Running</span>';
    } else if (d.last_event === 'completed') {
        badge.innerHTML = '<span class="badge badge-ingest-pass">&#10003; Completed</span>';
    } else if (d.last_event === 'failed') {
        badge.innerHTML = '<span class="badge badge-ingest-fail">&#10007; Failed / Killed</span>';
    } else {
        badge.innerHTML = '<span class="muted" style="font-size:12px">No recent build</span>';
    }

    if (!d.log_lines && !d.running) {
        body.innerHTML = '<span class="muted">No build log found. Trigger a build to see live stats.</span>';
        return;
    }

    const elapsed = d.elapsed_s != null
        ? `${Math.floor(d.elapsed_s/60)}m ${d.elapsed_s%60}s`
        : (d.start_time ? '(calculating...)' : '\u2014');

    // Weighted overall progress based on measured full-build timing:
    // Extraction ~65%, cross-ref ~34%, writing ~1%
    let overallPct = 0;
    let phaseLabel = '';
    const phase = d.phase || 'extraction';
    if (phase === 'extraction') {
        const filePct = d.files_total > 0 ? d.files_processed / d.files_total : 0;
        overallPct = Math.round(filePct * 65);
        phaseLabel = `Extracting files (${d.files_processed}/${d.files_total})`;
    } else if (phase === 'cross_ref') {
        const xrefPct = d.xref_total > 0 ? d.xref_processed / d.xref_total : 0;
        overallPct = Math.round(65 + xrefPct * 34);
        phaseLabel = `Cross-referencing (${(d.xref_processed||0).toLocaleString()}/${(d.xref_total||0).toLocaleString()} chunks)`;
    } else if (phase === 'writing') {
        overallPct = 99;
        phaseLabel = 'Writing output files';
    }
    if (!d.running && d.last_event === 'completed') overallPct = 100;

    const barColor = !d.running
        ? (d.last_event === 'completed' ? 'var(--success)' : 'var(--error)')
        : 'var(--accent)';

    const progressBar = d.files_total > 0 ? `
        <div style="margin:4px 0 8px">
            <div class="bar-track" style="height:10px">
                <div class="bar-fill" style="width:${overallPct}%;background:${barColor};transition:width 1s ease"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:2px">
                <span>${phaseLabel}</span>
                <span>${overallPct}%</span>
            </div>
        </div>` : '';

    const _row  = (k, v) => `<div class="stat-row"><span>${k}</span><span class="stat-val" style="font-size:12px">${v}</span></div>`;
    const _row2 = (k1, v1, k2, v2) =>
        `<div class="stat-row-2col">
            <div class="stat-col"><span class="stat-key">${k1}</span><span class="stat-val" style="padding-right:10px">${v1}</span></div>
            <div class="stat-col"><span class="stat-key2">${k2}</span><span class="stat-val2">${v2}</span></div>
        </div>`;

    const typeBadge = d.force_full != null
        ? (d.force_full ? '<span class="badge badge-build-full">Full</span>' : '<span class="badge badge-build-incr">Incremental</span>')
        : '\u2014';
    const trigBadge = d.trigger ? `<span class="badge badge-build-trigger">${d.trigger}</span>` : '\u2014';

    const rows = [
        _row2('Build type', typeBadge,   'Elapsed',    elapsed),
        _row2('Trigger',    trigBadge,   'User',       d.user_id || '\u2014'),
        _row2('CPU',        d.cpu_pct != null ? `${d.cpu_pct}%` : '\u2014',
                            'Cores',    d.cores_used != null ? `${d.cores_used} / 16` : '\u2014'),
        _row2('Files done', d.files_processed || 0, 'Remaining', d.files_remaining || 0),
        _row('Start time',  d.start_time || '\u2014'),
        _row('RAM (RSS)',   d.rss_mb != null ? `${d.rss_mb} MB` : '\u2014'),
        _row('Current file', d.current_file
            ? `<span class="truncate" style="max-width:180px;display:inline-block;vertical-align:bottom" title="${d.current_file}">${d.current_file}</span>`
            : '\u2014'),
    ].join('');

    const stopBtn = d.running
        ? `<button class="btn btn-sm btn-danger" style="margin-top:8px;width:100%" onclick="killBuild()">&#x25A0; STOP Build</button>`
        : '';

    body.innerHTML = progressBar + rows + stopBtn;
}

async function _loadIndexStats() {
    try {
        const r = await fetch('/api/index/stats');
        const d = await r.json();
        if (d.error) {
            document.getElementById('index-overview').innerHTML = `<span class="muted">${d.error}</span>`;
            return;
        }

        const lastBuild = d.builds && d.builds.length ? d.builds[0] : null;
        document.getElementById('index-overview').innerHTML = `
            <div class="stat-row"><span>Total chunks</span><span class="stat-val">${(d.total_chunks || 0).toLocaleString()}</span></div>
            <div class="stat-row"><span>Total index size</span><span class="stat-val">${_fmtBytes(d.total_bytes || 0)}</span></div>
            <div class="stat-row"><span>Category files</span><span class="stat-val">${(d.categories || []).length}</span></div>
            <div class="stat-row"><span>Total builds logged</span><span class="stat-val">${d.total_builds || 0}</span></div>
            <div class="stat-row"><span>Last build</span><span class="stat-val">${lastBuild ? fmt(lastBuild.timestamp) : '\u2014'}</span></div>
            <div class="stat-row"><span>Last build type</span><span class="stat-val">${lastBuild ? (lastBuild.force_full ? 'Full' : 'Incremental') : '\u2014'}</span></div>
        `;

        const cats = (d.categories || []).sort((a, b) => b.chunks - a.chunks);
        const totalChunks = d.total_chunks || 1;
        const catRows = cats.map(c => {
            const pct = Math.round(c.chunks / totalChunks * 100);
            return `<tr>
                <td><span class="badge badge-${c.category}">${c.category}</span></td>
                <td style="text-align:right;font-weight:600">${c.chunks.toLocaleString()}</td>
                <td style="min-width:120px">
                    <div class="bar-track" style="margin:0"><div class="bar-fill" style="width:${pct}%"></div></div>
                </td>
                <td style="text-align:right;color:var(--muted);font-size:11px">${pct}%</td>
                <td style="text-align:right;color:var(--muted);font-size:11px">${_fmtBytes(c.size_bytes)}</td>
            </tr>`;
        }).join('');
        document.getElementById('index-category-table').innerHTML = `
            <table class="data-table">
                <thead><tr><th>Category</th><th style="text-align:right">Chunks</th><th>Distribution</th><th style="text-align:right">%</th><th style="text-align:right">Size</th></tr></thead>
                <tbody>${catRows || '<tr><td colspan="5" class="muted center">No index files found</td></tr>'}</tbody>
            </table>`;

        document.getElementById('index-build-count').textContent =
            `${d.total_builds} build event${d.total_builds !== 1 ? 's' : ''}`;

        _buildPager.load(_normBuildRows(d.builds || []), 'index-build-table');
    } catch (e) {
        document.getElementById('index-overview').innerHTML = `<span class="muted">Error: ${e}</span>`;
    }
}

async function _loadSourceFiles() {
    try {
        const r = await fetch('/api/index/files');
        const d = await r.json();
        if (d.error) {
            document.getElementById('src-file-tbody').innerHTML = '<tr><td colspan=\x224\x22 class=\x22muted center\x22>' + d.error + '</td></tr>';
            return;
        }
        _srcPager.load(d.files || [], 'src-file-table');
    } catch (e) {
        document.getElementById('src-file-tbody').innerHTML = '<tr><td colspan=\x224\x22 class=\x22muted center\x22>Error: ' + e + '</td></tr>';
    }
}

async function uploadSourceFiles(input) {
    const status = document.getElementById('src-upload-status');
    const files  = Array.from(input.files);
    if (!files.length) return;
    status.textContent = `Uploading ${files.length} file${files.length !== 1 ? 's' : ''}...`;
    let ok = 0, fail = 0;
    for (const file of files) {
        const fd = new FormData();
        fd.append('file', file);
        try {
            const r = await fetch('/api/index/files', { method: 'POST', body: fd });
            const d = await r.json();
            if (d.ok) ok++; else { fail++; console.warn(`Upload failed: ${file.name}`, d); }
        } catch (e) {
            fail++; console.warn(`Upload error: ${file.name}`, e);
        }
    }
    input.value = '';
    status.textContent = `Done \u2014 ${ok} uploaded${fail ? `, ${fail} failed` : ''}`;
    await _loadSourceFiles();
}

async function killBuild() {
    if (!confirm('Stop the running build?\n\nThe current file will be abandoned and partial output discarded. You will need to trigger a new build manually.')) return;
    try {
        const r = await fetch('/api/index/build/kill', { method: 'POST' });
        const d = await r.json();
        if (!d.ok) { alert(`Kill failed: ${d.output || d.error}`); return; }
        setTimeout(_loadBuildMonitor, 2000);
    } catch (e) {
        alert(`Error: ${e}`);
    }
}

async function triggerBuild(forceFull) {
    const userId = document.getElementById('build-user-id').value.trim() || 'dashboard';
    const label  = forceFull ? 'FULL REBUILD' : 'incremental build';
    if (!confirm(`Trigger a ${label} on the MCP server?\nUser: ${userId}`)) return;
    const status = document.getElementById('build-trigger-status');
    status.textContent = 'Starting build...';
    try {
        const r = await fetch('/api/index/build', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force_full: forceFull, user_id: userId }),
        });
        const d = await r.json();
        status.textContent = d.ok ? `\u2705 ${d.output}` : `\u274c ${d.output || d.error}`;
        if (d.ok) setTimeout(() => _loadIndexStats(), 5000);
    } catch (e) {
        status.textContent = `\u274c Error: ${e}`;
    }
}
