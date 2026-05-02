// modules/jiradb.js — Jira Database tab

const _CSV_REQUIRED = {
    dpstriage: ['Issue key','Issue id','Summary','Status','Updated','Created',
                'Custom field (Resolution Category)','Custom field (Last Comment)'],
    postrca:   ['Issue key','Issue id','Summary','Status','Updated','Created',
                'Custom field (Resolution / Mitigation Solution)'],
};

const _jiradbPager = makePager('jiradb-tbody', 'jiradb-pagination', 'jiradb-count', 10, e => {
    const isPas  = e.status === 'pass';
    const badge  = isPas ? `<span class="badge badge-ingest-pass">pass</span>` : `<span class="badge badge-ingest-fail">fail</span>`;
    const rowCls = isPas ? '' : 'row-error';
    return `<tr class="${rowCls}">
        <td class="mono">${fmt(e.timestamp)}</td>
        <td><span class="badge badge-${e.table === 'dpstriage' ? 'search_jira' : 'build_index'}">${(e.table || '\u2014').toUpperCase()}</span></td>
        <td>${badge}</td>
        <td>${e.rows_updated ?? '\u2014'}</td>
        <td>${e.rows_inserted ?? '\u2014'}</td>
        <td>${e.total_rows != null ? e.total_rows.toLocaleString() : '\u2014'}</td>
        <td class="mono truncate">${e.filename || (e.error ? e.error : '\u2014')}</td>
    </tr>`;
}, '<tr><td colspan="7" class="muted center">No ingest events recorded yet</td></tr>',
{ toolbarId: 'jiradb-toolbar',
  filters:  [{ key: 'table', label: 'Table' }, { key: 'status', label: 'Status' }],
  searches: [{ key: 'filename', label: 'Filename' }] });

async function loadJiraDb() {
    await Promise.all([_loadJiraIngestHistory(), _loadJiraCsvFiles()]);
}

async function _loadJiraIngestHistory() {
    const r = await fetch('/api/jira-db');
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) return;
    _jiradbPager.load(d.ingests, 'jiradb-table');
}

async function _loadJiraCsvFiles() {
    try {
        const r = await fetch('/api/jira/csv-files');
        const d = await r.json();
        if (d.error) return;
        for (const [table, tbodyId] of [['dpstriage','dps-csv-tbody'],['postrca','rca-csv-tbody']]) {
            const files = d[table] || [];
            const rows  = files.map((f, i) => {
                const isLatest = i === 0;
                return `<tr${isLatest ? ' style="background:rgba(79,142,247,.06)"' : ''}>
                    <td class="truncate" style="max-width:280px" title="${f.name}">
                        ${isLatest ? '<span class="badge badge-ingest-pass" style="margin-right:4px">latest</span>' : ''}
                        ${f.name}
                    </td>
                    <td style="text-align:right;color:var(--muted);font-size:11px">${_fmtBytes(f.size_bytes)}</td>
                    <td class="mono" style="color:var(--muted)">${(f.modified_ts||'').replace('T',' ').replace('Z','')}</td>
                    <td><a class="btn btn-sm btn-ghost" href="/api/jira/csv-download/${table}/${encodeURIComponent(f.name)}" download="${f.name}" title="Download">&#x2B07;</a></td>
                </tr>`;
            }).join('');
            document.getElementById(tbodyId).innerHTML =
                rows || `<tr><td colspan="3" class="muted center">No CSV files found</td></tr>`;
        }
    } catch (e) { console.warn('_loadJiraCsvFiles:', e); }
}

async function _validateCsv(file, table) {
    return new Promise(resolve => {
        const fr = new FileReader();
        fr.onload = e => {
            const firstLn  = e.target.result.split('\n')[0].replace(/^\uFEFF/, '');
            const headers  = firstLn.match(/(?:"[^"]*"|[^,])+/g)
                                    ?.map(h => h.trim().replace(/^"|"$/g, '')) || [];
            const required = _CSV_REQUIRED[table] || [];
            const missing  = required.filter(c => !headers.includes(c));
            const rowCount = e.target.result.split('\n').length - 2;
            resolve({ ok: missing.length === 0, missing, headers, rowCount });
        };
        fr.readAsText(file);
    });
}

async function uploadJiraCsv(table, input) {
    const file     = input.files[0];
    const prefix   = table === 'dpstriage' ? 'dps' : 'rca';
    const statusEl = document.getElementById(`${prefix}-upload-status`);
    if (!file) return;
    input.value = '';

    statusEl.style.color = 'var(--muted)';
    statusEl.textContent = 'Validating columns...';
    const check = await _validateCsv(file, table);
    if (!check.ok) {
        statusEl.style.color = 'var(--error)';
        statusEl.textContent = `\u274c Missing columns: ${check.missing.join(', ')}`;
        return;
    }
    statusEl.style.color = 'var(--muted)';
    statusEl.textContent = `\u2713 ${check.headers.length} columns, ~${check.rowCount} rows \u2014 uploading & ingesting...`;

    const fd = new FormData();
    fd.append('table', table);
    fd.append('file', file);
    try {
        const r = await fetch('/api/jira/csv-upload', { method: 'POST', body: fd });
        const d = await r.json();
        if (d.ok) {
            statusEl.style.color = 'var(--success)';
            statusEl.textContent = '\u2705 Uploaded & ingested';
            document.getElementById('ingest-modal-title').textContent =
                `Ingest Result \u2014 ${table.toUpperCase()} \u2014 ${file.name}`;
            document.getElementById('ingest-modal-output').textContent = d.output || '(no output)';
            document.getElementById('ingest-modal').style.display = 'flex';
            await Promise.all([_loadJiraCsvFiles(), _loadJiraIngestHistory()]);
        } else {
            statusEl.style.color = 'var(--error)';
            const msg = d.error || d.output || 'Upload failed';
            statusEl.textContent = `\u274c ${msg.slice(0, 160)}`;
            if (d.found_columns) statusEl.textContent += ` | Found: ${d.found_columns.slice(0,5).join(', ')}...`;
        }
    } catch (e) {
        statusEl.style.color = 'var(--error)';
        statusEl.textContent = `\u274c Error: ${e}`;
    }
}
