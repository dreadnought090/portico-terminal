// Portico Dashboard panel logic. Loaded after utils.js + before app.js.
// Shares window scope with app.js (no module system) — accesses globals:
//   API, portfolioData, tickerChart/sectorChart/typeChart,
//   animateCounter, applyStaggerAnimation, updateTickerBar,
//   updateBrokerSelectDropdown, showPanel, quickAnalysis.
// Helpers defined here are likewise global.

async function loadDashboard() {
    // Skeleton loading state — shimmer on KPI cards while fetching
    document.querySelectorAll('#panel-dashboard.v2 .market-card').forEach(c => c.setAttribute('data-loading', '1'));
    try {
        const [marketRes, portfolioRes] = await Promise.all([
            fetch(`${API}/api/market`),
            fetch(`${API}/api/portfolio`)
        ]);
        const market = await marketRes.json();
        portfolioData = await portfolioRes.json();

        // IHSG ticker
        const ihsgEl = document.getElementById('ihsg-ticker');
        const ihsgVal = market.ihsg || 0;
        const ihsgChg = market.ihsg_change_pct || 0;
        ihsgEl.textContent = `IHSG: ${fmt(ihsgVal)} (${fmtPct(ihsgChg)})`;
        ihsgEl.style.color = ihsgChg >= 0 ? '#34d399' : '#f87171';
        ihsgEl.style.borderColor = ihsgChg >= 0 ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';
        ihsgEl.style.background = ihsgChg >= 0 ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)';

        document.getElementById('mc-ihsg').textContent = fmt(ihsgVal);
        const ihsgChangeEl = document.getElementById('mc-ihsg-change');
        ihsgChangeEl.textContent = `${fmtChange(market.ihsg_change)} (${fmtPct(ihsgChg)})`;
        ihsgChangeEl.className = `card-change ${pnlClass(ihsgChg)}`;

        const summary = portfolioData.summary;
        animateCounter(document.getElementById('mc-portfolio-value'), summary.total_market_value, 800, 'Rp ');
        animateCounter(document.getElementById('mc-total-cost'), summary.total_cost, 800, 'Rp ');
        document.getElementById('mc-total-items').textContent = `${summary.total_items} saham`;

        const pnlEl = document.getElementById('mc-pnl');
        animateCounter(pnlEl, summary.total_pnl, 800, 'Rp ');
        pnlEl.className = `card-value ${pnlClass(summary.total_pnl)}`;

        const pnlPctEl = document.getElementById('mc-pnl-pct');
        pnlPctEl.textContent = fmtPct(summary.total_pnl_pct);
        pnlPctEl.className = `card-change ${pnlClass(summary.total_pnl_pct)}`;

        const portfolioPnlEl = document.getElementById('mc-portfolio-pnl');
        portfolioPnlEl.textContent = `P&L: ${fmtPct(summary.total_pnl_pct)}`;
        portfolioPnlEl.className = `card-change ${pnlClass(summary.total_pnl_pct)}`;

        renderTickerChart(portfolioData.combined || portfolioData.items);
        renderSectorChart(portfolioData.by_sector);
        renderTypeChart(portfolioData.by_type);
        renderDashboardTable(portfolioData.items);
        updateTickerBar(portfolioData.items);
        updateBrokerSelectDropdown();

        document.getElementById('dashboard-update-time').textContent = `Updated: ${new Date().toLocaleTimeString('id-ID')}`;

        applyStaggerAnimation(document.querySelector('.market-cards'), '.market-card');
        document.querySelectorAll('#panel-dashboard.v2 .market-card').forEach(c => c.removeAttribute('data-loading'));
        loadSystemHealth().catch(() => {});
    } catch (err) {
        console.error('Dashboard error:', err);
        document.querySelectorAll('#panel-dashboard.v2 .market-card').forEach(c => c.removeAttribute('data-loading'));
    }
}

async function loadSystemHealth() {
    const grid = document.getElementById('health-grid');
    const updateEl = document.getElementById('health-update-time');
    if (!grid) return;
    let data;
    try {
        const r = await fetch(`${API}/api/observability/status`);
        data = await r.json();
    } catch (e) {
        grid.innerHTML = `<div class="health-tile"><div class="ht-label">Error</div><div class="ht-value" style="font-size:13px;color:var(--red-light);">${e.message}</div></div>`;
        return;
    }

    const tiles = [];

    const cronOk = data.cron?.running && data.cron.count > 0;
    tiles.push({
        label: 'Cron Jobs',
        value: data.cron?.count ?? 0,
        meta: cronOk ? `${data.cron.count} scheduled` : 'scheduler off',
        status: cronOk ? 'ok' : 'fail',
    });

    const bots = data.bots || {};
    const activeBots = Object.values(bots).filter(Boolean).length;
    const totalBots = Object.keys(bots).length;
    tiles.push({
        label: 'Bots Active',
        value: `${activeBots}/${totalBots}`,
        meta: Object.entries(bots).map(([k, v]) => `${k}${v ? '✓' : '✗'}`).join(' '),
        status: activeBots === totalBots ? 'ok' : (activeBots > 0 ? 'warn' : 'fail'),
    });

    if (data.alerts?.error == null) {
        tiles.push({
            label: 'Price Alerts',
            value: data.alerts?.armed ?? 0,
            meta: `${data.alerts?.triggered_24h ?? 0} fired 24h`,
            status: (data.alerts?.armed ?? 0) > 0 ? 'ok' : 'idle',
        });
    }

    if (data.briefing) {
        const lastRun = data.briefing.last_run_at ? new Date(data.briefing.last_run_at) : null;
        const ageH = lastRun ? Math.floor((Date.now() - lastRun.getTime()) / 36e5) : null;
        const status = data.briefing.last_run_status === 'ok' && ageH !== null && ageH < 30 ? 'ok'
                     : data.briefing.last_run_status === 'ok' ? 'warn' : 'fail';
        tiles.push({
            label: 'Briefing',
            value: data.briefing.mode || '—',
            meta: lastRun ? `${ageH}h ago · ${data.briefing.last_run_messages ?? 0} msg` : 'never run',
            status,
        });
    }

    if (data.email_inbox) {
        const accs = data.email_inbox.configured_accounts ?? 0;
        tiles.push({
            label: 'Email Inbox',
            value: accs,
            meta: accs > 0 ? `${accs} account${accs > 1 ? 's' : ''} active` : 'not configured',
            status: accs > 0 ? 'ok' : 'idle',
        });
    }

    if (data.idx_registry?.error == null) {
        tiles.push({
            label: 'IDX Registry',
            value: data.idx_registry?.active ?? 0,
            meta: `${data.idx_registry?.total ?? 0} total · ${data.idx_registry?.inactive ?? 0} inactive`,
            status: (data.idx_registry?.active ?? 0) > 800 ? 'ok' : 'warn',
        });
    }

    grid.innerHTML = tiles.map(t => `
        <div class="health-tile">
            <span class="ht-status ${t.status}"></span>
            <div class="ht-label">${t.label}</div>
            <div class="ht-value">${t.value}</div>
            <div class="ht-meta">${t.meta}</div>
        </div>
    `).join('');

    if (updateEl) {
        updateEl.textContent = `Updated: ${new Date().toLocaleTimeString('id-ID')}`;
    }
}

function renderDashboardTable(items) {
    const tbody = document.getElementById('dashboard-portfolio-body');
    if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="padding:0;">
            <div class="empty-state">
                <div class="es-icon"><i class="fas fa-folder-open"></i></div>
                <div class="es-title">Portfolio kosong</div>
                <div class="es-hint">Belum ada saham di portofolio. Tambahkan posisi pertamamu untuk mulai melacak.</div>
                <button class="es-action" onclick="showPanel('add-stock')">Tambah Saham</button>
            </div>
        </td></tr>`;
        return;
    }
    tbody.innerHTML = items.map((item, idx) => `
        <tr class="stagger-item" data-ticker="${item.ticker}" style="--delay:${idx * 40}ms">
            <td class="ticker-cell" onclick="quickAnalysis('${item.ticker}')">${item.ticker}</td>
            <td>${item.company_name || '-'}</td>
            <td>${item.sub_sector || '-'}</td>
            <td class="num">${fmt(item.lot)}</td>
            <td class="num">${fmtRp(item.current_price)}</td>
            <td class="num daily-delta-cell"><span class="skel-pill">—</span></td>
            <td class="num spark-cell"><svg width="72" height="20" viewBox="0 0 72 20"><rect width="72" height="20" fill="rgba(80,110,160,0.08)" rx="3"/></svg></td>
            <td class="num">${fmtRp(item.market_value)}</td>
            <td class="num ${pnlClass(item.unrealized_pnl)}">${fmtRp(item.unrealized_pnl)}</td>
            <td class="num ${pnlClass(item.unrealized_pnl_pct)}">${fmtPct(item.unrealized_pnl_pct)}</td>
        </tr>
    `).join('');

    loadDashboardSparklines(items.map(i => i.ticker)).catch(() => {});
}

async function loadDashboardSparklines(tickers) {
    if (!tickers || tickers.length === 0) return;
    const uniq = [...new Set(tickers)];
    let data;
    try {
        const r = await fetch(`${API}/api/stocks/sparklines?tickers=${encodeURIComponent(uniq.join(','))}&days=7`);
        data = await r.json();
    } catch { return; }

    for (const ticker of uniq) {
        const d = data[ticker];
        if (!d) continue;
        const rows = document.querySelectorAll(`#dashboard-portfolio-body tr[data-ticker="${ticker}"]`);
        rows.forEach(row => {
            const deltaCell = row.querySelector('.daily-delta-cell');
            const sparkCell = row.querySelector('.spark-cell');
            if (deltaCell) {
                const cls = d.change >= 0 ? 'pos' : 'neg';
                const sign = d.change >= 0 ? '+' : '';
                deltaCell.innerHTML = `<span class="pnl-pct-pill ${cls}">${sign}${fmtPct(d.change_pct)}</span>`;
            }
            if (sparkCell && d.closes && d.closes.length >= 2) {
                sparkCell.innerHTML = renderSparkline(d.closes, d.change >= 0);
            } else if (sparkCell) {
                sparkCell.innerHTML = '<span style="color:var(--text-muted);font-size:11px;">n/a</span>';
            }
        });
    }
}

function renderSparkline(closes, isUp) {
    const W = 72, H = 20, P = 2;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;
    const dx = (W - 2 * P) / (closes.length - 1);
    const points = closes.map((c, i) => {
        const x = P + i * dx;
        const y = H - P - ((c - min) / range) * (H - 2 * P);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const color = isUp ? '#34d399' : '#f87171';
    const fill = isUp ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)';
    const fillPath = `M ${P},${H - P} L ${points.replace(/ /g, ' L ')} L ${(W - P).toFixed(1)},${H - P} Z`;
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        <path d="${fillPath}" fill="${fill}" />
        <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>`;
}

function renderTickerChart(items) {
    const canvas = document.getElementById('ticker-chart');
    const legendEl = document.getElementById('ticker-chart-legend');
    if (!canvas) return;
    if (tickerChart) tickerChart.destroy();
    const sorted = [...items].filter(i => i.market_value > 0).sort((a, b) => b.market_value - a.market_value);
    if (sorted.length === 0) { canvas.style.display = 'none'; if (legendEl) legendEl.innerHTML = ''; return; }
    canvas.style.display = 'block';
    const total = sorted.reduce((a, b) => a + b.market_value, 0);
    const data = sorted.map(i => i.market_value);
    const colors = ['#3b82f6','#10b981','#f97316','#a78bfa','#22d3ee','#f59e0b','#ef4444','#ec4899','#8b5cf6','#14b8a6','#6366f1','#84cc16','#06b6d4','#e11d48','#7c3aed','#0ea5e9','#d946ef','#facc15','#4ade80','#fb923c'];
    tickerChart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels: sorted.map(i => i.ticker), datasets: [{ data, backgroundColor: colors.slice(0, data.length), borderWidth: 2, borderColor: 'rgba(6,10,19,0.8)', hoverOffset: 8 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '50%',
            animation: { duration: 800, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(14,23,38,0.95)',
                    borderColor: 'rgba(249,115,22,0.3)',
                    borderWidth: 1,
                    titleColor: '#eaf0f6',
                    bodyColor: '#8b9dc3',
                    cornerRadius: 8,
                    padding: 12,
                    callbacks: { label: ctx => {
                        const t = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const pct = (ctx.raw / t * 100).toFixed(1);
                        return ` ${ctx.label}: ${fmtRp(ctx.raw)} (${pct}%)`;
                    }}
                }
            }
        }
    });
    if (legendEl) {
        if (sorted.length === 0) {
            legendEl.innerHTML = `<div class="empty-state" style="padding:20px 0;">
                <div class="es-icon"><i class="fas fa-chart-pie"></i></div>
                <div class="es-title">Belum ada alokasi</div>
                <div class="es-hint">Tambahkan saham untuk lihat distribusi.</div>
            </div>`;
        } else {
            legendEl.innerHTML = sorted.map((item, i) => {
                const pct = (item.market_value / total * 100).toFixed(1);
                const color = colors[i % colors.length];
                const pnl = item.unrealized_pnl || 0;
                const pnlPct = item.unrealized_pnl_pct || 0;
                const pnlCls = pnl >= 0 ? 'pos' : 'neg';
                const ttContent = `
                    <div class="v2-tt-title">${item.ticker}</div>
                    <div style="font-size:11px;color:#8b9dc3;margin-bottom:6px;">${(item.company_name || '').slice(0, 40)}</div>
                    <div class="v2-tt-row"><span class="v2-tt-label">Lot</span><span class="v2-tt-value">${fmt(item.lot || 0)}</span></div>
                    <div class="v2-tt-row"><span class="v2-tt-label">Avg</span><span class="v2-tt-value">Rp ${fmt(item.avg_price || 0)}</span></div>
                    <div class="v2-tt-row"><span class="v2-tt-label">Last</span><span class="v2-tt-value">Rp ${fmt(item.current_price || 0)}</span></div>
                    <div class="v2-tt-row"><span class="v2-tt-label">Value</span><span class="v2-tt-value">${fmtBigNum(item.market_value)}</span></div>
                    <div class="v2-tt-row"><span class="v2-tt-label">P&L</span><span class="v2-tt-value ${pnlCls}">${fmtBigNum(pnl)} (${fmtPct(pnlPct)})</span></div>
                    <div class="v2-tt-row"><span class="v2-tt-label">Sektor</span><span class="v2-tt-value" style="font-size:10px;">${(item.sub_sector || '-').slice(0, 18)}</span></div>
                `.replace(/\s+/g, ' ').trim();
                return `<div class="v2-legend-item" data-ticker="${item.ticker}" data-tippy-content='${ttContent.replace(/'/g, "&apos;")}' style="display:flex;align-items:center;gap:8px;padding:4px 6px;">
                    <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0;"></span>
                    <span style="color:#eaf0f6;font-weight:500;">${item.ticker}</span>
                    <span style="color:#8b9dc3;">${pct}%</span>
                    <span style="color:#5a6f8c;margin-left:auto;">${fmtBigNum(item.market_value)}</span>
                </div>`;
            }).join('');

            if (typeof tippy !== 'undefined') {
                tippy(legendEl.querySelectorAll('.v2-legend-item'), {
                    allowHTML: true,
                    theme: 'v2',
                    placement: 'left',
                    delay: [120, 0],
                    arrow: true,
                });
            }
        }
    }
}

let tickerChartHeight = 280;
function zoomTickerChart(dir) {
    const wrapper = document.getElementById('ticker-chart-wrapper');
    if (!wrapper) return;
    if (dir === 0) { tickerChartHeight = 280; }
    else if (dir > 0) { tickerChartHeight = Math.min(tickerChartHeight + 80, 600); }
    else { tickerChartHeight = Math.max(tickerChartHeight - 80, 160); }
    wrapper.style.height = tickerChartHeight + 'px';
    if (tickerChart) setTimeout(() => tickerChart.resize(), 250);
}

function renderSectorChart(bySector) {
    const canvas = document.getElementById('sector-chart');
    const labels = Object.keys(bySector);
    const data = labels.map(k => bySector[k].market_value);
    const colors = ['#3b82f6','#10b981','#f97316','#a78bfa','#22d3ee','#f59e0b','#ef4444','#ec4899','#8b5cf6','#14b8a6','#f59e0b','#6366f1'];
    if (sectorChart) sectorChart.destroy();
    if (labels.length === 0) { canvas.style.display = 'none'; return; }
    canvas.style.display = 'block';
    sectorChart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels, datasets: [{ data, backgroundColor: colors.slice(0, labels.length), borderWidth: 2, borderColor: 'rgba(6,10,19,0.8)', hoverOffset: 6 }] },
        options: { responsive: true, cutout: '55%', animation: { duration: 800, easing: 'easeOutQuart' }, plugins: { legend: { position: 'right', labels: { color: '#eaf0f6', font: { size: 11, weight: '500' }, padding: 12 } }, tooltip: { backgroundColor: 'rgba(14,23,38,0.95)', borderColor: 'rgba(249,115,22,0.3)', borderWidth: 1, titleColor: '#eaf0f6', bodyColor: '#8b9dc3', cornerRadius: 8, padding: 12, callbacks: { label: ctx => ` ${ctx.label}: ${fmtRp(ctx.raw)}` } } } }
    });
}

function renderTypeChart(byType) {
    const canvas = document.getElementById('type-chart');
    const labels = Object.keys(byType);
    const data = labels.map(k => byType[k].market_value);
    const colors = ['#f97316','#3b82f6','#10b981','#a78bfa','#f59e0b','#ef4444','#22d3ee'];
    if (typeChart) typeChart.destroy();
    if (labels.length === 0) { canvas.style.display = 'none'; return; }
    canvas.style.display = 'block';
    typeChart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels, datasets: [{ data, backgroundColor: colors.slice(0, labels.length), borderWidth: 2, borderColor: 'rgba(6,10,19,0.8)', hoverOffset: 6 }] },
        options: { responsive: true, cutout: '55%', animation: { duration: 800, easing: 'easeOutQuart' }, plugins: { legend: { position: 'right', labels: { color: '#eaf0f6', font: { size: 11, weight: '500' }, padding: 12 } }, tooltip: { backgroundColor: 'rgba(14,23,38,0.95)', borderColor: 'rgba(249,115,22,0.3)', borderWidth: 1, titleColor: '#eaf0f6', bodyColor: '#8b9dc3', cornerRadius: 8, padding: 12, callbacks: { label: ctx => ` ${ctx.label}: ${fmtRp(ctx.raw)}` } } } }
    });
}
