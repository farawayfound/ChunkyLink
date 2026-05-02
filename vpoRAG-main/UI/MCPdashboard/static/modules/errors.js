// modules/errors.js — Errors tab

const _errorPager = makePager('error-tbody', 'error-pagination', 'error-count', 20, e => {
    const isWarning = e.event && e.event.endsWith('_warning');
    const isCsvFail = e.event === 'csv_ingest';
    const rowClass  = isWarning ? 'row-warning' : 'row-error';
    const badge     = isWarning
        ? `<span class="badge badge-warning">${e.warning_type ?? 'warning'}</span>`
        : isCsvFail
        ? `<span class="badge badge-ingest-fail">csv_ingest fail</span>`
        : `<span class="badge badge-tool_error">${e.error_type ?? 'error'}</span>`;
    const detail = isWarning
        ? (e.output_chars ? `${e.warning_type} \u2014 ${e.output_chars.toLocaleString()} chars` : e.warning_type ?? '\u2014')
        : isCsvFail
        ? (e.error ?? `table=${e.table} file=${e.filename || '?'}`)
        : (e.error ?? '\u2014');
    const tool = e.tool ?? (e.event === 'search_kb_warning' ? 'search_kb' : e.event === 'search_jira_warning' ? 'search_jira' : isCsvFail ? `csv_ingest (${e.table ?? '?'})` : '\u2014');
    return `<tr class="${rowClass}">
        <td class="mono">${fmt(e.timestamp)}</td>
        <td>${tool}</td>
        <td>${badge}</td>
        <td class="truncate">${detail}</td>
        <td>${e.user_id ?? '\u2014'}</td>
        <td>${Array.isArray(e.terms) ? e.terms.join(', ') : (e.terms || '\u2014')}</td>
        <td>${e.duration_ms != null ? e.duration_ms + ' ms' : '\u2014'}</td>
    </tr>`;
}, '<tr><td colspan="7" class="muted center">No errors or warnings</td></tr>',
{ toolbarId: 'error-toolbar',
  filters:  [{ key: 'tool', label: 'Tool' }, { key: 'error_type', label: 'Error Type' }],
  searches: [{ key: 'error', label: 'Message' }, { key: 'user_id', label: 'User' }, { key: 'terms', label: 'Terms' }] });

async function loadErrors() {
    const r = await fetch('/api/errors');
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) return;
    const normalised = d.errors.map(e => {
        const isCsvFail = e.event === 'csv_ingest';
        return Object.assign({}, e, {
            tool: e.tool ?? (e.event === 'search_kb_warning' ? 'search_kb' : e.event === 'search_jira_warning' ? 'search_jira' : isCsvFail ? `csv_ingest (${e.table ?? '?'})` : ''),
            error_type: e.error_type ?? e.warning_type ?? '',
            terms: (e.terms ?? []).join(', '),
        });
    });
    _errorPager.load(normalised, 'error-table');
}
