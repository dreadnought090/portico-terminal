// Merriot Thesis Tracker — web UI

let _thesisCurrentTab = 'all';
let _thesisLastPreview = null;

function _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => (
        {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
    ));
}

function _fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

function _statusBadge(status, daysToReview) {
    const map = {
        pending: 'badge-pending',
        reviewed: 'badge-reviewed',
        invalid: 'badge-invalid',
    };
    const colors = {
        pending: '#f59e0b',
        reviewed: '#22c55e',
        invalid: '#ef4444',
    };
    const labels = {pending: 'Pending', reviewed: 'Reviewed', invalid: 'Invalid'};
    const color = colors[status] || '#6b7280';
    let extra = '';
    if (status === 'pending' && daysToReview !== null && daysToReview <= 7) {
        const text = daysToReview <= 0 ? 'OVERDUE' : daysToReview === 1 ? 'BESOK' : `${daysToReview}d`;
        extra = `<span style="margin-left:6px;color:#ef4444;font-weight:600;">${text}</span>`;
    }
    return `<span style="color:${color};font-weight:600;">${labels[status] || status}</span>${extra}`;
}

function _directionIcon(d) {
    return {bullish:'🟢', bearish:'🔴', neutral:'⚪', exit:'🚪'}[d] || '';
}

// Hook into existing showPanel by calling loadThesis when panel opens.
// app.js's showPanel switch doesn't include 'thesis', so we monkey-patch.
(function attachThesisPanelHook() {
    if (typeof window === 'undefined') return;
    const orig = window.showPanel;
    if (typeof orig !== 'function') {
        // app.js not loaded yet, retry after DOMContentLoaded
        document.addEventListener('DOMContentLoaded', attachThesisPanelHook);
        return;
    }
    window.showPanel = function(panelId) {
        orig(panelId);
        if (panelId === 'thesis') loadThesis();
    };
})();

async function loadThesis() {
    const tab = _thesisCurrentTab;
    const ticker = (document.getElementById('thesis-filter-ticker')?.value || '').trim().toUpperCase();
    let url = '/api/thesis?limit=200';
    if (ticker) url += `&ticker=${encodeURIComponent(ticker)}`;
    if (tab === 'reviewed') url += '&status=reviewed';
    else if (tab === 'invalid') url += '&status=invalid';
    else if (tab === 'due') url = `/api/thesis/due?days=7`;
    // 'all' (Semua) — no status filter, show everything

    const target = document.getElementById('thesis-list-container');
    target.innerHTML = '<p class="placeholder-text">Memuat...</p>';
    try {
        const r = await fetch(url);
        const d = await r.json();
        const notes = d.notes || [];
        document.getElementById('thesis-stats').textContent = `${notes.length} notes`;
        if (!notes.length) {
            target.innerHTML = '<p class="placeholder-text">Belum ada note. Klik "Note Baru" buat mulai.</p>';
            return;
        }
        // Group by ticker
        const byTicker = {};
        for (const n of notes) {
            (byTicker[n.ticker] = byTicker[n.ticker] || []).push(n);
        }
        const tickers = Object.keys(byTicker).sort();
        const today = new Date(); today.setHours(0,0,0,0);
        const html = tickers.map(t => {
            const items = byTicker[t];
            const rows = items.map(n => {
                // Parse YYYY-MM-DD as LOCAL midnight (not UTC) so day diff is correct in WIB.
                let reviewDate = null;
                if (n.review_at) {
                    const parts = n.review_at.split('-').map(Number);
                    if (parts.length === 3) reviewDate = new Date(parts[0], parts[1]-1, parts[2]);
                }
                const days = reviewDate ? Math.round((reviewDate - today) / 86400000) : null;
                const kp = (n.key_points && n.key_points.length) ? n.key_points[0] : (n.body || '').slice(0,80);
                const tags = (n.tags || []).map(tg => `<span style="color:#60a5fa;font-size:10px;">#${_esc(tg)}</span>`).join(' ');
                return `
                <tr data-note-id="${n.id}">
                    <td>#${n.id}</td>
                    <td>${_directionIcon(n.thesis_direction)} ${_esc(kp)}</td>
                    <td>${tags}</td>
                    <td>${_fmtDate(n.created_at)}</td>
                    <td>${_fmtDate(n.review_at)} ${_statusBadge(n.status, days)}</td>
                    <td>
                        <button class="btn btn-sm" onclick="thesisDetail(${n.id})" title="Detail"><i class="fas fa-eye"></i></button>
                        ${n.status === 'pending' ? `<button class="btn btn-sm" onclick="thesisMarkReviewed(${n.id})" title="Mark Reviewed"><i class="fas fa-check"></i></button>` : ''}
                        ${n.status === 'pending' ? `<button class="btn btn-sm" onclick="thesisPostpone(${n.id})" title="Postpone 7d"><i class="fas fa-clock"></i></button>` : ''}
                        <button class="btn btn-sm btn-danger" onclick="thesisDelete(${n.id})" title="Hapus"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>`;
            }).join('');
            return `
            <div style="margin-bottom:18px;">
                <h3 style="margin:0 0 6px 0;color:var(--accent);">${_esc(t)} <span style="color:var(--text-secondary);font-size:11px;">(${items.length} notes)</span></h3>
                <table class="data-table">
                    <thead><tr><th>ID</th><th>Key point</th><th>Tags</th><th>Created</th><th>Review</th><th>Action</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
        }).join('');
        target.innerHTML = html;
    } catch (e) {
        target.innerHTML = `<p class="placeholder-text">Error: ${_esc(e.message)}</p>`;
    }
}

function showThesisTab(tab) {
    _thesisCurrentTab = tab;
    document.querySelectorAll('.thesis-tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.thesisTab === tab));
    loadThesis();
}

function openThesisCreate() {
    document.getElementById('thesis-input').value = '';
    document.getElementById('thesis-preview').innerHTML = '';
    _thesisLastPreview = null;
    document.getElementById('panel-thesis-create').classList.remove('hidden');
}

function closeThesisCreate() {
    document.getElementById('panel-thesis-create').classList.add('hidden');
}

async function extractThesisPreview() {
    const body = document.getElementById('thesis-input').value.trim();
    if (!body) return;
    const target = document.getElementById('thesis-preview');
    target.innerHTML = '<p class="placeholder-text">Extracting via Claude Haiku...</p>';
    try {
        const r = await fetch('/api/thesis/extract', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({body, auto_extract: true}),
        });
        const d = await r.json();
        if (d.error) {
            target.innerHTML = `<p class="placeholder-text">⚠ ${_esc(d.error)}: ${_esc(d.suggestion || '')}</p>`;
            return;
        }
        _thesisLastPreview = {body, ...d};
        const ticker = Array.isArray(d.ticker) ? d.ticker.join(', ') : d.ticker;
        const kpHtml = (d.key_points || []).map(kp => `<li>${_esc(kp)}</li>`).join('');
        const tagsHtml = (d.tags || []).map(t => `<span style="color:#60a5fa;">#${_esc(t)}</span>`).join(' ');
        const warnHtml = (d.warnings || []).map(w => `<span style="color:#f59e0b;">⚠ ${_esc(w)}</span>`).join(' ');
        target.innerHTML = `
            <div style="background:var(--bg-secondary);padding:12px;border-radius:8px;border:1px solid var(--border);">
                <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                    <strong>${_esc(ticker)} · ${_directionIcon(d.thesis_direction)} ${_esc(d.thesis_type)}</strong>
                    <span style="color:var(--text-secondary);font-size:11px;">Confidence: ${(d.confidence*100).toFixed(0)}%</span>
                </div>
                <ul style="margin:0 0 8px 16px;">${kpHtml}</ul>
                <div style="margin-bottom:8px;">${tagsHtml}</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                    Review: <strong>${_fmtDate(d.suggested_review_date)}</strong> — ${_esc(d.review_reasoning)}
                </div>
                ${warnHtml ? `<div style="margin-top:6px;font-size:11px;">${warnHtml}</div>` : ''}
                <div style="display:flex;gap:8px;margin-top:12px;">
                    <button class="btn btn-primary" onclick="confirmSaveThesis()"><i class="fas fa-check"></i> Save</button>
                    <button class="btn" onclick="document.getElementById('thesis-preview').innerHTML='';_thesisLastPreview=null;">Re-extract</button>
                </div>
            </div>`;
    } catch (e) {
        target.innerHTML = `<p class="placeholder-text">Error: ${_esc(e.message)}</p>`;
    }
}

async function confirmSaveThesis() {
    if (!_thesisLastPreview) return;
    // Send pre-extracted payload so backend skips a redundant LLM call (~$0.002 saved per save).
    const p = _thesisLastPreview;
    const extracted = {
        ticker: p.ticker,
        thesis_type: p.thesis_type,
        thesis_direction: p.thesis_direction,
        key_points: p.key_points,
        tags: p.tags,
        suggested_review_date: p.suggested_review_date,
        review_reasoning: p.review_reasoning,
        confidence: p.confidence,
    };
    try {
        const r = await fetch('/api/thesis', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({body: p.body, auto_extract: false, extracted}),
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            alert('Save gagal: ' + (err.detail || r.status));
            return;
        }
        closeThesisCreate();
        loadThesis();
    } catch (e) {
        alert('Save error: ' + e.message);
    }
}

async function thesisDetail(id) {
    try {
        const r = await fetch(`/api/thesis/${id}`);
        const n = await r.json();
        const kp = (n.key_points || []).map(k => `• ${k}`).join('\n');
        const tags = (n.tags || []).join(', ');
        alert(
            `#${n.id} ${n.ticker} (${n.status})\n\n` +
            `Created: ${_fmtDate(n.created_at)}\n` +
            `Review: ${_fmtDate(n.review_at)}\n` +
            `Type: ${n.thesis_type} · ${n.thesis_direction}\n` +
            `Tags: ${tags}\n\n` +
            `Body:\n${n.body}\n\n` +
            `Key points:\n${kp}\n\n` +
            (n.review_reasoning ? `Reasoning: ${n.review_reasoning}\n\n` : '') +
            (n.follow_up ? `Follow-up: ${n.follow_up}` : '')
        );
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function thesisMarkReviewed(id) {
    const followUp = prompt('Follow-up note (opsional, kosongkan kalau skip):', '');
    if (followUp === null) return;  // user clicked Cancel
    try {
        const r = await fetch(`/api/thesis/${id}/reviewed?follow_up=${encodeURIComponent(followUp)}`, {method: 'POST'});
        if (r.ok) loadThesis();
    } catch (e) { alert('Error: ' + e.message); }
}

async function thesisPostpone(id) {
    try {
        const r = await fetch(`/api/thesis/${id}/postpone?days=7`, {method: 'POST'});
        if (r.ok) loadThesis();
    } catch (e) { alert('Error: ' + e.message); }
}

async function thesisDelete(id) {
    if (!confirm(`Hapus note #${id}?`)) return;
    try {
        const r = await fetch(`/api/thesis/${id}`, {method: 'DELETE'});
        if (r.ok) loadThesis();
    } catch (e) { alert('Error: ' + e.message); }
}
