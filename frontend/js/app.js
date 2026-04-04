/* ── Portico Terminal - Main Application v2 ── */

const API = '';
let portfolioData = null;

async function apiFetch(url, options) {
    const res = await fetch(url, options);
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.message || `HTTP ${res.status}`);
    }
    return res.json();
}
let currentDetailTicker = '';
let priceChart = null;
let sectorChart = null;
let typeChart = null;
let tickerChart = null;
let ocrResults = [];
let watchlistGridApi = null;
let detailRequestId = 0;

// ── COMPLETE BROKER/SEKURITAS LIST (IDX Active Members) ──────────────

const BROKER_LIST = [
    { code: 'XC', name: 'Ajaib Sekuritas Asia', short: 'Ajaib' },
    { code: 'PP', name: 'Aldiracita Sekuritas Indonesia', short: 'Aldiracita' },
    { code: 'YO', name: 'Amantara Sekuritas Indonesia', short: 'Amantara' },
    { code: 'ID', name: 'Anugerah Sekuritas Indonesia', short: 'Anugerah' },
    { code: 'SH', name: 'Artha Sekuritas Indonesia', short: 'Artha' },
    { code: 'DX', name: 'Bahana Sekuritas', short: 'Bahana' },
    { code: 'SQ', name: 'BCA Sekuritas', short: 'BCA Sekuritas' },
    { code: 'AR', name: 'Binaartha Sekuritas', short: 'Binaartha' },
    { code: 'GA', name: 'BNC Sekuritas Indonesia', short: 'BNC' },
    { code: 'NI', name: 'BNI Sekuritas', short: 'BNI Sekuritas' },
    { code: 'OD', name: 'BRI Danareksa Sekuritas', short: 'BRI Danareksa' },
    { code: 'RF', name: 'Buana Capital Sekuritas', short: 'Buana Capital' },
    { code: 'ZR', name: 'Bumiputera Sekuritas', short: 'Bumiputera' },
    { code: 'YU', name: 'CGS International Sekuritas Indonesia', short: 'CGS International' },
    { code: 'KI', name: 'Ciptadana Sekuritas Asia', short: 'Ciptadana' },
    { code: 'KZ', name: 'CLSA Sekuritas Indonesia', short: 'CLSA' },
    { code: 'II', name: 'Danatama Makmur Sekuritas', short: 'Danatama' },
    { code: 'PF', name: 'Danasakti Sekuritas Indonesia', short: 'Danasakti' },
    { code: 'DP', name: 'DBS Vickers Sekuritas Indonesia', short: 'DBS Vickers' },
    { code: 'TS', name: 'Dwidana Sakti Sekuritas', short: 'Dwidana Sakti' },
    { code: 'ES', name: 'Ekokapital Sekuritas', short: 'Ekokapital' },
    { code: 'SA', name: 'Elit Sukses Sekuritas', short: 'Elit Sukses' },
    { code: 'BS', name: 'Equity Sekuritas Indonesia', short: 'Equity' },
    { code: 'AO', name: 'Erdikha Elit Sekuritas', short: 'Erdikha Elit' },
    { code: 'EL', name: 'Evergreen Sekuritas Indonesia', short: 'Evergreen' },
    { code: 'PC', name: 'FAC Sekuritas Indonesia', short: 'FAC' },
    { code: 'FO', name: 'Forte Global Sekuritas', short: 'Forte Global' },
    { code: 'AF', name: 'Harita Kencana Sekuritas', short: 'Harita Kencana' },
    { code: 'HP', name: 'Henan Putihrai Sekuritas', short: 'Henan Putihrai' },
    { code: 'RB', name: 'INA Sekuritas Indonesia', short: 'INA' },
    { code: 'IU', name: 'Indo Capital Sekuritas', short: 'Indo Capital' },
    { code: 'IH', name: 'Indo Harvest Sekuritas', short: 'Indo Harvest' },
    { code: 'PD', name: 'Indo Premier Sekuritas', short: 'IPOT' },
    { code: 'IC', name: 'Integrity Capital Sekuritas', short: 'Integrity Capital' },
    { code: 'BF', name: 'Inti Fikasa Sekuritas', short: 'Inti Fikasa' },
    { code: 'IT', name: 'Inti Teladan Sekuritas', short: 'Inti Teladan' },
    { code: 'IN', name: 'Investindo Nusantara Sekuritas', short: 'Investindo' },
    { code: 'BK', name: 'J.P. Morgan Sekuritas Indonesia', short: 'J.P. Morgan' },
    { code: 'DU', name: 'KAF Sekuritas Indonesia', short: 'KAF' },
    { code: 'AI', name: 'Kay Hian Sekuritas', short: 'Kay Hian' },
    { code: 'CP', name: 'KB Valbury Sekuritas', short: 'Valbury' },
    { code: 'HD', name: 'KGI Sekuritas Indonesia', short: 'KGI' },
    { code: 'AG', name: 'Kiwoom Sekuritas Indonesia', short: 'Kiwoom' },
    { code: 'BQ', name: 'Korea Investment & Sekuritas Indonesia', short: 'Korea Investment' },
    { code: 'TF', name: 'Laba Sekuritas Indonesia', short: 'Laba' },
    { code: 'YJ', name: 'Lotus Andalan Sekuritas', short: 'Lotus Andalan' },
    { code: 'RX', name: 'Macquarie Sekuritas Indonesia', short: 'Macquarie' },
    { code: 'PI', name: 'Magenta Kapital Sekuritas Indonesia', short: 'Magenta Kapital' },
    { code: 'DD', name: 'Makindo Sekuritas', short: 'Makindo' },
    { code: 'CC', name: 'Mandiri Sekuritas', short: 'Mandiri Sekuritas' },
    { code: 'ZP', name: 'Maybank Sekuritas Indonesia', short: 'Maybank' },
    { code: 'CD', name: 'Mega Capital Sekuritas', short: 'Mega Capital' },
    { code: 'MU', name: 'Minna Padi Investama Sekuritas Tbk', short: 'Minna Padi' },
    { code: 'YP', name: 'Mirae Asset Sekuritas Indonesia', short: 'Mirae Asset' },
    { code: 'EP', name: 'MNC Sekuritas', short: 'MNC' },
    { code: 'OK', name: 'Net Sekuritas', short: 'Net' },
    { code: 'XA', name: 'NH Korindo Sekuritas Indonesia', short: 'NH Korindo' },
    { code: 'TP', name: 'OCBC Sekuritas Indonesia', short: 'OCBC Sekuritas' },
    { code: 'AP', name: 'Pacific Sekuritas Indonesia', short: 'Pacific' },
    { code: 'PG', name: 'Panca Global Sekuritas', short: 'Panca Global' },
    { code: 'GR', name: 'Panin Sekuritas Tbk', short: 'Panin' },
    { code: 'KK', name: 'Phillip Sekuritas Indonesia', short: 'Phillip Sekuritas' },
    { code: 'AT', name: 'Phintraco Sekuritas', short: 'Phintraco' },
    { code: 'PO', name: 'Pilarmas Investindo Sekuritas', short: 'Pilarmas' },
    { code: 'RO', name: 'Pluang Maju Sekuritas', short: 'Pluang' },
    { code: 'RG', name: 'Profindo Sekuritas Indonesia', short: 'Profindo' },
    { code: 'LS', name: 'Reliance Sekuritas Indonesia Tbk', short: 'Reliance' },
    { code: 'DR', name: 'RHB Sekuritas Indonesia', short: 'RHB Sekuritas' },
    { code: 'IF', name: 'Samuel Sekuritas Indonesia', short: 'Samuel' },
    { code: 'MG', name: 'Semesta Indovest Sekuritas', short: 'Semesta Indovest' },
    { code: 'AH', name: 'Shinhan Sekuritas Indonesia', short: 'Shinhan' },
    { code: 'DH', name: 'Sinarmas Sekuritas', short: 'Sinarmas' },
    { code: 'XL', name: 'Stockbit Sekuritas Digital', short: 'Stockbit' },
    { code: 'AD', name: 'Sukadana Prima Sekuritas', short: 'Sukadana Prima' },
    { code: 'AZ', name: 'Sucor Sekuritas', short: 'Sucor Sekuritas' },
    { code: 'SS', name: 'Supra Sekuritas Indonesia', short: 'Supra' },
    { code: 'SF', name: 'Surya Fajar Sekuritas', short: 'Surya Fajar' },
    { code: 'LG', name: 'Trimegah Sekuritas Indonesia Tbk', short: 'Trimegah' },
    { code: 'BR', name: 'Trust Sekuritas', short: 'Trust' },
    { code: 'QA', name: 'Tuntun Sekuritas Indonesia', short: 'Tuntun' },
    { code: 'AK', name: 'UBS Sekuritas Indonesia', short: 'UBS' },
    { code: 'BB', name: 'Verdhana Sekuritas Indonesia', short: 'Verdhana' },
    { code: 'MI', name: 'Victoria Sekuritas Indonesia', short: 'Victoria' },
    { code: 'FZ', name: 'Waterfront Sekuritas Indonesia', short: 'Waterfront' },
    { code: 'GI', name: 'Webull Sekuritas Indonesia', short: 'Webull' },
    { code: 'YB', name: 'Yakin Bertumbuh Sekuritas', short: 'Yakin Bertumbuh' },
    { code: 'FS', name: 'Yuanta Sekuritas Indonesia', short: 'Yuanta' },
    { code: 'RS', name: 'Yulie Sekuritas Indonesia Tbk', short: 'Yulie' },
    // Platform non-sekuritas (untuk reksadana/obligasi)
    { code: '-', name: 'Bibit', short: 'Bibit' },
    { code: '-', name: 'Bareksa', short: 'Bareksa' },
    { code: '-', name: 'Lainnya', short: 'Lainnya' },
];

function populateBrokerSelects() {
    const selects = document.querySelectorAll('.broker-select, #add-broker, #edit-broker, #ocr-broker, #paste-broker, #portfolio-bulk-broker');
    selects.forEach(sel => {
        const currentVal = sel.value;
        // Keep only the placeholder
        const placeholder = sel.options[0];
        sel.innerHTML = '';
        if (placeholder && placeholder.value === '') sel.appendChild(placeholder);

        for (const b of BROKER_LIST) {
            const opt = document.createElement('option');
            opt.value = b.short;
            opt.textContent = b.code !== '-' ? `${b.short} (${b.code})` : b.short;
            sel.appendChild(opt);
        }

        // Restore previous value if valid
        if (currentVal) sel.value = currentVal;
    });
}

// ── INIT ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    loadDashboard();

    // Search bar
    document.getElementById('search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const ticker = e.target.value.trim();
            if (ticker) {
                showPanel('stock-detail');
                document.getElementById('detail-ticker-input').value = ticker;
                loadStockDetail();
                e.target.value = '';
            }
        }
    });

    // Detail ticker input Enter key
    document.getElementById('detail-ticker-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') loadStockDetail();
    });

    // Screenshot upload
    const uploadArea = document.getElementById('upload-area');
    const screenshotInput = document.getElementById('screenshot-input');
    uploadArea.addEventListener('click', () => screenshotInput.click());
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.style.borderColor = '#f97316'; });
    uploadArea.addEventListener('dragleave', () => { uploadArea.style.borderColor = ''; });
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '';
        if (e.dataTransfer.files.length > 0) processScreenshot(e.dataTransfer.files[0]);
    });
    screenshotInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) processScreenshot(e.target.files[0]);
    });

    // Escape key closes modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('edit-modal');
            if (modal && !modal.classList.contains('hidden')) closeEditModal();
        }
    });

    // Auto-refresh every 5 minutes
    setInterval(() => { loadDashboard(); }, 300000);

    // Initialize favorite broker pins on all broker selects
    initFavoriteBrokers();

    // Sortable.js — sidebar nav drag-and-drop
    if (typeof Sortable !== 'undefined') {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            new Sortable(sidebar, {
                animation: 200,
                ghostClass: 'sortable-ghost',
                handle: '.nav-btn',
                filter: '.sidebar-divider',
                onEnd: () => {
                    const order = Array.from(sidebar.querySelectorAll('.nav-btn')).map(b => b.dataset.panel);
                    localStorage.setItem('sidebarOrder', JSON.stringify(order));
                }
            });
            // Restore saved order
            const saved = localStorage.getItem('sidebarOrder');
            if (saved) {
                try {
                    const order = JSON.parse(saved);
                    const btns = sidebar.querySelectorAll('.nav-btn');
                    const divider = sidebar.querySelector('.sidebar-divider');
                    const btnMap = {};
                    btns.forEach(b => { btnMap[b.dataset.panel] = b; });
                    order.forEach(panel => {
                        if (btnMap[panel]) sidebar.insertBefore(btnMap[panel], divider || null);
                    });
                } catch(e) {}
            }
        }
    }

    // Tippy.js — global tooltip delegate
    if (typeof tippy !== 'undefined') {
        tippy.delegate('body', {
            target: '[data-tippy-content]',
            theme: 'terminal',
            animation: 'scale',
            arrow: true,
            delay: [200, 0]
        });
    }
});

function updateClock() {
    const now = new Date();
    const opts = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    document.getElementById('clock').textContent = now.toLocaleDateString('id-ID', opts);
}

// ── NAVIGATION ────────────────────────────────────────────────────────

function showPanel(panelId) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`panel-${panelId}`).classList.add('active');
    const btn = document.querySelector(`[data-panel="${panelId}"]`);
    if (btn) btn.classList.add('active');

    switch (panelId) {
        case 'dashboard': loadDashboard(); break;
        case 'portfolio': loadPortfolio(); break;
        case 'watchlist': loadWatchlist(); break;
        case 'news': loadNews(); break;
        case 'disclosure': loadDisclosure(); break;
    }
}

// ── NUMERAL.JS LOCALE SETUP ──────────────────────────────────────────

if (typeof numeral !== 'undefined') {
    numeral.register('locale', 'id', {
        delimiters: { thousands: '.', decimal: ',' },
        abbreviations: { thousand: 'rb', million: 'Jt', billion: 'M', trillion: 'T' },
        currency: { symbol: 'Rp ' }
    });
    numeral.locale('id');
}

// ── FORMATTING ────────────────────────────────────────────────────────

function fmt(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return numeral(Math.round(num)).format('0,0');
}
function fmtRp(num) {
    if (num === null || num === undefined || isNaN(num)) return 'Rp -';
    return 'Rp ' + numeral(Math.round(num)).format('0,0');
}
function fmtPct(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
}
function fmtChange(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return `${num >= 0 ? '+' : ''}${fmt(num)}`;
}
function pnlClass(num) {
    if (num > 0) return 'positive';
    if (num < 0) return 'negative';
    return 'neutral';
}
function fmtBigNum(num) {
    if (!num || num === 0) return '-';
    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';
    if (abs >= 1e12) return `${sign}Rp ${numeral(abs / 1e12).format('0.0')}T`;
    if (abs >= 1e9) return `${sign}Rp ${numeral(abs / 1e9).format('0.0')}M`;
    if (abs >= 1e6) return `${sign}Rp ${numeral(abs / 1e6).format('0.0')}Jt`;
    return fmtRp(num);
}
function fmtPctVal(num) {
    if (num === null || num === undefined || num === 0) return '-';
    // TradingView & yfinance return margins/ratios as decimals (0.15 = 15%)
    // Values > 1 or < -1 are already in percentage form (e.g., growth 120%)
    if (Math.abs(num) <= 1) return numeral(num * 100).format('0.00') + '%';
    return numeral(num).format('0.00') + '%';
}
function fmtDecimal(num, d = 2) {
    if (!num) return '-';
    return numeral(num).format('0.' + '0'.repeat(d));
}

// ── FAVORITE BROKER (PIN) SYSTEM ─────────────────────────────────────

function getFavoriteBrokers() {
    try { return JSON.parse(localStorage.getItem('favBrokers') || '[]'); }
    catch { return []; }
}

function saveFavoriteBrokers(favs) {
    localStorage.setItem('favBrokers', JSON.stringify(favs));
}

function toggleFavoriteBroker(broker) {
    if (!broker) return;
    let favs = getFavoriteBrokers();
    if (favs.includes(broker)) {
        favs = favs.filter(b => b !== broker);
    } else {
        favs.push(broker);
    }
    saveFavoriteBrokers(favs);
    // Re-sort all broker selects
    document.querySelectorAll('.broker-select').forEach(sel => sortBrokerSelect(sel));
    // Update all pin buttons
    document.querySelectorAll('.broker-pin-btn').forEach(btn => updatePinButton(btn));
}

function sortBrokerSelect(select) {
    const favs = getFavoriteBrokers();
    const currentVal = select.value;
    const options = Array.from(select.options);

    // Separate placeholder (first option with value=""), favorites, and regular
    const placeholder = options.find(o => o.value === '');
    const favOptions = [];
    const regularOptions = [];
    // Remove existing separators
    options.filter(o => o.disabled && o.textContent.includes('───')).forEach(o => o.remove());

    for (const opt of options) {
        if (opt.value === '' || (opt.disabled && opt.textContent.includes('───'))) continue; // skip placeholder & separators
        // Clean label (remove star prefix if present)
        opt.textContent = opt.textContent.replace(/^⭐\s*/, '');
        if (favs.includes(opt.value)) {
            opt.textContent = '⭐ ' + opt.textContent;
            favOptions.push(opt);
        } else {
            regularOptions.push(opt);
        }
    }

    // Clear and re-add in order: placeholder, favorites, separator-ish, regular
    select.innerHTML = '';
    if (placeholder) select.appendChild(placeholder);

    // Add fav options first
    for (const opt of favOptions) select.appendChild(opt);

    // Add a visual separator if there are favorites
    if (favOptions.length > 0 && regularOptions.length > 0) {
        const sep = document.createElement('option');
        sep.disabled = true;
        sep.textContent = '──────────────';
        sep.className = 'broker-separator';
        select.appendChild(sep);
    }

    // Add regular options
    for (const opt of regularOptions) select.appendChild(opt);

    // Restore selection
    select.value = currentVal;
}

function updatePinButton(btn) {
    const selectId = btn.dataset.for;
    const select = document.getElementById(selectId);
    if (!select) return;
    const favs = getFavoriteBrokers();
    const isFav = select.value && favs.includes(select.value);
    btn.innerHTML = isFav
        ? '<i class="fas fa-star"></i>'
        : '<i class="far fa-star"></i>';
    btn.setAttribute('data-tippy-content', isFav ? 'Hapus dari favorit' : 'Pin sebagai favorit');
    if (btn._tippy) btn._tippy.setContent(isFav ? 'Hapus dari favorit' : 'Pin sebagai favorit');
    btn.style.color = isFav ? 'var(--gold)' : 'var(--text-muted)';
}

function initFavoriteBrokers() {
    // First populate all broker selects with complete list
    populateBrokerSelects();

    const brokerSelects = [
        { id: 'add-broker', label: 'add' },
        { id: 'edit-broker', label: 'edit' },
        { id: 'ocr-broker', label: 'ocr' },
        { id: 'paste-broker', label: 'paste' }
    ];

    for (const { id, label } of brokerSelects) {
        const select = document.getElementById(id);
        if (!select) continue;

        // Mark select for identification
        select.classList.add('broker-select');

        // Create pin button
        const pinBtn = document.createElement('button');
        pinBtn.type = 'button';
        pinBtn.className = 'btn btn-ghost btn-sm broker-pin-btn';
        pinBtn.dataset.for = id;
        pinBtn.style.cssText = 'position:absolute;right:4px;top:50%;transform:translateY(-50%);z-index:2;padding:4px 6px;font-size:13px;';
        pinBtn.innerHTML = '<i class="far fa-star"></i>';
        pinBtn.setAttribute('data-tippy-content', 'Pin sebagai favorit');
        pinBtn.style.color = 'var(--text-muted)';
        pinBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleFavoriteBroker(select.value);
        };

        // Wrap select parent in relative container if not already
        const parent = select.parentElement;
        if (parent && getComputedStyle(parent).position === 'static') {
            parent.style.position = 'relative';
        }
        // Add extra padding to select so text doesn't overlap the star
        select.style.paddingRight = '44px';
        parent.appendChild(pinBtn);

        // Update pin button when selection changes
        select.addEventListener('change', () => updatePinButton(pinBtn));

        // Initial sort and pin state
        sortBrokerSelect(select);
        updatePinButton(pinBtn);
    }
}

// ── TOAST QUEUE SYSTEM ───────────────────────────────────────────────

const TOAST_MAX = 4;
const TOAST_ICONS = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    warning: 'fa-exclamation-triangle',
    info: 'fa-info-circle'
};

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    // Enforce max visible toasts
    const existing = container.querySelectorAll('.toast-item:not(.removing)');
    if (existing.length >= TOAST_MAX) {
        const oldest = existing[existing.length - 1];
        removeToast(oldest);
    }

    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type} animate__animated animate__fadeInRight animate__faster`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);
    toast.innerHTML = `
        <i class="fas ${TOAST_ICONS[type] || TOAST_ICONS.info} toast-icon"></i>
        <span class="toast-msg">${message}</span>
        <button class="toast-close" onclick="removeToast(this.parentElement)"><i class="fas fa-times"></i></button>
        <div class="toast-progress"></div>
    `;

    container.prepend(toast);

    // Auto dismiss
    const timer = setTimeout(() => removeToast(toast), duration);
    toast._timer = timer;
}

function removeToast(el) {
    if (!el || el.classList.contains('removing')) return;
    el.classList.add('removing');
    el.classList.remove('animate__fadeInRight');
    el.classList.add('animate__fadeOutRight');
    clearTimeout(el._timer);
    setTimeout(() => el.remove(), 400);
}

// ── ANIMATED NUMBER COUNTER ──────────────────────────────────────────

function animateCounter(element, targetValue, duration = 600, prefix = '', suffix = '') {
    if (!element) return;
    const startValue = parseFloat(element.dataset.currentValue) || 0;
    const startTime = performance.now();
    const format = (v) => prefix + numeral(Math.round(v)).format('0,0') + suffix;

    // Set final value immediately as fallback, then animate over it
    element.textContent = format(targetValue);
    element.dataset.currentValue = targetValue;

    // Skip animation if values are the same
    if (Math.round(startValue) === Math.round(targetValue)) return;

    let started = false;
    function step(now) {
        started = true;
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = startValue + (targetValue - startValue) * eased;
        element.textContent = format(current);
        if (progress < 1) requestAnimationFrame(step);
        else element.dataset.currentValue = targetValue;
    }
    requestAnimationFrame(step);
}

// ── SKELETON LOADERS ─────────────────────────────────────────────────

function showSkeleton(containerId, type = 'cards') {
    const el = document.getElementById(containerId);
    if (!el) return;

    const skeletons = {
        cards: `<div class="market-cards">${'<div class="skeleton skeleton-card market-card"></div>'.repeat(4)}</div>`,
        table: `<div class="table-wrapper" style="border:none;">${'<div class="skeleton skeleton-row"></div>'.repeat(6)}</div>`,
        detail: `<div class="skeleton skeleton-text" style="width:40%;height:28px;margin-bottom:16px;"></div>
                 <div class="skeleton skeleton-text" style="width:70%;"></div>
                 <div class="skeleton skeleton-text" style="width:55%;"></div>
                 <div class="skeleton skeleton-chart" style="margin-top:16px;"></div>`,
        chart: `<div class="skeleton skeleton-chart"></div>`
    };
    el.innerHTML = skeletons[type] || skeletons.cards;
}

// ── STAGGER ANIMATION HELPER ─────────────────────────────────────────

function applyStaggerAnimation(container, selector = '.market-card, .summary-item, .news-item, .disclosure-item') {
    if (!container) return;
    const items = container.querySelectorAll(selector);
    items.forEach((item, i) => {
        item.classList.add('stagger-item', 'animate__animated', 'animate__fadeInUp');
        item.style.animationDelay = `${i * 60}ms`;
        item.style.animationDuration = '0.4s';
    });
}

// ── RUNNING TICKER BAR ────────────────────────────────────────────────

function updateTickerBar(items) {
    const track = document.getElementById('ticker-track');
    if (!items || items.length === 0) {
        track.innerHTML = '<span class="placeholder-ticker">Tambahkan saham ke portfolio untuk melihat ticker berjalan</span>';
        return;
    }

    let html = '';
    // Duplicate items for seamless loop
    const allItems = [...items, ...items];
    for (const item of allItems) {
        const chgClass = item.unrealized_pnl >= 0 ? 'up' : 'down';
        const arrow = item.unrealized_pnl >= 0 ? '&#9650;' : '&#9660;';
        html += `
            <span class="ticker-item" onclick="quickAnalysis('${item.ticker}')">
                <span class="ti-symbol">${item.ticker}</span>
                <span class="ti-price">${fmtRp(item.current_price)}</span>
                <span class="ti-change ${chgClass}">${arrow} ${fmtPct(item.unrealized_pnl_pct)}</span>
                <span class="ti-dot">&#9679;</span>
            </span>`;
    }
    track.innerHTML = html;
}

// ── DASHBOARD ─────────────────────────────────────────────────────────

async function loadDashboard() {
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

        document.getElementById('dashboard-update-time').textContent = `Updated: ${new Date().toLocaleTimeString('id-ID')}`;

        // Apply stagger animation to market cards
        applyStaggerAnimation(document.querySelector('.market-cards'), '.market-card');
    } catch (err) {
        console.error('Dashboard error:', err);
    }
}

function renderDashboardTable(items) {
    const tbody = document.getElementById('dashboard-portfolio-body');
    if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="placeholder-text">Portfolio kosong. Tambahkan saham untuk memulai.</td></tr>`;
        return;
    }
    tbody.innerHTML = items.map((item, idx) => `
        <tr class="stagger-item" style="--delay:${idx * 40}ms">
            <td class="ticker-cell" onclick="quickAnalysis('${item.ticker}')">${item.ticker}</td>
            <td>${item.company_name || '-'}</td>
            <td>${item.sub_sector || '-'}</td>
            <td class="num">${fmt(item.lot)}</td>
            <td class="num">${fmtRp(item.avg_price)}</td>
            <td class="num">${fmtRp(item.current_price)}</td>
            <td class="num">${fmtRp(item.market_value)}</td>
            <td class="num ${pnlClass(item.unrealized_pnl)}">${fmtRp(item.unrealized_pnl)}</td>
            <td class="num ${pnlClass(item.unrealized_pnl_pct)}">${fmtPct(item.unrealized_pnl_pct)}</td>
        </tr>
    `).join('');
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
    // HTML legend
    if (legendEl) {
        legendEl.innerHTML = sorted.map((item, i) => {
            const pct = (item.market_value / total * 100).toFixed(1);
            const color = colors[i % colors.length];
            return `<div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:11px;font-family:'JetBrains Mono',monospace;">
                <span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:${color};flex-shrink:0;"></span>
                <span style="color:#eaf0f6;font-weight:500;">${item.ticker}</span>
                <span style="color:#8b9dc3;">${pct}%</span>
                <span style="color:#5a6f8c;">${fmtBigNum(item.market_value)}</span>
            </div>`;
        }).join('');
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

// ── PORTFOLIO ─────────────────────────────────────────────────────────

async function loadPortfolio() {
    try {
        portfolioData = await apiFetch(`${API}/api/portfolio`);
        renderPortfolioSummary(portfolioData.summary);
        showPortfolioView('all');
    } catch (err) { showToast('Gagal memuat portfolio', 'error'); }
}

function renderPortfolioSummary(s) {
    const uniqueLabel = s.total_unique && s.total_unique < s.total_items ? ` (${s.total_unique} saham)` : '';
    const container = document.getElementById('portfolio-summary');
    container.innerHTML = `
        <div class="summary-item stagger-item" style="--delay:0ms"><div class="label">Total Posisi</div><div class="value">${s.total_items}${uniqueLabel}</div></div>
        <div class="summary-item stagger-item" style="--delay:60ms"><div class="label">Total Cost</div><div class="value" id="ps-cost">Rp 0</div></div>
        <div class="summary-item stagger-item" style="--delay:120ms"><div class="label">Market Value</div><div class="value" id="ps-mv">Rp 0</div></div>
        <div class="summary-item stagger-item" style="--delay:180ms"><div class="label">Unrealized P&L</div><div class="value ${pnlClass(s.total_pnl)}" id="ps-pnl">Rp 0</div></div>
    `;
    animateCounter(document.getElementById('ps-cost'), s.total_cost, 700, 'Rp ');
    animateCounter(document.getElementById('ps-mv'), s.total_market_value, 700, 'Rp ');
    animateCounter(document.getElementById('ps-pnl'), s.total_pnl, 700, 'Rp ');
}

let portfolioSortCol = null;
let portfolioSortAsc = true;

function sortPortfolio(col) {
    if (portfolioSortCol === col) {
        portfolioSortAsc = !portfolioSortAsc;
    } else {
        portfolioSortCol = col;
        portfolioSortAsc = true;
    }
    // Update header icons
    document.querySelectorAll('#portfolio-table th.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    const activeHeader = document.querySelector(`#portfolio-table th.sortable[onclick*="'${col}'"]`);
    if (activeHeader) activeHeader.classList.add(portfolioSortAsc ? 'sort-asc' : 'sort-desc');

    // Sort items
    const stringCols = ['ticker', 'company_name', 'security_type', 'sub_sector', 'broker'];
    portfolioData.items.sort((a, b) => {
        let va = a[col], vb = b[col];
        if (stringCols.includes(col)) {
            va = (va || '').toLowerCase();
            vb = (vb || '').toLowerCase();
            return portfolioSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        va = va || 0; vb = vb || 0;
        return portfolioSortAsc ? va - vb : vb - va;
    });
    showPortfolioView('all');
}

function showPortfolioView(view, evt) {
    document.querySelectorAll('.tab-bar .tab').forEach(t => t.classList.remove('active'));
    if (evt && evt.target) evt.target.classList.add('active');
    const tbody = document.getElementById('portfolio-body');
    const items = portfolioData.items;
    if (items.length === 0) { tbody.innerHTML = `<tr><td colspan="14" class="placeholder-text">Portfolio kosong</td></tr>`; return; }

    const groupHeader = (icon, label, color, group) =>
        `<tr><td colspan="14" style="background:var(--bg-tertiary);font-weight:700;color:var(--${color});padding:12px;font-size:12px;">
            <i class="fas fa-${icon}" style="margin-right:6px;"></i> ${label} &mdash; MV: ${fmtRp(group.market_value)} | P&L: <span class="${pnlClass(group.pnl)}">${fmtRp(group.pnl)}</span>
        </td></tr>`;

    if (view === 'all') {
        tbody.innerHTML = items.map(i => portfolioRowHtml(i)).join('');
    } else if (view === 'combined') {
        const combined = portfolioData.combined || [];
        if (combined.length === 0) { tbody.innerHTML = items.map(i => portfolioRowHtml(i)).join(''); return; }
        tbody.innerHTML = combined.map(c => {
            const brokerLabel = c.brokers && c.brokers.length > 0 ? c.brokers.join(', ') : '';
            const brokerBadge = brokerLabel ? `<span style="font-size:10px;color:var(--text-muted);display:block;">${brokerLabel}</span>` : '';
            const multiTag = c.brokers && c.brokers.length > 1 ? `<span style="font-size:9px;background:var(--accent);color:#000;padding:1px 5px;border-radius:3px;margin-left:4px;">${c.brokers.length} sekuritas</span>` : '';
            return `<tr>
                <td class="checkbox-col"></td>
                <td class="ticker-cell" onclick="quickAnalysis('${c.ticker}')">${c.ticker}${multiTag}${brokerBadge}</td>
                <td>${c.company_name || '-'}</td>
                <td>${c.security_type}</td>
                <td>${c.sub_sector || '-'}</td>
                <td class="num">${fmt(c.lot)}</td>
                <td class="num">${fmt(c.shares)}</td>
                <td class="num">${fmtRp(c.avg_price)}</td>
                <td class="num">${fmtRp(c.total_cost)}</td>
                <td class="num">${fmtRp(c.current_price)}</td>
                <td class="num">${fmtRp(c.market_value)}</td>
                <td class="num ${pnlClass(c.unrealized_pnl)}">${fmtRp(c.unrealized_pnl)}</td>
                <td class="num ${pnlClass(c.unrealized_pnl_pct)}">${fmtPct(c.unrealized_pnl_pct)}</td>
                <td></td>
            </tr>`;
        }).join('');
    } else if (view === 'by-broker') {
        let html = '';
        for (const [broker, group] of Object.entries(portfolioData.by_broker)) {
            html += groupHeader('university', broker, 'blue-light', group);
            html += group.items.map(i => portfolioRowHtml(i)).join('');
        }
        tbody.innerHTML = html;
    } else if (view === 'by-type') {
        let html = '';
        for (const [type, group] of Object.entries(portfolioData.by_type)) {
            html += groupHeader('tag', type, 'accent', group);
            html += group.items.map(i => portfolioRowHtml(i)).join('');
        }
        tbody.innerHTML = html;
    } else if (view === 'by-sector') {
        let html = '';
        for (const [sector, group] of Object.entries(portfolioData.by_sector)) {
            html += groupHeader('building', sector, 'cyan', group);
            html += group.items.map(i => portfolioRowHtml(i)).join('');
        }
        tbody.innerHTML = html;
    }
    const selectAll = document.getElementById('portfolio-select-all');
    if (selectAll) selectAll.checked = false;
    updatePortfolioSelection();
}

function portfolioRowHtml(item) {
    const accLabel = item.account_type && item.account_type !== 'Reguler' ? ` [${item.account_type}]` : '';
    const brokerBadge = item.broker ? `<span style="font-size:10px;color:var(--text-muted);display:block;">${item.broker}${accLabel}</span>` : '';
    return `<tr>
        <td class="checkbox-col"><input type="checkbox" class="portfolio-checkbox" data-id="${item.id}" data-ticker="${item.ticker}" onchange="updatePortfolioSelection()"></td>
        <td class="ticker-cell" onclick="quickAnalysis('${item.ticker}')">${item.ticker}${brokerBadge}</td>
        <td>${item.company_name || '-'}</td>
        <td>${item.security_type}</td>
        <td>${item.sub_sector || '-'}</td>
        <td class="num">${fmt(item.lot)}</td>
        <td class="num">${fmt(item.shares)}</td>
        <td class="num">${fmtRp(item.avg_price)}</td>
        <td class="num">${fmtRp(item.total_cost)}</td>
        <td class="num">${fmtRp(item.current_price)}</td>
        <td class="num">${fmtRp(item.market_value)}</td>
        <td class="num ${pnlClass(item.unrealized_pnl)}">${fmtRp(item.unrealized_pnl)}</td>
        <td class="num ${pnlClass(item.unrealized_pnl_pct)}">${fmtPct(item.unrealized_pnl_pct)}</td>
        <td>
            <button class="btn btn-ghost btn-sm" onclick="openEditModal(${item.id},'${item.ticker}',${item.lot},${item.avg_price},'${item.security_type}','${(item.notes||'').replace(/'/g,"\\'")}','${(item.broker||'').replace(/'/g,"\\'")}','${item.account_type||'Reguler'}')"><i class="fas fa-edit"></i></button>
            <button class="btn btn-ghost btn-sm" onclick="deleteItem(${item.id},'${item.ticker}')" style="color:var(--red)"><i class="fas fa-trash"></i></button>
        </td>
    </tr>`;
}

async function refreshPortfolio() {
    showToast('Memperbarui harga saham...', 'info', 3000);
    try {
        const data = await apiFetch(`${API}/api/portfolio/refresh`, { method: 'POST' });
        showToast(data.message, 'success', 5000);
        loadDashboard();
    } catch (err) { showToast('Gagal refresh harga', 'error', 5000); }
}

// ── ADD STOCK ─────────────────────────────────────────────────────────

function onAssetTypeChange() {
    const type = document.getElementById('add-security-type').value.toLowerCase();
    // Hide all asset-specific fields
    document.querySelectorAll('.asset-field').forEach(el => el.style.display = 'none');
    // Show fields matching the selected type
    document.querySelectorAll(`.asset-${type}`).forEach(el => el.style.display = '');
    // Update required attributes
    const tickerInput = document.getElementById('add-ticker');
    const avgInput = document.getElementById('add-avg-price');
    const bondCode = document.getElementById('add-bond-code');
    const bondNominal = document.getElementById('add-bond-nominal');
    const rdName = document.getElementById('add-rd-name');
    // Reset required
    [tickerInput, avgInput, bondCode, bondNominal, rdName].forEach(el => { if (el) el.required = false; });
    if (type === 'obligasi') {
        bondCode.required = true;
        bondNominal.required = true;
    } else if (type === 'reksadana') {
        rdName.required = true;
    } else {
        tickerInput.required = true;
        avgInput.required = true;
    }
}

async function addStock(event) {
    event.preventDefault();
    const securityType = document.getElementById('add-security-type').value;
    const broker = document.getElementById('add-broker').value;
    const notes = document.getElementById('add-notes').value;
    const resultEl = document.getElementById('add-result');
    const type = securityType.toLowerCase();

    if (!broker) { showToast('Pilih sekuritas/broker terlebih dahulu!', 'error'); return; }
    const accountType = document.getElementById('add-account-type')?.value || 'Reguler';
    let payload = { security_type: securityType, broker, account_type: accountType, notes };

    if (type === 'obligasi') {
        payload.ticker = document.getElementById('add-bond-code').value.trim().toUpperCase();
        const nominal = parseFloat(document.getElementById('add-bond-nominal').value) || 0;
        const coupon = parseFloat(document.getElementById('add-bond-coupon').value) || 0;
        const bondPrice = parseFloat(document.getElementById('add-bond-price').value) || 100;
        payload.lot = 1;
        payload.shares = 1;
        payload.avg_price = bondPrice;
        payload.total_cost = nominal;
        payload.notes = `Nominal: Rp${nominal.toLocaleString('id-ID')} | Kupon: ${coupon}% | Harga: ${bondPrice}%${notes ? ' | ' + notes : ''}`;
    } else if (type === 'reksadana') {
        payload.ticker = document.getElementById('add-rd-name').value.trim().toUpperCase().replace(/\s+/g, '-').substring(0, 10);
        const unit = parseFloat(document.getElementById('add-rd-unit').value) || 0;
        const nav = parseFloat(document.getElementById('add-rd-nav').value) || 0;
        const totalInvest = parseFloat(document.getElementById('add-rd-total').value) || (unit * nav);
        payload.lot = Math.ceil(unit);
        payload.shares = Math.ceil(unit);
        payload.avg_price = nav || (totalInvest / (unit || 1));
        payload.company_name = document.getElementById('add-rd-name').value.trim();
        payload.notes = `Unit: ${unit} | NAV: Rp${nav.toLocaleString('id-ID')} | Total: Rp${totalInvest.toLocaleString('id-ID')}${notes ? ' | ' + notes : ''}`;
    } else {
        payload.ticker = document.getElementById('add-ticker').value.trim().toUpperCase();
        payload.lot = parseInt(document.getElementById('add-lot').value) || 0;
        payload.shares = parseInt(document.getElementById('add-shares').value) || 0;
        payload.avg_price = parseFloat(document.getElementById('add-avg-price').value) || 0;
    }

    try {
        const res = await fetch(`${API}/api/portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            resultEl.className = 'result-message success';
            resultEl.textContent = data.message;
            showToast(`${payload.ticker} ditambahkan ke portfolio!`, 'success');
            event.target.reset();
            onAssetTypeChange();
        } else {
            resultEl.className = 'result-message error';
            resultEl.textContent = data.detail || 'Gagal menambahkan';
        }
    } catch (err) {
        resultEl.className = 'result-message error';
        resultEl.textContent = 'Error: ' + err.message;
    }
}

// ── EDIT / DELETE ─────────────────────────────────────────────────────

function openEditModal(id, ticker, lot, avgPrice, secType, notes, broker, accountType) {
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-ticker').value = ticker;
    document.getElementById('edit-lot').value = lot;
    document.getElementById('edit-avg-price').value = avgPrice;
    document.getElementById('edit-security-type').value = secType;
    const editBrokerSel = document.getElementById('edit-broker');
    sortBrokerSelect(editBrokerSel);
    editBrokerSel.value = broker || '';
    const editAccType = document.getElementById('edit-account-type');
    if (editAccType) editAccType.value = accountType || 'Reguler';
    document.getElementById('edit-notes').value = notes;
    document.getElementById('edit-modal').classList.remove('hidden');
    const editPinBtn = document.querySelector('.broker-pin-btn[data-for="edit-broker"]');
    if (editPinBtn) updatePinButton(editPinBtn);
}
function closeEditModal() { document.getElementById('edit-modal').classList.add('hidden'); }

async function saveEdit(event) {
    event.preventDefault();
    const id = document.getElementById('edit-id').value;
    const lot = parseInt(document.getElementById('edit-lot').value);
    const avgPrice = parseFloat(document.getElementById('edit-avg-price').value);
    const securityType = document.getElementById('edit-security-type').value;
    const broker = document.getElementById('edit-broker').value;
    const accountType = document.getElementById('edit-account-type')?.value || 'Reguler';
    const notes = document.getElementById('edit-notes').value;
    try {
        const res = await fetch(`${API}/api/portfolio/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lot, avg_price: avgPrice, security_type: securityType, broker, account_type: accountType, notes })
        });
        if (res.ok) { showToast('Portfolio updated!', 'success'); closeEditModal(); loadPortfolio(); }
        else showToast('Gagal update', 'error');
    } catch (err) { showToast('Error: ' + err.message, 'error'); }
}

async function deleteItem(id, ticker) {
    if (!confirm(`Hapus ${ticker} dari portfolio?`)) return;
    try {
        await fetch(`${API}/api/portfolio/${id}`, { method: 'DELETE' });
        showToast(`${ticker} dihapus`, 'success');
        loadPortfolio();
    } catch (err) { showToast('Gagal menghapus', 'error'); }
}

// ── STOCK DETAIL (ENHANCED WITH TABS) ─────────────────────────────────

function quickAnalysis(ticker) {
    showPanel('stock-detail');
    document.getElementById('detail-ticker-input').value = ticker;
    loadStockDetail();
}

async function loadStockDetail() {
    const ticker = document.getElementById('detail-ticker-input').value.trim().toUpperCase();
    if (!ticker) return;
    const container = document.getElementById('stock-detail-content');
    showSkeleton('stock-detail-content', 'detail');
    currentDetailTicker = ticker;
    const thisRequestId = ++detailRequestId;

    try {
        // Fetch all data in parallel
        const [stockRes, histRes, newsRes, profileRes, finRes, ownerRes] = await Promise.all([
            fetch(`${API}/api/stock/${ticker}`),
            fetch(`${API}/api/stock/${ticker}/history?period=1mo`),
            fetch(`${API}/api/stock/${ticker}/news`),
            fetch(`${API}/api/stock/${ticker}/profile`),
            fetch(`${API}/api/stock/${ticker}/financials`),
            fetch(`${API}/api/stock/${ticker}/ownership`)
        ]);

        const stock = await stockRes.json();
        const hist = await histRes.json();
        const newsData = await newsRes.json();
        const profile = await profileRes.json();
        const fin = await finRes.json();
        const owner = await ownerRes.json();

        // Stale request guard: user may have searched another ticker while we were loading
        if (thisRequestId !== detailRequestId) return;

        if (stock.error && !stock.last_price) {
            container.innerHTML = `<p class="placeholder-text">${stock.error}</p>`;
            return;
        }

        // Build header
        const headerHtml = `
            <div class="stock-header">
                <span class="ticker-name">${stock.ticker}</span>
                <span class="company-name">${stock.company_name || profile.company_name || '-'}</span>
                <span class="price-big ${pnlClass(stock.change)}">${fmtRp(stock.last_price)}</span>
                <span class="${pnlClass(stock.change)}" style="font-size:16px;font-family:'JetBrains Mono',monospace;">
                    ${fmtChange(stock.change)} (${fmtPct(stock.change_pct)})
                </span>
            </div>`;

        // Build tabs navigation
        const tabsHtml = `
            <div class="detail-tabs">
                <button class="detail-tab active" onclick="switchDetailTab(event,'overview')"><i class="fas fa-chart-area"></i> Overview</button>
                <button class="detail-tab" onclick="switchDetailTab(event,'profile')"><i class="fas fa-building"></i> Profile</button>
                <button class="detail-tab" onclick="switchDetailTab(event,'financials')"><i class="fas fa-calculator"></i> Keuangan</button>
                <button class="detail-tab" onclick="switchDetailTab(event,'statements')"><i class="fas fa-file-invoice-dollar"></i> Lap. Keuangan</button>
                <button class="detail-tab" onclick="switchDetailTab(event,'ownership')"><i class="fas fa-users"></i> Kepemilikan</button>
                <button class="detail-tab" onclick="switchDetailTab(event,'news')"><i class="fas fa-newspaper"></i> Berita</button>
            </div>`;

        // ── Overview Tab ──
        const w52High = fin.fifty_two_week_high || 0;
        const w52Low = fin.fifty_two_week_low || 0;
        const w52Range = w52High - w52Low;
        const w52Pos = w52Range > 0 ? ((stock.last_price - w52Low) / w52Range * 100) : 50;

        const overviewHtml = `
            <div class="detail-tab-content active" id="dtab-overview">
                <div class="stock-info-grid">
                    <div class="stock-info-item"><div class="label">Open</div><div class="value">${fmtRp(stock.open_price)}</div></div>
                    <div class="stock-info-item"><div class="label">High</div><div class="value positive">${fmtRp(stock.high)}</div></div>
                    <div class="stock-info-item"><div class="label">Low</div><div class="value negative">${fmtRp(stock.low)}</div></div>
                    <div class="stock-info-item"><div class="label">Prev Close</div><div class="value">${fmtRp(stock.prev_close)}</div></div>
                    <div class="stock-info-item"><div class="label">Volume</div><div class="value">${fmt(stock.volume)}</div></div>
                    <div class="stock-info-item"><div class="label">Market Cap</div><div class="value">${fmtBigNum(stock.market_cap)}</div></div>
                    <div class="stock-info-item"><div class="label">P/E Ratio</div><div class="value">${fmtDecimal(fin.pe_trailing || stock.pe_ratio)}</div></div>
                    <div class="stock-info-item"><div class="label">P/B Ratio</div><div class="value">${fmtDecimal(fin.pb_ratio || stock.pb_ratio)}</div></div>
                    <div class="stock-info-item"><div class="label">Div Yield</div><div class="value">${fin.dividend_yield ? fin.dividend_yield.toFixed(2) + '%' : (stock.dividend_yield ? stock.dividend_yield.toFixed(2) + '%' : '-')}</div></div>
                    <div class="stock-info-item"><div class="label">Sector</div><div class="value" style="font-size:12px;">${stock.sector || '-'}</div></div>
                </div>

                ${w52High > 0 ? `
                <div class="range-bar-container">
                    <div class="range-bar-label"><span>52W Low: ${fmtRp(w52Low)}</span><span>52W High: ${fmtRp(w52High)}</span></div>
                    <div class="range-bar"><div class="range-bar-marker" style="left:${Math.min(100, Math.max(0, w52Pos))}%"></div></div>
                </div>` : ''}

                <div class="chart-container" style="margin-top:20px;">
                    <div class="chart-period-btns">
                        <button onclick="loadChart(event,'${ticker}','5d')" class="period-btn">5D</button>
                        <button onclick="loadChart(event,'${ticker}','1mo')" class="period-btn active">1M</button>
                        <button onclick="loadChart(event,'${ticker}','3mo')" class="period-btn">3M</button>
                        <button onclick="loadChart(event,'${ticker}','6mo')" class="period-btn">6M</button>
                        <button onclick="loadChart(event,'${ticker}','1y')" class="period-btn">1Y</button>
                        <button onclick="loadChart(event,'${ticker}','5y')" class="period-btn">5Y</button>
                    </div>
                    <div id="price-chart" style="height:280px;"></div>
                </div>

                <div class="fin-section" style="margin-top:20px;">
                    <div class="fin-section-title"><i class="fas fa-chart-line"></i> Key Statistics</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">50-Day Avg</div><div class="fi-value">${fmtRp(fin.fifty_day_avg)}</div></div>
                        <div class="fin-item"><div class="fi-label">200-Day Avg</div><div class="fi-value">${fmtRp(fin.two_hundred_day_avg)}</div></div>
                        <div class="fin-item"><div class="fi-label">Avg Vol (10D)</div><div class="fi-value">${fmt(fin.avg_volume_10d)}</div></div>
                        <div class="fin-item"><div class="fi-label">Beta</div><div class="fi-value">${fmtDecimal(fin.beta)}</div></div>
                    </div>
                </div>
            </div>`;

        // ── Profile Tab ──
        const officersHtml = (profile.officers || []).map(o => `
            <div class="officer-card">
                <div class="officer-avatar">${(o.name || '?').charAt(0)}</div>
                <div class="officer-info">
                    <div class="officer-name">${o.name || '-'}</div>
                    <div class="officer-title">${o.title || '-'}</div>
                </div>
            </div>`).join('');

        const profileHtml = `
            <div class="detail-tab-content" id="dtab-profile">
                <div class="profile-header">
                    <div class="profile-main">
                        <h3 style="font-size:20px;margin-bottom:12px;">${profile.company_name || stock.company_name || ticker}</h3>
                        <div>
                            ${profile.sector ? `<span class="profile-badge sector"><i class="fas fa-industry"></i> ${profile.sector}</span>` : ''}
                            ${profile.industry ? `<span class="profile-badge industry"><i class="fas fa-cogs"></i> ${profile.industry}</span>` : ''}
                            ${profile.employees ? `<span class="profile-badge employees"><i class="fas fa-users"></i> ${fmt(profile.employees)} karyawan</span>` : ''}
                        </div>
                        ${profile.website ? `<div style="margin-top:10px;"><a href="${profile.website}" target="_blank" style="color:var(--blue-light);font-size:12px;"><i class="fas fa-globe" style="margin-right:4px;"></i>${profile.website}</a></div>` : ''}
                        ${profile.address ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted);"><i class="fas fa-map-marker-alt" style="margin-right:4px;"></i>${profile.address}${profile.city ? ', ' + profile.city : ''}, ${profile.country || 'Indonesia'}</div>` : ''}
                    </div>
                </div>

                ${profile.business_summary ? `
                <div style="margin-bottom:24px;">
                    <div class="fin-section-title"><i class="fas fa-info-circle"></i> Tentang Perusahaan</div>
                    <div class="profile-summary">${profile.business_summary}</div>
                </div>` : ''}

                ${officersHtml ? `
                <div>
                    <div class="fin-section-title"><i class="fas fa-user-tie"></i> Manajemen & Direksi</div>
                    <div class="officers-grid">${officersHtml}</div>
                </div>` : '<p class="placeholder-text">Data manajemen tidak tersedia</p>'}
            </div>`;

        // ── Financials Tab (clean ratios/margins/valuation) ──
        const srcBadge = fin.source === 'tradingview' ? '<span style="font-size:9px;color:var(--cyan);background:rgba(34,211,238,0.1);padding:2px 6px;border-radius:4px;margin-left:8px;">TradingView</span>' : '<span style="font-size:9px;color:var(--text-muted);background:rgba(139,157,195,0.08);padding:2px 6px;border-radius:4px;margin-left:8px;">Yahoo Finance</span>';
        const financialsHtml = `
            <div class="detail-tab-content" id="dtab-financials">
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-tags"></i> Valuasi${srcBadge}</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">P/E (TTM)</div><div class="fi-value">${fmtDecimal(fin.pe_trailing)}</div></div>
                        <div class="fin-item"><div class="fi-label">PEG Ratio</div><div class="fi-value">${fmtDecimal(fin.peg_ratio)}</div></div>
                        <div class="fin-item"><div class="fi-label">P/B Ratio</div><div class="fi-value">${fmtDecimal(fin.pb_ratio)}</div></div>
                        <div class="fin-item"><div class="fi-label">P/S Ratio</div><div class="fi-value">${fmtDecimal(fin.ps_ratio)}</div></div>
                        <div class="fin-item"><div class="fi-label">EV/EBITDA</div><div class="fi-value">${fmtDecimal(fin.ev_ebitda)}</div></div>
                        <div class="fin-item"><div class="fi-label">Enterprise Value</div><div class="fi-value">${fmtBigNum(fin.enterprise_value)}</div></div>
                        <div class="fin-item"><div class="fi-label">Market Cap</div><div class="fi-value">${fmtBigNum(fin.market_cap)}</div></div>
                        <div class="fin-item"><div class="fi-label">Book Value/Share</div><div class="fi-value">${fmtRp(fin.book_value)}</div></div>
                    </div>
                </div>
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-percentage"></i> Margin & Profitabilitas</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">Gross Margin</div><div class="fi-value">${fmtPctVal(fin.gross_margin)}</div></div>
                        <div class="fin-item"><div class="fi-label">Operating Margin</div><div class="fi-value">${fmtPctVal(fin.operating_margin)}</div></div>
                        <div class="fin-item"><div class="fi-label">Pretax Margin</div><div class="fi-value">${fmtPctVal(fin.pretax_margin)}</div></div>
                        <div class="fin-item"><div class="fi-label">Net Margin</div><div class="fi-value">${fmtPctVal(fin.profit_margin)}</div></div>
                        <div class="fin-item"><div class="fi-label">FCF Margin</div><div class="fi-value">${fmtPctVal(fin.fcf_margin)}</div></div>
                        <div class="fin-item"><div class="fi-label">ROE</div><div class="fi-value">${fmtPctVal(fin.roe)}</div></div>
                        <div class="fin-item"><div class="fi-label">ROA</div><div class="fi-value">${fmtPctVal(fin.roa)}</div></div>
                        <div class="fin-item"><div class="fi-label">ROIC</div><div class="fi-value">${fmtPctVal(fin.roic)}</div></div>
                    </div>
                </div>
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-user-tie"></i> Per Saham</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">EPS (TTM)</div><div class="fi-value">${fmtRp(fin.eps_trailing)}</div></div>
                        <div class="fin-item"><div class="fi-label">EPS Diluted</div><div class="fi-value">${fmtRp(fin.eps_diluted)}</div></div>
                        <div class="fin-item"><div class="fi-label">Revenue/Share</div><div class="fi-value">${fmtRp(fin.revenue_per_share)}</div></div>
                        <div class="fin-item"><div class="fi-label">Dividend/Share</div><div class="fi-value">${fin.dividend_per_share ? fmtRp(fin.dividend_per_share) : '-'}</div></div>
                    </div>
                </div>
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-chart-bar"></i> Growth</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">Revenue YoY</div><div class="fi-value ${pnlClass(fin.revenue_growth)}">${fmtPctVal(fin.revenue_growth)}</div></div>
                        <div class="fin-item"><div class="fi-label">Earnings YoY</div><div class="fi-value ${pnlClass(fin.earnings_growth)}">${fmtPctVal(fin.earnings_growth)}</div></div>
                        <div class="fin-item"><div class="fi-label">Revenue QoQ</div><div class="fi-value ${pnlClass(fin.revenue_growth_qoq)}">${fmtPctVal(fin.revenue_growth_qoq)}</div></div>
                        <div class="fin-item"><div class="fi-label">Earnings QoQ</div><div class="fi-value ${pnlClass(fin.earnings_growth_qoq)}">${fmtPctVal(fin.earnings_growth_qoq)}</div></div>
                    </div>
                </div>
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-balance-scale"></i> Neraca & Rasio</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">Total Assets</div><div class="fi-value">${fmtBigNum(fin.total_assets)}</div></div>
                        <div class="fin-item"><div class="fi-label">Total Debt</div><div class="fi-value">${fmtBigNum(fin.total_debt)}</div></div>
                        <div class="fin-item"><div class="fi-label">Free Cash Flow</div><div class="fi-value ${pnlClass(fin.free_cashflow)}">${fmtBigNum(fin.free_cashflow)}</div></div>
                        <div class="fin-item"><div class="fi-label">D/E Ratio</div><div class="fi-value">${fmtDecimal(fin.debt_to_equity)}</div></div>
                        <div class="fin-item"><div class="fi-label">Current Ratio</div><div class="fi-value">${fmtDecimal(fin.current_ratio)}</div></div>
                        <div class="fin-item"><div class="fi-label">Quick Ratio</div><div class="fi-value">${fmtDecimal(fin.quick_ratio)}</div></div>
                    </div>
                </div>
                <div class="fin-section">
                    <div class="fin-section-title"><i class="fas fa-coins"></i> Dividen & Info</div>
                    <div class="fin-grid">
                        <div class="fin-item"><div class="fi-label">Dividend Yield</div><div class="fi-value">${fin.dividend_yield ? fin.dividend_yield.toFixed(2) + '%' : '-'}</div></div>
                        <div class="fin-item"><div class="fi-label">Beta (1Y)</div><div class="fi-value">${fmtDecimal(fin.beta)}</div></div>
                        <div class="fin-item"><div class="fi-label">Shares Outstanding</div><div class="fi-value">${fmtBigNum(fin.shares_outstanding)}</div></div>
                        <div class="fin-item"><div class="fi-label">Float Shares</div><div class="fi-value">${fmtBigNum(fin.float_shares)}</div></div>
                        <div class="fin-item"><div class="fi-label">Karyawan</div><div class="fi-value">${fin.employees ? fmt(fin.employees) : '-'}</div></div>
                    </div>
                </div>
            </div>`;

        // ── Financial Statements Tab (loads on demand) ──
        const statementsHtml = `
            <div class="detail-tab-content" id="dtab-statements">
                <div id="statements-loading" class="placeholder-text"><i class="fas fa-spinner fa-spin"></i> Memuat laporan keuangan...</div>
                <div id="statements-content" style="display:none;"></div>
            </div>`;

        // ── Ownership Tab ──
        let majorHtml = '';
        if (owner.major_holders && owner.major_holders.length > 0) {
            majorHtml = '<div class="holders-section"><h4><i class="fas fa-chart-pie" style="margin-right:6px;color:var(--accent);"></i>Ringkasan Kepemilikan</h4>';
            majorHtml += owner.major_holders.map(h => `
                <div class="holder-bar">
                    <span class="hb-value">${h.value}</span>
                    <span class="hb-name">${h.label}</span>
                </div>`).join('');
            majorHtml += '</div>';
        }

        let instHtml = '';
        if (owner.institutional_holders && owner.institutional_holders.length > 0) {
            instHtml = '<div class="holders-section"><h4><i class="fas fa-university" style="margin-right:6px;color:var(--blue-light);"></i>Pemegang Saham Institusional</h4>';
            instHtml += owner.institutional_holders.map(h => {
                const name = h['Holder'] || h['holder'] || h['Name'] || Object.values(h)[0] || '-';
                const shares = h['Shares'] || h['shares'] || h['Position'] || 0;
                const pctHeld = h['pctHeld'] || h['% Out'] || 0;
                const pctNum = typeof pctHeld === 'number' ? pctHeld : parseFloat(pctHeld) || 0;
                const pctDisplay = pctNum > 0 ? (pctNum < 1 ? (pctNum * 100).toFixed(2) : pctNum.toFixed(2)) + '%' : '';
                return `
                <div class="holder-bar">
                    <span class="hb-name">${name}</span>
                    <span class="hb-value">${typeof shares === 'number' ? fmt(shares) : shares}</span>
                    ${pctDisplay ? `<span class="hb-pct">${pctDisplay}</span>
                    <div class="holder-bar-visual"><div class="holder-bar-fill" style="width:${Math.min(100, pctNum < 1 ? pctNum * 100 : pctNum)}%"></div></div>` : ''}
                </div>`;
            }).join('');
            instHtml += '</div>';
        }

        let fundHtml = '';
        if (owner.insider_holders && owner.insider_holders.length > 0) {
            fundHtml = '<div class="holders-section"><h4><i class="fas fa-piggy-bank" style="margin-right:6px;color:var(--green-light);"></i>Pemegang Saham Reksadana</h4>';
            fundHtml += owner.insider_holders.map(h => {
                const name = h['Holder'] || h['holder'] || h['Name'] || Object.values(h)[0] || '-';
                const shares = h['Shares'] || h['shares'] || h['Position'] || 0;
                return `
                <div class="holder-bar">
                    <span class="hb-name">${name}</span>
                    <span class="hb-value">${typeof shares === 'number' ? fmt(shares) : shares}</span>
                </div>`;
            }).join('');
            fundHtml += '</div>';
        }

        const ownershipHtml = `
            <div class="detail-tab-content" id="dtab-ownership">
                ${majorHtml || ''}
                ${instHtml || ''}
                ${fundHtml || ''}
                ${!majorHtml && !instHtml && !fundHtml ? '<p class="placeholder-text">Data kepemilikan tidak tersedia untuk saham ini</p>' : ''}
            </div>`;

        // ── News Tab ──
        const newsHtml = `
            <div class="detail-tab-content" id="dtab-news">
                <div class="news-feed">
                    ${newsData.news.length > 0
                        ? newsData.news.map(n => `
                            <a href="${n.link}" target="_blank" class="news-item" style="text-decoration:none;">
                                <div class="news-title">${n.title}</div>
                                <div class="news-meta">
                                    <span class="news-ticker">${n.ticker}</span>
                                    <span>${n.source}</span>
                                    <span>${n.published ? new Date(n.published).toLocaleDateString('id-ID', {day:'2-digit',month:'short',year:'numeric'}) : ''}</span>
                                </div>
                            </a>`).join('')
                        : '<p class="placeholder-text">Tidak ada berita terbaru</p>'}
                </div>
            </div>`;

        container.innerHTML = headerHtml + tabsHtml + overviewHtml + profileHtml + financialsHtml + statementsHtml + ownershipHtml + newsHtml;

        // Render chart
        if (hist.data && hist.data.length > 0) renderPriceChart(hist.data);

    } catch (err) {
        container.innerHTML = `<p class="placeholder-text">Error: ${err.message}</p>`;
    }
}

function switchDetailTab(evt, tabId) {
    document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.detail-tab-content').forEach(c => c.classList.remove('active'));
    if (evt && evt.target) {
        const btn = evt.target.closest('.detail-tab');
        if (btn) btn.classList.add('active');
    }
    const tabEl = document.getElementById(`dtab-${tabId}`);
    if (tabEl) tabEl.classList.add('active');
    // Load financial statements on demand
    if (tabId === 'statements' && !document.getElementById('statements-content').innerHTML) {
        loadFinancialStatements(currentDetailTicker);
    }
}

async function loadFinancialStatements(ticker) {
    const loading = document.getElementById('statements-loading');
    const content = document.getElementById('statements-content');
    if (!loading || !content) return;
    loading.style.display = 'block';
    content.style.display = 'none';
    try {
        const res = await fetch(`${API}/api/stock/${ticker}/statements?quarters=8`);
        const data = await res.json();
        if (data.error || !data.quarters || data.quarters.length === 0) {
            loading.innerHTML = '<p class="placeholder-text">Data laporan keuangan tidak tersedia</p>';
            return;
        }
        const qs = data.quarters;
        const hdr = qs.map(q => `<th style="text-align:right;padding:4px 6px;font-size:10px;color:var(--cyan);white-space:nowrap;">${q.label}</th>`).join('');

        const stmtRow = (label, key, isCurrency = true) => {
            const cells = qs.map(q => {
                const v = q[key];
                if (v === null || v === undefined) return '<td style="text-align:right;padding:3px 6px;font-size:11px;color:var(--text-muted);">-</td>';
                const cls = !isCurrency ? '' : (v < 0 ? ' class="negative"' : (v > 0 ? '' : ''));
                const display = isCurrency ? fmtBigNum(v) : v.toFixed(2) + '%';
                return `<td style="text-align:right;padding:3px 6px;font-size:11px;"${cls}>${display}</td>`;
            }).join('');
            return `<tr><td style="padding:3px 6px;font-size:11px;color:var(--text-muted);white-space:nowrap;">${label}</td>${cells}</tr>`;
        };

        const tblStyle = 'width:100%;border-collapse:collapse;margin-bottom:4px;';
        const theadStyle = 'border-bottom:1px solid rgba(26,45,74,0.5);';

        const html = `
            <div class="fin-section">
                <div class="fin-section-title"><i class="fas fa-money-bill-wave"></i> Laporan Pemasukan (Income Statement)
                    <span style="font-size:9px;color:var(--cyan);background:rgba(34,211,238,0.1);padding:2px 6px;border-radius:4px;margin-left:8px;">TradingView</span>
                </div>
                <div style="overflow-x:auto;">
                <table style="${tblStyle}">
                    <thead><tr style="${theadStyle}">
                        <th style="text-align:left;padding:4px 6px;font-size:10px;color:var(--text-muted);"></th>${hdr}
                    </tr></thead>
                    <tbody>
                        ${stmtRow('Total Revenue', 'revenue')}
                        ${stmtRow('Gross Profit', 'gross_profit')}
                        ${stmtRow('EBITDA', 'ebitda')}
                        ${stmtRow('Net Income', 'net_income')}
                        ${stmtRow('EPS (Diluted)', 'eps')}
                        ${stmtRow('Gross Margin', 'gross_margin', false)}
                        ${stmtRow('Net Margin', 'net_margin', false)}
                    </tbody>
                </table>
                </div>
            </div>
            <div class="fin-section">
                <div class="fin-section-title"><i class="fas fa-balance-scale"></i> Neraca (Balance Sheet)</div>
                <div style="overflow-x:auto;">
                <table style="${tblStyle}">
                    <thead><tr style="${theadStyle}">
                        <th style="text-align:left;padding:4px 6px;font-size:10px;color:var(--text-muted);"></th>${hdr}
                    </tr></thead>
                    <tbody>
                        ${stmtRow('Total Assets', 'total_assets')}
                        ${stmtRow('Total Debt', 'total_debt')}
                        ${stmtRow('Total Equity*', 'total_equity')}
                    </tbody>
                </table>
                </div>
                <div style="font-size:9px;color:var(--text-muted);margin-top:2px;">*Equity = Assets - Debt (estimasi)</div>
            </div>
            <div class="fin-section">
                <div class="fin-section-title"><i class="fas fa-water"></i> Arus Kas (Cash Flow)</div>
                <div style="overflow-x:auto;">
                <table style="${tblStyle}">
                    <thead><tr style="${theadStyle}">
                        <th style="text-align:left;padding:4px 6px;font-size:10px;color:var(--text-muted);"></th>${hdr}
                    </tr></thead>
                    <tbody>
                        ${stmtRow('Free Cash Flow', 'free_cash_flow')}
                    </tbody>
                </table>
                </div>
            </div>`;

        content.innerHTML = html;
        loading.style.display = 'none';
        content.style.display = 'block';
    } catch (err) {
        loading.innerHTML = '<p class="placeholder-text">Gagal memuat laporan keuangan</p>';
        console.error('Statements error:', err);
    }
}

function renderPriceChart(data) {
    const container = document.getElementById('price-chart');
    if (!container) return;

    // Clean up previous chart
    if (priceChart) { priceChart.remove(); priceChart = null; }
    container.innerHTML = '';

    const prices = data.map(d => d.close);
    const isUp = prices[prices.length - 1] >= prices[0];
    const lineColor = isUp ? '#34d399' : '#f87171';
    const areaTopColor = isUp ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';
    const areaBottomColor = isUp ? 'rgba(16,185,129,0)' : 'rgba(239,68,68,0)';

    priceChart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#5a6f8c',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 10
        },
        grid: {
            vertLines: { color: 'rgba(26,45,74,0.2)' },
            horzLines: { color: 'rgba(26,45,74,0.2)' }
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: { color: 'rgba(249,115,22,0.3)', width: 1, style: 2, labelBackgroundColor: '#1a2d4a' },
            horzLine: { color: 'rgba(249,115,22,0.3)', width: 1, style: 2, labelBackgroundColor: '#1a2d4a' }
        },
        rightPriceScale: {
            borderColor: 'rgba(26,45,74,0.3)',
            scaleMargins: { top: 0.1, bottom: 0.1 }
        },
        timeScale: {
            borderColor: 'rgba(26,45,74,0.3)',
            timeVisible: false,
            fixLeftEdge: true,
            fixRightEdge: true
        },
        handleScroll: { vertTouchDrag: false },
        handleScale: { axisPressedMouseMove: { time: true, price: false } }
    });

    // Area series for price
    const areaSeries = priceChart.addAreaSeries({
        lineColor: lineColor,
        topColor: areaTopColor,
        bottomColor: areaBottomColor,
        lineWidth: 2,
        priceFormat: { type: 'custom', formatter: price => 'Rp ' + numeral(Math.round(price)).format('0,0') }
    });

    const chartData = data.map(d => ({ time: d.date, value: d.close }));
    areaSeries.setData(chartData);

    // Volume histogram if volume data available
    if (data[0] && data[0].volume !== undefined) {
        const volumeSeries = priceChart.addHistogramSeries({
            color: 'rgba(249,115,22,0.15)',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
            scaleMargins: { top: 0.85, bottom: 0 }
        });
        volumeSeries.setData(data.map(d => ({
            time: d.date,
            value: d.volume || 0,
            color: d.close >= (d.open || d.close) ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'
        })));
    }

    priceChart.timeScale().fitContent();
}

async function loadChart(evt, ticker, period) {
    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
    if (evt && evt.target) evt.target.classList.add('active');
    try {
        const res = await fetch(`${API}/api/stock/${ticker}/history?period=${period}`);
        const data = await res.json();
        if (data.data && data.data.length > 0) renderPriceChart(data.data);
    } catch (err) { console.error(err); }
}

// ── WATCHLIST ─────────────────────────────────────────────────────────

async function loadWatchlist() {
    try {
        const res = await fetch(`${API}/api/watchlist`);
        const data = await res.json();
        const container = document.getElementById('watchlist-grid');
        if (!container) return;

        const AG_PNL_CLASS = params => params.value > 0 ? 'pnl-positive' : params.value < 0 ? 'pnl-negative' : '';
        const colDefs = [
            { headerCheckboxSelection: true, checkboxSelection: true, width: 40, pinned: 'left' },
            { field: 'ticker', headerName: 'TICKER', width: 100, pinned: 'left',
              cellRenderer: p => `<span style="cursor:pointer;color:var(--accent);font-weight:600;" onclick="quickAnalysis('${p.value}')">${p.value}</span>` },
            { field: 'company_name', headerName: 'COMPANY', minWidth: 180, flex: 1 },
            { field: 'last_price', headerName: 'LAST PRICE', width: 120, type: 'numericColumn', valueFormatter: p => p.value != null ? fmtRp(p.value) : 'Rp -' },
            { field: 'change', headerName: 'CHANGE', width: 100, type: 'numericColumn',
              valueFormatter: p => p.value != null ? fmtChange(p.value) : '-', cellClass: AG_PNL_CLASS },
            { field: 'change_pct', headerName: 'CHANGE %', width: 100, type: 'numericColumn',
              valueFormatter: p => p.value != null ? fmtPct(p.value) : '-', cellClass: AG_PNL_CLASS },
            { field: 'volume', headerName: 'VOLUME', width: 110, type: 'numericColumn', valueFormatter: p => p.value != null ? fmt(p.value) : '-' },
            { headerName: 'AKSI', width: 70, sortable: false, filter: false,
              cellRenderer: p => `<button class="btn btn-ghost btn-sm" onclick="removeFromWatchlist('${p.data.ticker}')" style="color:var(--red)"><i class="fas fa-times"></i></button>` }
        ];

        if (!watchlistGridApi) {
            const gridOptions = {
                columnDefs: colDefs,
                rowData: data.watchlist,
                defaultColDef: { sortable: true, resizable: true, filter: true },
                rowSelection: 'multiple',
                animateRows: true,
                suppressCellFocus: true,
                domLayout: data.watchlist.length <= 15 ? 'autoHeight' : 'normal',
                overlayNoRowsTemplate: '<span style="color:var(--text-muted);padding:20px;">Watchlist kosong</span>',
                onSelectionChanged: () => {
                    const count = watchlistGridApi.getSelectedRows().length;
                    const btn = document.getElementById('watchlist-bulk-delete');
                    const countEl = document.getElementById('watchlist-selected-count');
                    if (countEl) countEl.textContent = count;
                    if (btn) btn.classList.toggle('hidden', count === 0);
                }
            };
            watchlistGridApi = agGrid.createGrid(container, gridOptions);
        } else {
            watchlistGridApi.setGridOption('rowData', data.watchlist);
        }
    } catch (err) { showToast('Gagal memuat watchlist', 'error'); }
}

async function removeFromWatchlist(ticker) {
    try {
        await fetch(`${API}/api/watchlist/${ticker}`, { method: 'DELETE' });
        showToast(`${ticker} dihapus dari watchlist`, 'success');
        loadWatchlist();
    } catch (err) { showToast('Gagal menghapus', 'error'); }
}

// ── NEWS ──────────────────────────────────────────────────────────────

let cachedNews = [];

// Urgency keywords with weights (higher = more urgent)
const URGENCY_RULES = [
    // Critical (suspension, delisting, legal, fraud)
    { keywords: ['suspend', 'delisting', 'default', 'pailit', 'bangkrut', 'fraud', 'penipuan', 'korupsi', 'ditangkap', 'tersangka', 'sanksi', 'denda', 'gugatan', 'sengketa', 'gagal bayar'], score: 100, label: 'KRITIS', level: 'critical' },
    // High (corporate actions, insider activity, major events)
    { keywords: ['akuisisi', 'merger', 'right issue', 'rights issue', 'buyback', 'insider', 'tender offer', 'stock split', 'reverse stock', 'privatisasi', 'likuidasi', 'restrukturisasi', 'rugi besar', 'kerugian signifikan', 'ekspansi', 'pabrik baru', 'tambang baru'], score: 80, label: 'TINGGI', level: 'high' },
    // Medium (financial results, dividends, RUPS, corporate disclosure)
    { keywords: ['dividen', 'dividend', 'laba bersih', 'laba rugi', 'laporan keuangan', 'pendapatan naik', 'pendapatan turun', 'revenue', 'earning', 'rups', 'rupst', 'rupslb', 'direksi', 'komisaris', 'direktur utama', 'kontrak baru', 'proyek baru', 'kerjasama', 'partnership', 'joint venture', 'obligasi', 'surat utang', 'rating', 'upgrade', 'downgrade', 'investasi saham'], score: 60, label: 'SEDANG', level: 'medium' },
    // Low (recommendations, analyst opinions, general market)
    { keywords: ['rekomendasi', 'target harga', 'analis', 'sekuritas hari ini', 'top picks', 'pilihan saham', 'saham pilihan', 'prediksi', 'prospek', 'outlook', 'saham unggulan', 'saham murah', 'saham potensial'], score: 20, label: 'RENDAH', level: 'low' },
    // Info (very general)
    { keywords: ['saham', 'ihsg', 'bursa', 'pasar modal'], score: 10, label: 'INFO', level: 'info' },
];

function scoreNewsUrgency(newsItem) {
    const title = (newsItem.title || '').toLowerCase();
    const summary = (newsItem.summary || '').toLowerCase();
    const text = title + ' ' + summary;
    let maxScore = 0;
    let label = 'INFO';
    let level = 'info';

    for (const rule of URGENCY_RULES) {
        for (const kw of rule.keywords) {
            if (text.includes(kw)) {
                if (rule.score > maxScore) {
                    maxScore = rule.score;
                    label = rule.label;
                    level = rule.level;
                }
                break;
            }
        }
    }

    // Recency boost: news from today gets +15, yesterday +10, this week +5
    if (newsItem.published) {
        const hoursAgo = (Date.now() - new Date(newsItem.published).getTime()) / 3600000;
        if (hoursAgo < 24) maxScore += 15;
        else if (hoursAgo < 48) maxScore += 10;
        else if (hoursAgo < 168) maxScore += 5;
    }

    return { score: maxScore, label, level };
}

function sortNewsByUrgency(news) {
    return news.map(n => ({ ...n, urgency: scoreNewsUrgency(n) }))
        .sort((a, b) => b.urgency.score - a.urgency.score);
}

function sortNewsByDate(news) {
    return [...news].sort((a, b) => new Date(b.published) - new Date(a.published));
}

function dedupeNews(news) {
    const seen = new Set();
    return news.filter(n => {
        // Filter out TradingView technical analysis noise
        const src = (n.source || '').toLowerCase();
        if (src.includes('tradingview')) return false;

        const key = n.title.replace(/\s+/g, ' ').trim().toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function resortNews() {
    if (cachedNews.length === 0) return;
    cachedNews = dedupeNews(cachedNews);
    const sortMode = document.getElementById('news-sort').value;
    const container = document.getElementById('news-feed');
    const sorted = sortMode === 'urgency' ? sortNewsByUrgency(cachedNews) : sortNewsByDate(cachedNews);
    renderNewsFeed(container, sorted, sortMode === 'urgency');
}

let newsLoadedCount = 0;
let newsLoading = false;
const NEWS_BATCH_SIZE = 10;

async function loadNews(loadMore = false) {
    if (newsLoading && !loadMore) return;
    newsLoading = true;
    const ticker = document.getElementById('news-ticker-input').value.trim().toUpperCase();
    const container = document.getElementById('news-feed');

    if (!loadMore) {
        showSkeleton('news-feed', 'table');
        newsLoadedCount = 0;
        cachedNews = [];
    }

    if (!ticker) {
        if (portfolioData && portfolioData.items.length > 0) {
            const allTickers = [...new Set(portfolioData.items.map(i => i.ticker))];
            const batch = allTickers.slice(newsLoadedCount, newsLoadedCount + NEWS_BATCH_SIZE);
            if (batch.length === 0) {
                if (!loadMore) container.innerHTML = '<p class="placeholder-text">Tidak ada berita ditemukan untuk saham di portfolio</p>';
                return;
            }

            if (loadMore) {
                // Remove the "load more" button while loading
                const loadMoreBtn = container.querySelector('.news-load-more');
                if (loadMoreBtn) loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Memuat...';
            }

            try {
                const results = await Promise.allSettled(
                    batch.map(t => fetch(`${API}/api/stock/${t}/news`).then(r => r.json()))
                );
                let batchNews = [];
                for (const r of results) {
                    if (r.status === 'fulfilled' && r.value.news) {
                        batchNews = batchNews.concat(r.value.news);
                    }
                }
                newsLoadedCount += batch.length;
                cachedNews = cachedNews.concat(batchNews);

                if (cachedNews.length === 0) {
                    container.innerHTML = '<p class="placeholder-text">Tidak ada berita ditemukan untuk saham di portfolio</p>';
                } else {
                    resortNews();
                    // Add "load more" button if there are more tickers
                    if (newsLoadedCount < allTickers.length) {
                        const remaining = allTickers.length - newsLoadedCount;
                        container.insertAdjacentHTML('beforeend',
                            `<button class="btn btn-ghost news-load-more" onclick="loadNews(true)" style="width:100%;padding:12px;margin-top:8px;border:1px dashed var(--border);border-radius:8px;color:var(--accent);font-size:12px;">
                                <i class="fas fa-plus"></i> Muat lebih banyak (${remaining} saham lagi, ${newsLoadedCount}/${allTickers.length} dimuat)
                            </button>`);
                    } else {
                        container.insertAdjacentHTML('beforeend',
                            `<div style="text-align:center;padding:8px;color:var(--text-muted);font-size:11px;">Semua ${allTickers.length} saham dimuat</div>`);
                    }
                }
            } catch (err) {
                container.innerHTML = `<p class="placeholder-text">Gagal memuat berita: ${err.message}</p>`;
            }
        } else {
            container.innerHTML = '<p class="placeholder-text">Masukkan ticker atau tambah saham ke portfolio terlebih dahulu</p>';
        }
        newsLoading = false;
        return;
    }
    try {
        const res = await fetch(`${API}/api/stock/${ticker}/news`);
        const data = await res.json();
        cachedNews = data.news;
        if (data.news.length === 0) {
            container.innerHTML = `<p class="placeholder-text">Tidak ada berita ditemukan untuk ${ticker}</p>`;
        } else {
            resortNews();
        }
    } catch (err) {
        container.innerHTML = `<p class="placeholder-text">Gagal memuat berita: ${err.message}</p>`;
    } finally {
        newsLoading = false;
    }
}

function renderNewsFeed(container, news, showUrgency = true) {
    news = dedupeNews(news);
    if (news.length === 0) { container.innerHTML = '<p class="placeholder-text">Tidak ada berita ditemukan</p>'; return; }
    container.innerHTML = news.map((n, idx) => {
        const urg = n.urgency || scoreNewsUrgency(n);
        const urgBadge = showUrgency ? `<span class="news-urgency urgency-${urg.level}">${urg.label}</span>` : '';
        return `
        <a href="${n.link}" target="_blank" class="news-item news-border-${urg.level}" style="text-decoration:none;">
            <div class="news-title">${urgBadge}${n.title}</div>
            <div class="news-meta">
                <span class="news-ticker">${n.ticker}</span>
                <span>${n.source}</span>
                <span>${n.published ? new Date(n.published).toLocaleDateString('id-ID', {day:'2-digit',month:'short',year:'numeric'}) : ''}</span>
            </div>
        </a>`;
    }).join('');
}

// ── DISCLOSURE ────────────────────────────────────────────────────────

function formatDisclosureDate(raw) {
    if (!raw) return '-';
    try {
        const d = new Date(raw);
        if (isNaN(d.getTime())) return raw;
        const dd = String(d.getDate()).padStart(2, '0');
        const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
        const mm = months[d.getMonth()];
        const yy = d.getFullYear();
        const hh = String(d.getHours()).padStart(2, '0');
        const mi = String(d.getMinutes()).padStart(2, '0');
        return `${dd} ${mm} ${yy}, ${hh}:${mi}`;
    } catch { return raw; }
}

async function loadDisclosure() {
    const ticker = document.getElementById('disclosure-ticker-input').value.trim().toUpperCase();
    const container = document.getElementById('disclosure-content');
    showSkeleton('disclosure-content', 'table');
    try {
        const res = await fetch(`${API}/api/disclosure?ticker=${ticker}`);
        const data = await res.json();
        if (!data.disclosures || data.disclosures.length === 0) {
            container.innerHTML = '<p class="placeholder-text">Tidak ada data keterbukaan informasi</p>';
            return;
        }
        container.innerHTML = data.disclosures.map((d, idx) => `
            <div class="disclosure-item">
                <div class="disc-info">
                    <div>
                        <span class="disc-ticker">${d.ticker || ''}</span>
                        <span class="disc-title">${d.title || d.subject || ''}</span>
                    </div>
                    <div class="disc-date"><i class="fas fa-clock"></i> ${formatDisclosureDate(d.date)}</div>
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span class="disc-type">${d.type || 'Info'}</span>
                    ${d.link ? `<a href="${d.link}" target="_blank" rel="noopener" class="disc-download" data-tippy-content="Download PDF"><i class="fas fa-file-pdf"></i></a>` : ''}
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<p class="placeholder-text">Gagal memuat: ${err.message}</p>`;
    }
}

// ── SCREENSHOT OCR ────────────────────────────────────────────────────

async function processScreenshot(file) {
    const statusEl = document.getElementById('ocr-status');
    statusEl.textContent = 'Memproses screenshot...';
    statusEl.className = 'result-message';
    statusEl.style.background = 'rgba(59,130,246,0.1)';
    statusEl.style.color = '#60a5fa';
    statusEl.style.border = '1px solid rgba(59,130,246,0.2)';

    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(`${API}/api/ocr/screenshot`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error && data.stocks.length === 0) {
            statusEl.className = 'result-message error';
            let msg = data.error;
            if (data.instructions) msg += '\n' + data.instructions;
            if (data.raw_text) {
                msg += '\n\n── Raw OCR Text (debug) ──\n' + data.raw_text.substring(0, 1000);
            }
            statusEl.textContent = msg;
            statusEl.style.whiteSpace = 'pre-wrap';
            statusEl.style.maxHeight = '300px';
            statusEl.style.overflowY = 'auto';
            statusEl.style.fontSize = '11px';
            return;
        }
        ocrResults = data.stocks;
        const previewEl = document.getElementById('ocr-preview');
        const resultsEl = document.getElementById('ocr-results');
        previewEl.classList.remove('hidden');
        resultsEl.innerHTML = ocrResults.map((s, i) => `
            <div class="ocr-stock-item">
                <input type="checkbox" id="ocr-check-${i}" checked>
                <span class="ocr-ticker">${s.ticker}</span>
                <span>Lot: <input type="number" value="${s.lot}" onchange="ocrResults[${i}].lot=parseInt(this.value)" style="width:60px;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:4px 8px;border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:12px;"></span>
                <span>Avg: <input type="number" value="${s.avg_price}" onchange="ocrResults[${i}].avg_price=parseFloat(this.value)" style="width:100px;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:4px 8px;border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:12px;"></span>
                <span style="color:var(--text-muted);font-size:11px;">${s.raw_line || ''}</span>
            </div>
        `).join('');
        statusEl.textContent = `${ocrResults.length} saham terdeteksi`;
        statusEl.className = 'result-message success';
    } catch (err) {
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'result-message error';
    }
}

async function importOcrResults() {
    const selected = ocrResults.filter((_, i) => document.getElementById(`ocr-check-${i}`).checked);
    if (selected.length === 0) { showToast('Pilih saham yang ingin diimport', 'error'); return; }
    const broker = document.getElementById('ocr-broker').value;
    if (!broker) { showToast('Pilih sekuritas/broker terlebih dahulu!', 'error'); return; }
    const accountType = document.getElementById('ocr-account-type')?.value || 'Reguler';
    try {
        const res = await fetch(`${API}/api/ocr/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stocks: selected, broker, account_type: accountType })
        });
        const data = await res.json();
        if (res.ok) {
            const skipMsg = data.skipped_count ? ` (${data.skipped_count} duplikat diskip)` : '';
            showToast(`${data.count} saham berhasil diimport!${skipMsg}`, 'success');
            document.getElementById('ocr-preview').classList.add('hidden');
            ocrResults = [];
            // Reset file input so user can upload another screenshot
            const fileInput = document.getElementById('screenshot-input');
            if (fileInput) fileInput.value = '';
            document.getElementById('upload-area').style.display = '';
            const ocrStatus = document.getElementById('ocr-status');
            if (ocrStatus) ocrStatus.textContent = '';
            loadDashboard();
            loadWatchlist();
        } else {
            showToast('Gagal import: ' + (data.detail || JSON.stringify(data)), 'error');
        }
    } catch (err) { showToast('Gagal import: ' + err.message, 'error'); }
}

// ── PASTE FROM EXCEL IMPORT ─────────────────────────────────────────

let pasteResults = [];

function switchImportTab(tab) {
    const screenshotTab = document.getElementById('import-tab-screenshot');
    const pasteTab = document.getElementById('import-tab-paste');
    const panel = document.getElementById('panel-screenshot');
    const btns = panel ? panel.querySelectorAll('.tab-bar .tab') : [];

    if (tab === 'paste') {
        screenshotTab.style.display = 'none';
        pasteTab.style.display = 'block';
    } else {
        screenshotTab.style.display = 'block';
        pasteTab.style.display = 'none';
    }

    btns.forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase().includes(tab === 'paste' ? 'paste' : 'screenshot'));
    });
}

function parsePasteData() {
    const raw = document.getElementById('paste-input').value;
    if (!raw || !raw.trim()) { showToast('Paste data dari Excel terlebih dahulu', 'error'); return; }

    const lines = raw.split('\n').map(l => l.replace(/\r$/, '').replace(/\s+$/, '')).filter(l => l.trim().length > 0);
    pasteResults = [];

    // Auto-detect separator: tabs or spaces
    const usesTabs = lines.some(l => (l.match(/\t/g) || []).length >= 3);

    function splitLine(line) {
        if (usesTabs) return line.split('\t').map(c => c.trim());
        // For space-separated: split on any whitespace
        return line.split(/\s+/).map(c => c.trim()).filter(c => c.length > 0);
    }

    // Parse number: handle both comma (8,436) and dot (8.436) as thousands separators
    // Indonesian format uses dots: 1.253.000 = 1253000
    // International uses commas: 1,253,000 = 1253000
    function parseNum(s) {
        if (!s) return 0;
        s = s.toString().trim().replace(/\s/g, '');
        const neg = (s.startsWith('(') && s.endsWith(')')) || s.startsWith('-');
        if (s.startsWith('(') && s.endsWith(')')) s = s.slice(1, -1);
        if (s.startsWith('-')) s = s.slice(1);

        // Detect format: if has multiple dots like "1.253.000" → dot is thousands sep
        const dots = (s.match(/\./g) || []).length;
        const commas = (s.match(/,/g) || []).length;

        if (dots > 1) {
            // Indonesian: 1.253.000 → remove all dots
            s = s.replace(/\./g, '');
        } else if (commas > 0 && dots <= 1) {
            // International: 1,253,000 or 1,253.50 → remove commas
            s = s.replace(/,/g, '');
        } else if (dots === 1 && commas === 0) {
            // Could be decimal (12.5) or thousands (12.530)
            // If digits after dot are exactly 3 and no decimal context, treat as thousands
            const afterDot = s.split('.')[1];
            if (afterDot && afterDot.length === 3 && parseInt(afterDot) > 0) {
                // Likely thousands separator: 12.530 → 12530
                s = s.replace('.', '');
            }
            // else keep as decimal
        }

        const n = parseFloat(s);
        return isNaN(n) ? 0 : (neg ? -n : n);
    }

    // Header keywords for each column
    const HEADER_KEYS = {
        code: ['code', 'kode', 'ticker', 'saham', 'stock'],
        avg: ['avg', 'avg price', 'average', 'harga avg', 'avg.', 'cost', 'buy price', 'buy avg'],
        lot: ['lot', 'lots'],
        shares: ['shares', 'lembar', 'share', 'qty', 'quantity', 'vol'],
        last: ['last', 'last price', 'harga', 'price', 'current', 'close'],
        value: ['value', 'nilai', 'market value', 'mkt value', 'mkt val', 'amount']
    };

    // Detect header row to find column indices
    let colMap = null;
    let startIdx = 0;

    // For space-separated data, we'll also build a list of expected column order from header
    let headerOrder = []; // e.g. ['no', 'code', 'notasi', 'avg', 'last', 'lot', 'shares', 'value', 'pnl', 'pct']

    for (let i = 0; i < Math.min(lines.length, 5); i++) {
        const cols = splitLine(lines[i]);
        const lower = cols.map(c => c.toLowerCase().trim());
        // Look for a header containing code-like keyword
        const codeIdx = lower.findIndex(c => HEADER_KEYS.code.includes(c));
        if (codeIdx >= 0) {
            colMap = {};
            lower.forEach((c, j) => {
                for (const [key, keywords] of Object.entries(HEADER_KEYS)) {
                    if (keywords.includes(c) && colMap[key] === undefined) colMap[key] = j;
                }
            });
            headerOrder = lower;
            startIdx = i + 1;
            break;
        }
    }

    // If no header detected, try to auto-detect from data pattern
    if (!colMap) {
        const firstCols = splitLine(lines[0]);
        if (firstCols.length >= 3) {
            const hasRowNum = /^\d+$/.test(firstCols[0].trim());
            if (hasRowNum && firstCols.length >= 8) {
                // Format: No, Code, Notasi, Avg, Last, Lot, Shares, Value, PnL, %
                colMap = { code: 1, avg: 3, last: 4, lot: 5, shares: 6, value: 7 };
            } else if (hasRowNum && firstCols.length >= 4) {
                // Shorter: No, Code, Avg, Lot, ...
                colMap = { code: 1, avg: 2, lot: 3 };
                if (firstCols.length >= 5) colMap.shares = 4;
                if (firstCols.length >= 6) colMap.last = 5;
            } else if (!hasRowNum && firstCols.length >= 6) {
                colMap = { code: 0, avg: 2, last: 3, lot: 4, shares: 5, value: 6 };
            } else if (!hasRowNum && firstCols.length >= 3) {
                colMap = { code: 0, avg: 1, lot: 2 };
            }
        }
        startIdx = 0;
    }

    if (!colMap || colMap.code === undefined) {
        showToast('Format tidak dikenali. Pastikan ada kolom Code/Ticker.', 'error');
        return;
    }

    for (let i = startIdx; i < lines.length; i++) {
        const cols = splitLine(lines[i]);
        if (cols.length < 3) continue;

        let code, avg, lot, shares, last, value;

        if (usesTabs) {
            // Tab-separated: columns align with header perfectly
            code = (cols[colMap.code] || '').trim().replace(/\*/g, '').replace(/\s/g, '').toUpperCase();
            avg = parseNum(cols[colMap.avg !== undefined ? colMap.avg : 2]);
            lot = colMap.lot !== undefined ? parseNum(cols[colMap.lot]) : 0;
            shares = colMap.shares !== undefined ? parseNum(cols[colMap.shares]) : lot * 100;
            last = colMap.last !== undefined ? parseNum(cols[colMap.last]) : 0;
            value = colMap.value !== undefined ? parseNum(cols[colMap.value]) : 0;
        } else {
            // Space-separated: tokens may shift due to empty columns
            // Strategy: find the ticker (uppercase letters 2-5 chars), then take numbers in order
            const tickerIdx = cols.findIndex(c => /^[A-Z]{2,5}$/.test(c.replace(/\*/g, '').trim().toUpperCase()) && !/^\d/.test(c));
            if (tickerIdx < 0) continue;
            code = cols[tickerIdx].replace(/\*/g, '').trim().toUpperCase();

            // Collect all numeric tokens after the ticker (skip * notation markers)
            const nums = [];
            for (let j = tickerIdx + 1; j < cols.length; j++) {
                const cleaned = cols[j].replace(/\*/g, '').trim();
                if (cleaned === '' || cleaned === '*') continue;
                // Check if it's a number-like token
                if (/^-?[\d.,()]+%?$/.test(cleaned)) {
                    nums.push(cleaned.replace(/%$/, ''));
                }
            }

            // Map numbers to columns based on header order (after code)
            // Expected order from header: avg, last, lot, shares, value, pnl, pct
            // But we only need: avg, last, lot, shares, value
            avg = nums.length > 0 ? parseNum(nums[0]) : 0;   // Avg
            last = nums.length > 1 ? parseNum(nums[1]) : 0;   // Last
            lot = nums.length > 2 ? parseNum(nums[2]) : 0;    // Lot
            shares = nums.length > 3 ? parseNum(nums[3]) : lot * 100; // Shares
            value = nums.length > 4 ? parseNum(nums[4]) : 0;  // Value
        }

        if (!code || code.length < 2 || /^(TOTAL|JUMLAH|SUM|GRAND)/i.test(code)) continue;
        if (/^\d+$/.test(code)) continue;
        if (/^(CODE|KODE|TICKER|SAHAM|NOTASI|NO)$/i.test(code)) continue;

        if (avg <= 0 && lot <= 0 && shares <= 0) continue;

        // Skip delisted stocks (last_price=0 and value=0)
        if (last <= 0 && value <= 0) continue;

        pasteResults.push({ ticker: code, avg_price: avg, lot: Math.round(lot), shares: Math.round(shares), last_price: last, value: Math.round(value), checked: true });
    }

    if (pasteResults.length === 0) {
        showToast('Tidak ada data saham yang valid ditemukan', 'error');
        return;
    }

    // Render preview table
    const tbody = document.getElementById('paste-table-body');
    tbody.innerHTML = pasteResults.map((s, i) => `
        <tr>
            <td class="checkbox-col"><input type="checkbox" id="paste-check-${i}" checked></td>
            <td><strong>${s.ticker}</strong></td>
            <td>${fmtRp(s.avg_price)}</td>
            <td>${fmt(s.lot)}</td>
            <td>${fmt(s.shares)}</td>
            <td>${fmtRp(s.last_price)}</td>
            <td>${fmtRp(s.value)}</td>
        </tr>
    `).join('');

    document.getElementById('paste-preview').classList.remove('hidden');
    document.getElementById('paste-select-all').checked = true;

    const statusEl = document.getElementById('paste-status');
    statusEl.textContent = `${pasteResults.length} saham berhasil diparsing`;
    statusEl.className = 'result-message success';

    showToast(`${pasteResults.length} saham terdeteksi dari paste data`, 'success');
}

function toggleAllPaste(master) {
    pasteResults.forEach((_, i) => {
        const cb = document.getElementById(`paste-check-${i}`);
        if (cb) cb.checked = master.checked;
    });
}

async function importPasteResults() {
    const selected = pasteResults.filter((_, i) => {
        const cb = document.getElementById(`paste-check-${i}`);
        return cb && cb.checked;
    });
    if (selected.length === 0) { showToast('Pilih saham yang ingin diimport', 'error'); return; }

    const broker = document.getElementById('paste-broker').value;
    if (!broker) { showToast('Pilih sekuritas/broker terlebih dahulu!', 'error'); return; }
    const accountType = document.getElementById('paste-account-type')?.value || 'Reguler';
    const statusEl = document.getElementById('paste-status');
    statusEl.textContent = 'Mengimport...';
    statusEl.className = 'result-message';

    try {
        const res = await fetch(`${API}/api/ocr/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stocks: selected, broker, account_type: accountType })
        });
        const data = await res.json();
        if (res.ok) {
            const skipMsg = data.skipped_count ? ` (${data.skipped_count} duplikat diskip)` : '';
            showToast(`${data.count} saham berhasil diimport!${skipMsg}`, 'success');
            statusEl.textContent = `${data.count} saham berhasil diimport${skipMsg}`;
            statusEl.className = 'result-message success';
            document.getElementById('paste-preview').classList.add('hidden');
            document.getElementById('paste-input').value = '';
            pasteResults = [];
            loadDashboard();
            loadWatchlist();
        } else {
            const msg = data.detail || JSON.stringify(data);
            showToast('Gagal import: ' + msg, 'error');
            statusEl.textContent = 'Gagal: ' + msg;
            statusEl.className = 'result-message error';
        }
    } catch (err) {
        showToast('Gagal import: ' + err.message, 'error');
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'result-message error';
    }
}

// ── EXPORT TO EXCEL ─────────────────────────────────────────────────

function exportPortfolioExcel() {
    if (!portfolioData || !portfolioData.items || portfolioData.items.length === 0) {
        showToast('Portfolio kosong, tidak ada data untuk diexport', 'error');
        return;
    }

    const items = portfolioData.items;
    const summary = portfolioData.summary;

    // Build main portfolio sheet data
    const rows = items.map((item, i) => ({
        'No': i + 1,
        'Ticker': item.ticker,
        'Company': item.company_name || '',
        'Tipe': item.security_type || '',
        'Sektor': item.sub_sector || '',
        'Broker': item.broker || '',
        'Akun': item.account_type || 'Reguler',
        'Lot': item.lot,
        'Shares': item.shares,
        'Avg Price': item.avg_price,
        'Total Cost': item.total_cost,
        'Last Price': item.current_price,
        'Market Value': item.market_value,
        'Unrealized P&L': item.unrealized_pnl,
        'P&L %': Math.round(item.unrealized_pnl_pct * 100) / 100,
    }));

    // Summary row
    rows.push({});
    rows.push({
        'No': '',
        'Ticker': 'TOTAL',
        'Company': `${summary.total_items} posisi`,
        'Tipe': '',
        'Sektor': '',
        'Broker': '',
        'Akun': '',
        'Lot': '',
        'Shares': '',
        'Avg Price': '',
        'Total Cost': summary.total_cost,
        'Last Price': '',
        'Market Value': summary.total_market_value,
        'Unrealized P&L': summary.total_pnl,
        'P&L %': Math.round(summary.total_pnl_pct * 100) / 100,
    });

    const ws = XLSX.utils.json_to_sheet(rows);

    // Set column widths
    ws['!cols'] = [
        { wch: 4 },   // No
        { wch: 8 },   // Ticker
        { wch: 28 },  // Company
        { wch: 10 },  // Tipe
        { wch: 22 },  // Sektor
        { wch: 16 },  // Broker
        { wch: 8 },   // Akun
        { wch: 7 },   // Lot
        { wch: 9 },   // Shares
        { wch: 12 },  // Avg Price
        { wch: 15 },  // Total Cost
        { wch: 12 },  // Last Price
        { wch: 15 },  // Market Value
        { wch: 15 },  // Unrealized P&L
        { wch: 8 },   // P&L %
    ];

    // Build per-broker summary sheet
    const brokerRows = [];
    if (portfolioData.by_broker) {
        for (const [broker, group] of Object.entries(portfolioData.by_broker)) {
            brokerRows.push({
                'Broker': broker,
                'Jumlah Saham': group.items.length,
                'Total Cost': group.total_cost,
                'Market Value': group.market_value,
                'Unrealized P&L': group.pnl,
                'P&L %': group.total_cost ? Math.round(group.pnl / group.total_cost * 10000) / 100 : 0,
            });
        }
    }
    const wsBroker = XLSX.utils.json_to_sheet(brokerRows);
    wsBroker['!cols'] = [{ wch: 20 }, { wch: 14 }, { wch: 16 }, { wch: 16 }, { wch: 16 }, { wch: 8 }];

    // Build per-sector summary sheet
    const sectorRows = [];
    if (portfolioData.by_sector) {
        for (const [sector, group] of Object.entries(portfolioData.by_sector)) {
            sectorRows.push({
                'Sektor': sector,
                'Jumlah Saham': group.items.length,
                'Total Cost': group.total_cost,
                'Market Value': group.market_value,
                'Unrealized P&L': group.pnl,
                'P&L %': group.total_cost ? Math.round(group.pnl / group.total_cost * 10000) / 100 : 0,
            });
        }
    }
    const wsSector = XLSX.utils.json_to_sheet(sectorRows);
    wsSector['!cols'] = [{ wch: 26 }, { wch: 14 }, { wch: 16 }, { wch: 16 }, { wch: 16 }, { wch: 8 }];

    // Create workbook with multiple sheets
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Portfolio');
    XLSX.utils.book_append_sheet(wb, wsBroker, 'Per Broker');
    XLSX.utils.book_append_sheet(wb, wsSector, 'Per Sektor');

    // Generate filename with date
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
    XLSX.writeFile(wb, `Portico_Portfolio_${dateStr}.xlsx`);

    showToast('Portfolio berhasil diexport ke Excel!', 'success');
}

// ── MULTISELECT & BULK DELETE ────────────────────────────────────────

function toggleAllPortfolio(master) {
    document.querySelectorAll('.portfolio-checkbox').forEach(cb => { cb.checked = master.checked; });
    updatePortfolioSelection();
}

function updatePortfolioSelection() {
    const checked = document.querySelectorAll('.portfolio-checkbox:checked');
    const count = checked.length;
    const countEl = document.getElementById('portfolio-selected-count');
    const deleteBtn = document.getElementById('portfolio-bulk-delete');
    const brokerBtn = document.getElementById('portfolio-bulk-broker-btn');
    const brokerSelect = document.getElementById('portfolio-bulk-broker');
    const brokerCountEl = document.getElementById('portfolio-broker-count');
    countEl.textContent = count;
    if (brokerCountEl) brokerCountEl.textContent = count;
    if (count > 0) {
        deleteBtn.classList.remove('hidden');
        if (brokerBtn) brokerBtn.classList.remove('hidden');
        if (brokerSelect) brokerSelect.classList.remove('hidden');
    } else {
        deleteBtn.classList.add('hidden');
        if (brokerBtn) brokerBtn.classList.add('hidden');
        if (brokerSelect) brokerSelect.classList.add('hidden');
    }
    const all = document.querySelectorAll('.portfolio-checkbox');
    const selectAll = document.getElementById('portfolio-select-all');
    if (selectAll) selectAll.checked = all.length > 0 && count === all.length;
}

async function bulkUpdateBroker() {
    const checked = document.querySelectorAll('.portfolio-checkbox:checked');
    const ids = Array.from(checked).map(cb => parseInt(cb.dataset.id));
    const tickers = Array.from(checked).map(cb => cb.dataset.ticker);
    const brokerSelect = document.getElementById('portfolio-bulk-broker');
    const broker = brokerSelect ? brokerSelect.value : '';
    if (ids.length === 0) return;
    if (!broker) { showToast('Pilih broker dulu dari dropdown', 'error'); return; }
    if (!confirm(`Pindahkan ${ids.length} saham ke broker "${broker}"?\n${tickers.join(', ')}`)) return;
    try {
        const res = await fetch(`${API}/api/portfolio/bulk-update-broker`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, broker })
        });
        const data = await res.json();
        showToast(data.message, 'success');
        loadPortfolio();
    } catch (err) { showToast('Gagal update broker', 'error'); }
}

async function bulkDeletePortfolio() {
    const checked = document.querySelectorAll('.portfolio-checkbox:checked');
    const ids = Array.from(checked).map(cb => parseInt(cb.dataset.id));
    const tickers = Array.from(checked).map(cb => cb.dataset.ticker);
    if (ids.length === 0) return;
    if (!confirm(`Hapus ${ids.length} item dari portfolio?\n${tickers.join(', ')}`)) return;
    try {
        const res = await fetch(`${API}/api/portfolio/bulk-delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        const data = await res.json();
        showToast(data.message, 'success');
        loadPortfolio();
    } catch (err) { showToast('Gagal menghapus', 'error'); }
}

async function bulkDeleteWatchlist() {
    if (!watchlistGridApi) return;
    const selected = watchlistGridApi.getSelectedRows();
    const tickers = selected.map(r => r.ticker);
    if (tickers.length === 0) return;
    if (!confirm(`Hapus ${tickers.length} item dari watchlist?\n${tickers.join(', ')}`)) return;
    try {
        const res = await fetch(`${API}/api/watchlist/bulk-delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tickers })
        });
        const data = await res.json();
        showToast(data.message, 'success');
        watchlistGridApi = null;
        document.getElementById('watchlist-grid').innerHTML = '';
        loadWatchlist();
    } catch (err) { showToast('Gagal menghapus', 'error'); }
}
