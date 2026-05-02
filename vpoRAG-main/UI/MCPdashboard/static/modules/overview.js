// modules/overview.js — Overview tab: stats, charts, KPIs

let _dailyChart = null;
let _toolChart  = null;
let _statsData  = null;
let _activeRange = null;

async function loadStats() {
    const r = await fetch('/api/stats');
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) return;
    _statsData   = d;
    _activeRange = null;
    renderOverview(d.all_tool_events, d.all_errors, d);
}

function resetDateRange() {
    if (!_statsData) return;
    _activeRange = null;
    document.getElementById('range-label').textContent = '';
    renderOverview(_statsData.all_tool_events, _statsData.all_errors, _statsData);
}

function renderOverview(toolEvents, errors, fullData) {
    const toolDefs = [
        { key: 'search_kb',   label: 'search_kb',    color: '#f7a24f' },
        { key: 'search_jira', label: 'search_jira',   color: '#4f8ef7' },
        { key: 'build_index', label: 'build_index',   color: '#4fc97a' },
        { key: 'learn',       label: 'learn',          color: '#a78bfa' },
        { key: 'request_end', label: 'HTTP requests', color: '#94a3b8' },
    ];

    const callsByTool = {};
    toolDefs.forEach(t => callsByTool[t.key] = 0);
    toolEvents.forEach(e => { if (callsByTool[e.event] !== undefined) callsByTool[e.event]++; });

    document.getElementById('kpi-total').textContent  = toolEvents.length;
    document.getElementById('kpi-kb').textContent     = callsByTool.search_kb;
    document.getElementById('kpi-jira').textContent   = callsByTool.search_jira;
    document.getElementById('kpi-build').textContent  = callsByTool.build_index;
    document.getElementById('kpi-learn').textContent  = callsByTool.learn ?? 0;
    document.getElementById('kpi-errors').textContent = errors.length;

    const kbChunks = toolEvents.filter(e => e.event === 'search_kb').map(e => e.chunks_returned || 0);
    document.getElementById('kpi-avg-chunks').textContent = kbChunks.length
        ? (kbChunks.reduce((a, b) => a + b, 0) / kbChunks.length).toFixed(1) : 0;

    const lastEvent = toolEvents.reduce((best, e) =>
        (!best || e.timestamp > best.timestamp) ? e : best, null);
    document.getElementById('last-activity').textContent = 'Last activity: ' + fmt(lastEvent?.timestamp);

    // Daily line chart
    const allEventsForChart = [...toolEvents, ...((fullData.all_http_events) || [])];
    const callsByDay = {};
    const callsByDayByTool = {};
    toolDefs.forEach(t => callsByDayByTool[t.key] = {});
    allEventsForChart.forEach(e => {
        const day = (e.timestamp || '').slice(0, 10);
        if (!day) return;
        if (e.event !== 'request_end') callsByDay[day] = (callsByDay[day] || 0) + 1;
        else callsByDay[day] = callsByDay[day] || 0;
        if (callsByDayByTool[e.event]) callsByDayByTool[e.event][day] = (callsByDayByTool[e.event][day] || 0) + 1;
    });
    const today  = new Date().toISOString().slice(0, 10);
    const cutoff = new Date(new Date(today) - 29 * 86400000).toISOString().slice(0, 10);
    let allDays = Object.keys(callsByDay).filter(d => d >= cutoff).sort();
    if (_activeRange) allDays = allDays.filter(d => d >= _activeRange.from && d <= _activeRange.to);

    const datasets = toolDefs.map(({ key, label, color }) => ({
        label,
        data: allDays.map(day => (callsByDayByTool[key] || {})[day] || 0),
        borderColor: color,
        backgroundColor: color + '22',
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 6,
        fill: false,
        borderDash: key === 'request_end' ? [3, 3] : undefined,
        hidden: key === 'request_end',
    }));
    datasets.push({
        label: 'Tool Total',
        data: allDays.map(day => callsByDay[day] || 0),
        borderColor: '#e2e8f0',
        backgroundColor: '#e2e8f022',
        borderDash: [5, 3],
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 6,
        fill: false,
    });

    if (_dailyChart) _dailyChart.destroy();
    _dailyChart = new Chart(document.getElementById('chart-daily'), {
        type: 'line',
        data: { labels: allDays, datasets },
        options: {
            onClick(evt, elements, chart) {
                const pts = chart.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
                if (!pts.length) return;
                const day = allDays[pts[0].index];
                _activeRange = { from: day, to: day };
                document.getElementById('range-label').textContent = `Showing: ${day}`;
                _applyRange();
            },
            plugins: {
                legend: { position: 'bottom', labels: { color: '#94a3b8', boxWidth: 12 } },
                tooltip: { mode: 'index', intersect: false },
                zoom: {
                    zoom: {
                        drag: { enabled: true, backgroundColor: 'rgba(79,142,247,0.15)', borderColor: '#4f8ef7', borderWidth: 1 },
                        mode: 'x',
                        onZoomComplete({ chart }) {
                            const { min, max } = chart.scales.x;
                            const iFrom = Math.max(0, Math.round(min));
                            const iTo   = Math.min(allDays.length - 1, Math.round(max));
                            const from  = allDays[iFrom];
                            const to    = allDays[iTo];
                            if (from && to) {
                                _activeRange = { from, to };
                                document.getElementById('range-label').textContent = from === to ? `Showing: ${from}` : `Showing: ${from} \u2192 ${to}`;
                                setTimeout(_applyRange, 0);
                            }
                        },
                    },
                },
            },
            scales: {
                x: { ticks: { color: '#64748b', maxRotation: 45 } },
                y: { beginAtZero: true, ticks: { stepSize: 1, color: '#64748b' } },
            },
        },
    });

    // Tool pie chart
    if (_toolChart) _toolChart.destroy();
    const toolDefsKpi = toolDefs.filter(t => t.key !== 'request_end');
    _toolChart = new Chart(document.getElementById('chart-tools'), {
        type: 'doughnut',
        data: {
            labels: toolDefsKpi.map(t => t.key),
            datasets: [{ data: toolDefsKpi.map(t => callsByTool[t.key] ?? 0), backgroundColor: toolDefsKpi.map(t => t.color) }],
        },
        options: { plugins: { legend: { position: 'bottom' } } },
    });

    // Level distribution
    const levelDist = {};
    toolEvents.filter(e => e.event === 'search_kb' && e.level).forEach(e => {
        levelDist[e.level] = (levelDist[e.level] || 0) + 1;
    });
    document.getElementById('level-dist').innerHTML = _barList(levelDist, callsByTool.search_kb || 1);

    // Jira sources
    const jiraSources = {};
    toolEvents.filter(e => e.event === 'search_jira' && e.source).forEach(e => {
        jiraSources[e.source] = (jiraSources[e.source] || 0) + 1;
    });
    document.getElementById('jira-sources').innerHTML = _barList(jiraSources, callsByTool.search_jira || 1);

    // Avg durations
    const durBuckets = {};
    toolEvents.filter(e => e.duration_ms != null).forEach(e => {
        if (!durBuckets[e.event]) durBuckets[e.event] = [];
        durBuckets[e.event].push(e.duration_ms);
    });
    const durHtml = Object.entries(durBuckets)
        .map(([t, vals]) => `<div class="stat-row"><span>${t}</span><span class="stat-val">${Math.round(vals.reduce((a,b)=>a+b,0)/vals.length)} ms</span></div>`)
        .join('') || '<span class="muted">No data</span>';
    document.getElementById('avg-durations').innerHTML = durHtml;

    // Client table
    const byClient = {};
    toolEvents.forEach(e => {
        const ip  = e.client_ip || 'unknown';
        const uid = e.user_id || '';
        const key = (uid && uid !== 'anonymous') ? `${uid} (${ip})` : ip;
        byClient[key] = (byClient[key] || 0) + 1;
    });
    const rows = Object.entries(byClient).sort((a, b) => b[1] - a[1])
        .map(([ip, n]) => `<tr><td>${ip}</td><td>${n}</td></tr>`).join('');
    document.getElementById('client-table').innerHTML =
        `<table class="data-table"><thead><tr><th>User (IP)</th><th>Calls</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function _applyRange() {
    if (!_statsData || !_activeRange) return;
    const { from, to } = _activeRange;
    const filtered = _statsData.all_tool_events.filter(e => {
        const day = (e.timestamp || '').slice(0, 10);
        return day >= from && day <= to;
    });
    const filteredErrors = _statsData.all_errors.filter(e => {
        const day = (e.timestamp || '').slice(0, 10);
        return day >= from && day <= to;
    });
    renderOverview(filtered, filteredErrors, _statsData);
}

function _barList(obj, total) {
    if (!obj || !Object.keys(obj).length) return '<span class="muted">No data</span>';
    return Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
        const pct = total ? Math.round(v / total * 100) : 0;
        return `<div class="bar-row">
            <span class="bar-label">${k}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span class="bar-count">${v}</span>
        </div>`;
    }).join('');
}
