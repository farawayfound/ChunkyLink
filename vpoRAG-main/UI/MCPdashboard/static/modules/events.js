// modules/events.js — Event Log tab

let _evAll  = [];
let _evPage = 1;
let _evSort = { col: null, dir: 'asc' };

function _evSortVal(e, col) {
    if (col === 'terms')  return fmtTerms(e);
    if (col === 'result') return fmtResult(e);
    if (col === 'event')  return e.event ?? '';
    return e[col] ?? '';
}

function _evSorted() {
    if (!_evSort.col) return _evAll;
    const k = _evSort.col, d = _evSort.dir === 'asc' ? 1 : -1;
    return [..._evAll].sort((a, b) => {
        const av = _evSortVal(a, k), bv = _evSortVal(b, k);
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * d;
        return String(av).localeCompare(String(bv)) * d;
    });
}

function _evUpdateHeaders() {
    document.querySelectorAll('#event-table th[data-sort-key]').forEach(th => {
        th.removeAttribute('data-sort-dir');
        if (th.dataset.sortKey === _evSort.col) th.setAttribute('data-sort-dir', _evSort.dir);
    });
}

function _bindEvHeaders() {
    document.querySelectorAll('#event-table th[data-sort-key]').forEach(th => {
        th.addEventListener('click', () => {
            const k = th.dataset.sortKey;
            if (_evSort.col === k) { _evSort.dir = _evSort.dir === 'asc' ? 'desc' : 'asc'; }
            else { _evSort.col = k; _evSort.dir = 'asc'; }
            _evPage = 1;
            renderEventPage();
            _evUpdateHeaders();
        });
    });
}

async function loadEvents() {
    const selected = Array.from(document.querySelectorAll('#ev-dropdown-panel input:checked')).map(o => o.value);
    const client = document.getElementById('col-filter-client').value.trim();
    const terms  = document.getElementById('col-filter-terms').value.trim().toLowerCase();
    if (!selected.length) { _evAll = []; _evPage = 1; renderEventPage(); return; }
    let url = '/api/events?limit=500';
    selected.forEach(ev => url += `&event=${encodeURIComponent(ev)}`);
    if (client) url += `&client=${encodeURIComponent(client)}`;

    const r = await fetch(url);
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) return;

    _evAll  = terms ? d.events.filter(e => fmtTerms(e).toLowerCase().includes(terms)) : d.events;
    _evPage = 1;
    renderEventPage();
    _bindEvHeaders();
    _evUpdateHeaders();
}

function renderEventPage() {
    const pageSize = parseInt(document.getElementById('page-size').value, 10);
    const sorted   = _evSorted();
    const total    = sorted.length;
    const pages    = Math.max(1, Math.ceil(total / pageSize));
    _evPage        = Math.min(_evPage, pages);
    const start    = (_evPage - 1) * pageSize;
    const slice    = sorted.slice(start, start + pageSize);

    document.getElementById('event-count').textContent =
        `${total} events \u2014 page ${_evPage} of ${pages}`;

    const rows = slice.map(e => {
        const rowId  = `ev-${e.timestamp}-${e.event}`.replace(/[^a-zA-Z0-9-]/g, '_');
        const detail = JSON.stringify(e, null, 2);
        return `<tr>
        <td class="mono">${fmt(e.timestamp)}</td>
        <td><span class="badge badge-${e.event}">${e.event}</span></td>
        <td class="mono">${e.client_ip ?? '\u2014'}</td>
        <td>${e.user_id ?? '\u2014'}</td>
        <td class="truncate">${fmtTerms(e)}</td>
        <td class="truncate">${fmtResult(e)}</td>
        <td>${e.duration_ms != null ? e.duration_ms + ' ms' : '\u2014'}</td>
        <td><button class="btn btn-sm btn-ghost ev-expand-btn" title="Expand" onclick="toggleEvDetail('${rowId}')">&#x25BC;</button></td>
    </tr>
    <tr id="${rowId}" class="ev-detail-row" style="display:none">
        <td colspan="8"><pre class="ev-detail-pre">${detail.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre></td>
    </tr>`;
    }).join('');
    document.getElementById('event-tbody').innerHTML =
        rows || '<tr><td colspan="8" class="muted center">No events</td></tr>';

    let pg = '';
    if (pages > 1) {
        pg += `<button class="pg-btn" onclick="_evPage=1;renderEventPage()" ${_evPage===1?'disabled':''}>\u00ab</button>`;
        pg += `<button class="pg-btn" onclick="_evPage--;renderEventPage()" ${_evPage===1?'disabled':''}>\u2039</button>`;
        const lo = Math.max(1, _evPage - 3);
        const hi = Math.min(pages, lo + 6);
        for (let p = lo; p <= hi; p++)
            pg += `<button class="pg-btn ${p===_evPage?'pg-active':''}" onclick="_evPage=${p};renderEventPage()">${p}</button>`;
        pg += `<button class="pg-btn" onclick="_evPage++;renderEventPage()" ${_evPage===pages?'disabled':''}>\u203a</button>`;
        pg += `<button class="pg-btn" onclick="_evPage=${pages};renderEventPage()" ${_evPage===pages?'disabled':''}>\u00bb</button>`;
    }
    document.getElementById('event-pagination').innerHTML = pg;
}

function toggleEvDetail(rowId) {
    const row = document.getElementById(rowId);
    if (!row) return;
    const visible = row.style.display !== 'none';
    row.style.display = visible ? 'none' : '';
    const btn = row.previousElementSibling?.querySelector('.ev-expand-btn');
    if (btn) btn.innerHTML = visible ? '&#x25BC;' : '&#x25B2;';
}

function toggleEvDropdown(e) {
    e.stopPropagation();
    document.getElementById('ev-dropdown-panel').classList.toggle('open');
}

function updateEvBtn() {
    const all     = document.querySelectorAll('#ev-dropdown-panel input');
    const checked = document.querySelectorAll('#ev-dropdown-panel input:checked');
    const span    = document.getElementById('ev-filter-count');
    span.textContent = (checked.length && checked.length < all.length) ? `(${checked.length})` : '';
}

document.addEventListener('click', () => {
    document.getElementById('ev-dropdown-panel')?.classList.remove('open');
});
