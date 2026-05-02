// modules/pager.js — generic client-side pager + toolbar helpers

const _pagerRegistry = {};

function makePager(tbodyId, paginationId, countId, defaultSize, renderRowFn, emptyHtml, opts) {
    const s = { rows: [], orig: [], page: 1, size: defaultSize, sortCol: null, sortDir: 'asc' };
    const _fState  = {};
    const _sState  = {};
    const _fValues = {};

    function _sortVal(row, key) { const v = row[key]; return v == null ? '' : v; }

    function _sorted(rows) {
        if (!s.sortCol) return rows;
        const k = s.sortCol, d = s.sortDir === 'asc' ? 1 : -1;
        return [...rows].sort((a, b) => {
            const av = _sortVal(a, k), bv = _sortVal(b, k);
            if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * d;
            return String(av).localeCompare(String(bv)) * d;
        });
    }

    function _filtered() {
        let rows = s.orig;
        for (const [key, checked] of Object.entries(_fState)) {
            if (!checked) continue;
            rows = rows.filter(r => checked.has(String(r[key] ?? '')));
        }
        for (const [key, term] of Object.entries(_sState)) {
            if (!term) continue;
            const t = term.toLowerCase();
            rows = rows.filter(r => String(r[key] ?? '').toLowerCase().includes(t));
        }
        return rows;
    }

    function _updateHeaders(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        table.querySelectorAll('th[data-sort-key]').forEach(th => {
            th.removeAttribute('data-sort-dir');
            if (th.dataset.sortKey === s.sortCol) th.setAttribute('data-sort-dir', s.sortDir);
        });
    }

    function render() {
        const filtered = _filtered();
        s.rows = _sorted(filtered);
        const total = s.rows.length;
        const pages = Math.max(1, Math.ceil(total / s.size));
        s.page = Math.min(s.page, pages);
        const start = (s.page - 1) * s.size;
        document.getElementById(tbodyId).innerHTML =
            s.rows.slice(start, start + s.size).map(renderRowFn).join('') ||
            (emptyHtml || '<tr><td colspan="99" class="muted center">No data</td></tr>');
        if (countId) {
            const cel = document.getElementById(countId);
            if (cel) cel.textContent = `${total} record${total !== 1 ? 's' : ''} \u2014 page ${s.page} of ${pages}`;
        }
        let pg = '';
        if (pages > 1) {
            const lo = Math.max(1, s.page - 3), hi = Math.min(pages, lo + 6);
            pg += `<button class="pg-btn" data-p="1" ${s.page===1?'disabled':''}>\u00ab</button>`;
            pg += `<button class="pg-btn" data-p="${s.page-1}" ${s.page===1?'disabled':''}>\u2039</button>`;
            for (let p = lo; p <= hi; p++)
                pg += `<button class="pg-btn ${p===s.page?'pg-active':''}" data-p="${p}">${p}</button>`;
            pg += `<button class="pg-btn" data-p="${s.page+1}" ${s.page===pages?'disabled':''}>\u203a</button>`;
            pg += `<button class="pg-btn" data-p="${pages}" ${s.page===pages?'disabled':''}>\u00bb</button>`;
        }
        const pgEl = document.getElementById(paginationId);
        pgEl.innerHTML = pg;
        pgEl.querySelectorAll('.pg-btn:not([disabled])').forEach(btn =>
            btn.addEventListener('click', () => { s.page = +btn.dataset.p; render(); }));
    }

    function _buildToolbar() {
        const toolbarId = opts && opts.toolbarId;
        const el = toolbarId && document.getElementById(toolbarId);
        if (!el) return;
        const filters  = (opts && opts.filters)  || [];
        const searches = (opts && opts.searches) || [];
        if (!filters.length && !searches.length) return;
        let html = '<div class="pager-toolbar">';
        filters.forEach(f => {
            const panelId = `pf-panel-${tbodyId}-${f.key}`;
            const vals = _fValues[f.key] || [];
            const checks = vals.map(v =>
                `<label><input type="checkbox" value="${v.replace(/"/g,'&quot;')}" checked
                    onchange="_pagerFilterChange('${tbodyId}','${f.key}','${panelId}')"> ${v||'(blank)'}</label>`
            ).join('');
            html += `<div class="pager-filter-wrap">
                <button class="pager-filter-btn" onclick="_pagerTogglePanel('${panelId}',event)">${f.label} \u25be</button>
                <div class="pager-filter-panel" id="${panelId}">${checks}</div>
            </div>`;
        });
        searches.forEach(f => {
            html += `<div class="pager-search-wrap">
                <div class="pager-search-label">${f.label}</div>
                <input type="text" placeholder="Search ${f.label.toLowerCase()}..."
                    oninput="_pagerSearchChange('${tbodyId}','${f.key}',this.value)">
            </div>`;
        });
        html += '</div>';
        el.innerHTML = html;
    }

    function bindHeaders(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        table.querySelectorAll('th[data-sort-key]').forEach(th => {
            th.addEventListener('click', () => {
                const k = th.dataset.sortKey;
                if (s.sortCol === k) { s.sortDir = s.sortDir === 'asc' ? 'desc' : 'asc'; }
                else { s.sortCol = k; s.sortDir = 'asc'; }
                s.page = 1; render(); _updateHeaders(tableId);
            });
        });
    }

    const api = {
        load(rows, tableId) {
            s.orig = rows; s.page = 1;
            ((opts && opts.filters) || []).forEach(f => {
                _fValues[f.key] = [...new Set(rows.map(r => String(r[f.key] ?? '')))].sort();
                if (_fState[f.key] === undefined) _fState[f.key] = null;
            });
            ((opts && opts.searches) || []).forEach(f => {
                if (_sState[f.key] === undefined) _sState[f.key] = '';
            });
            _buildToolbar();
            render();
            if (tableId) { bindHeaders(tableId); _updateHeaders(tableId); }
        },
        setPageSize(n) { s.size = n; s.page = 1; render(); },
        refilter(key, checked) {
            _fState[key] = checked.size === (_fValues[key] || []).length ? null : checked;
            s.page = 1; render();
        },
        research(key, val) { _sState[key] = val; s.page = 1; render(); },
        bindHeaders,
    };
    _pagerRegistry[tbodyId] = api;
    return api;
}

function _pagerTogglePanel(panelId, evt) {
    evt.stopPropagation();
    document.querySelectorAll('.pager-filter-panel.open').forEach(p => { if (p.id !== panelId) p.classList.remove('open'); });
    document.getElementById(panelId).classList.toggle('open');
}
function _pagerFilterChange(tbodyId, key, panelId) {
    const panel   = document.getElementById(panelId);
    const checked = new Set([...panel.querySelectorAll('input:checked')].map(i => i.value));
    _pagerRegistry[tbodyId].refilter(key, checked);
}
function _pagerSearchChange(tbodyId, key, val) {
    _pagerRegistry[tbodyId].research(key, val);
}
document.addEventListener('click', () =>
    document.querySelectorAll('.pager-filter-panel.open').forEach(p => p.classList.remove('open')));
