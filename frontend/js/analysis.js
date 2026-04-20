/**
 * Analysis Mode — Council UI + API interactions
 *
 * Namespace: window.Analysis (avoid collision with existing app.js)
 */
(function () {
    "use strict";

    const API = {
        estimate: (ticker, thesis) =>
            fetch(`/api/analysis/council/${ticker}/estimate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ thesis }),
            }).then((r) => r.json()),

        runCouncil: (ticker, thesis, rolesEnabled) =>
            fetch(`/api/analysis/council/${ticker}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ thesis, roles_enabled: rolesEnabled || null }),
            }).then((r) => r.json()),

        history: (ticker) =>
            fetch(`/api/analysis/history/${ticker}`).then((r) => r.json()),

        runDetail: (runId) =>
            fetch(`/api/analysis/run/${runId}`).then((r) => r.json()),

        deleteRun: (runId) =>
            fetch(`/api/analysis/run/${runId}`, { method: "DELETE" }).then((r) => r.json()),

        getMemo: (ticker) =>
            fetch(`/api/analysis/memo/${ticker}`).then((r) => r.json()),

        saveMemo: (ticker, contentMd, confidenceScore, tags) =>
            fetch(`/api/analysis/memo/${ticker}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    content_md: contentMd,
                    confidence_score: confidenceScore,
                    tags: tags || [],
                }),
            }).then((r) => r.json()),
    };

    const state = {
        currentTicker: "",
        activeTab: "council",
        isRunning: false,
        lastResult: null,
        lastEstimate: null,
    };

    // ── DOM helpers ──────────────────────────────────────────────
    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

    function escapeHtml(s) {
        const div = document.createElement("div");
        div.textContent = s || "";
        return div.innerHTML;
    }

    // Basic markdown-ish rendering (no external lib needed). Converts:
    // ## heading, ### subheading, **bold**, bullet lists, line breaks.
    function renderMarkdown(text) {
        if (!text) return "";
        let html = escapeHtml(text);
        html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
        html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        // Simple bullet list: lines starting with "- "
        html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
        html = html.replace(/(<li>.+<\/li>\n?)+/g, (m) => "<ul>" + m + "</ul>");
        // Numbered list: lines starting with "1. "
        html = html.replace(/^(\d+)\. (.+)$/gm, "<li>$2</li>");
        return html;
    }

    // ── UI update functions ─────────────────────────────────────
    function openPanel() {
        $(".analysis-panel").classList.add("open");
        $(".analysis-toggle-btn").classList.add("active");
        // Pre-fill ticker if there's a selected one globally (existing app may expose)
        if (!state.currentTicker && window.currentStockTicker) {
            state.currentTicker = window.currentStockTicker;
            $("#analysis-ticker").value = state.currentTicker;
        }
    }

    function closePanel() {
        $(".analysis-panel").classList.remove("open");
        $(".analysis-toggle-btn").classList.remove("active");
    }

    function setActiveTab(tabName) {
        state.activeTab = tabName;
        $$(".analysis-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
        $$(".analysis-tab-content").forEach((c) => (c.style.display = c.dataset.tab === tabName ? "block" : "none"));
        if (tabName === "history" && state.currentTicker) loadHistory();
        if (tabName === "memo" && state.currentTicker) loadMemo();
    }

    function setStatus(text, type = "") {
        const el = $("#analysis-status");
        el.textContent = text;
        el.className = "analysis-status " + type;
    }

    async function updateEstimate() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase();
        const thesis = $("#analysis-thesis").value;
        if (!ticker || !thesis.trim()) {
            $("#analysis-estimate").innerHTML = "";
            return;
        }
        try {
            const est = await API.estimate(ticker, thesis);
            state.lastEstimate = est;
            $("#analysis-estimate").innerHTML =
                `Est. cost: <strong>$${est.total_cost_usd.toFixed(4)}</strong> (panel $${est.panel_cost_usd.toFixed(4)} + synth $${est.synthesizer_cost_usd.toFixed(4)})`;
        } catch (e) {
            $("#analysis-estimate").innerHTML = "";
        }
    }

    async function runCouncil() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase();
        const thesis = $("#analysis-thesis").value.trim();

        if (!ticker) {
            setStatus("Ticker kosong", "error");
            return;
        }
        if (!thesis) {
            setStatus("Thesis kosong", "error");
            return;
        }

        state.isRunning = true;
        state.currentTicker = ticker;
        $("#analysis-run-btn").disabled = true;
        $("#analysis-results").innerHTML = "";
        setStatus("Running council... (butuh 20-60 detik)", "running");

        try {
            const result = await API.runCouncil(ticker, thesis);
            state.lastResult = result;

            if (result.error) {
                setStatus("Error: " + result.error, "error");
            } else {
                setStatus(
                    `Done in ${(result.total_duration_ms / 1000).toFixed(1)}s • Cost $${result.total_cost_usd.toFixed(4)}`,
                    ""
                );
            }
            renderResult(result);
        } catch (e) {
            setStatus("Network error: " + e.message, "error");
        } finally {
            state.isRunning = false;
            $("#analysis-run-btn").disabled = false;
        }
    }

    function renderResult(result) {
        const container = $("#analysis-results");
        container.innerHTML = "";

        if (!result || !result.panel) return;

        // Synthesis first (most important)
        if (result.synthesis && result.synthesis.output) {
            container.appendChild(
                buildResultBlock("synthesis", "CIO Synthesis", result.synthesis)
            );
        }

        // Panel results
        const order = ["bull", "bear", "macro", "devil"];
        order.forEach((roleKey) => {
            const roleData = result.panel[roleKey];
            if (roleData) {
                const label = { bull: "Bull", bear: "Bear", macro: "Macro", devil: "Devil's Advocate" }[roleKey] || roleKey;
                container.appendChild(buildResultBlock(roleKey, label, roleData));
            }
        });
    }

    function buildResultBlock(roleKey, label, data) {
        const block = document.createElement("div");
        block.className = "analysis-result-block";

        const output = data.output || "";
        const model = data.model || "";
        const cost = data.cost_usd || 0;
        const duration = data.duration_ms || 0;
        const tokens = (data.input_tokens || 0) + (data.output_tokens || 0);
        const errorMsg = data.error;

        block.innerHTML = `
            <div class="analysis-result-header">
                <span class="analysis-result-role ${roleKey}">${label}</span>
                <span class="analysis-result-meta">
                    ${model} • ${(duration / 1000).toFixed(1)}s • $${cost.toFixed(4)} • ${tokens} tok
                </span>
            </div>
            <div class="analysis-result-body">
                ${errorMsg ? `<em style="color:#ff6b6b">Error: ${escapeHtml(errorMsg)}</em>` : renderMarkdown(output)}
            </div>
        `;
        return block;
    }

    async function loadHistory() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase() || state.currentTicker;
        if (!ticker) {
            $("#analysis-history-list").innerHTML = '<div class="analysis-status">Pilih ticker dulu</div>';
            return;
        }
        $("#analysis-history-list").innerHTML = '<div class="analysis-status">Loading...</div>';
        try {
            const data = await API.history(ticker);
            const runs = data.runs || [];
            if (runs.length === 0) {
                $("#analysis-history-list").innerHTML = '<div class="analysis-status">Belum ada run untuk ' + ticker + '</div>';
                return;
            }
            $("#analysis-history-list").innerHTML = runs
                .map(
                    (r) => `
                <div class="analysis-history-item" data-run-id="${r.id}">
                    <div class="analysis-history-head">
                        <span>#${r.id} • ${r.run_type} • ${r.status}</span>
                        <span>${new Date(r.created_at).toLocaleString("id-ID")} • $${r.cost_usd.toFixed(4)}</span>
                    </div>
                    <div class="analysis-history-preview">${escapeHtml(r.synthesis_preview || "(no synthesis)")}</div>
                </div>
            `
                )
                .join("");
            $$(".analysis-history-item").forEach((el) => {
                el.addEventListener("click", () => loadRun(el.dataset.runId));
            });
        } catch (e) {
            $("#analysis-history-list").innerHTML = '<div class="analysis-status error">Error: ' + e.message + "</div>";
        }
    }

    async function loadRun(runId) {
        try {
            const detail = await API.runDetail(runId);
            setActiveTab("council");
            $("#analysis-ticker").value = detail.ticker;
            $("#analysis-thesis").value = detail.input_thesis || "";
            state.currentTicker = detail.ticker;
            state.lastResult = detail.output;
            renderResult(detail.output);
            setStatus(`Loaded run #${runId} from ${new Date(detail.created_at).toLocaleString("id-ID")}`);
        } catch (e) {
            setStatus("Failed to load run: " + e.message, "error");
        }
    }

    async function loadMemo() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase() || state.currentTicker;
        if (!ticker) {
            $("#analysis-memo-content").value = "";
            $("#analysis-memo-info").textContent = "Pilih ticker dulu";
            return;
        }
        try {
            const data = await API.getMemo(ticker);
            if (data.memo) {
                $("#analysis-memo-content").value = data.memo.content_md || "";
                $("#analysis-memo-info").textContent = `v${data.memo.version} • updated ${new Date(data.memo.updated_at).toLocaleString("id-ID")}`;
            } else {
                $("#analysis-memo-content").value = "";
                $("#analysis-memo-info").textContent = "Belum ada memo untuk " + ticker;
            }
        } catch (e) {
            $("#analysis-memo-info").textContent = "Error: " + e.message;
        }
    }

    async function saveMemo() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase() || state.currentTicker;
        const content = $("#analysis-memo-content").value;
        if (!ticker) {
            $("#analysis-memo-info").textContent = "Pilih ticker dulu";
            return;
        }
        try {
            const result = await API.saveMemo(ticker, content, 0, []);
            $("#analysis-memo-info").textContent = `Saved v${result.version}`;
        } catch (e) {
            $("#analysis-memo-info").textContent = "Save failed: " + e.message;
        }
    }

    function copyThesisToMemo() {
        const thesis = $("#analysis-thesis").value;
        $("#analysis-memo-content").value = thesis;
        setActiveTab("memo");
    }

    // ── Init ─────────────────────────────────────────────────────
    function init() {
        // Toggle button
        $(".analysis-toggle-btn").addEventListener("click", () => {
            const isOpen = $(".analysis-panel").classList.contains("open");
            if (isOpen) closePanel();
            else openPanel();
        });

        $(".analysis-panel-close").addEventListener("click", closePanel);

        // Tabs
        $$(".analysis-tab").forEach((t) => {
            t.addEventListener("click", () => {
                if (!t.classList.contains("disabled")) setActiveTab(t.dataset.tab);
            });
        });

        // Ticker input sync
        $("#analysis-ticker").addEventListener("input", (e) => {
            state.currentTicker = e.target.value.trim().toUpperCase();
            e.target.value = state.currentTicker;
            updateEstimate();
        });

        // Thesis input → debounced estimate
        let estimateTimer;
        $("#analysis-thesis").addEventListener("input", () => {
            clearTimeout(estimateTimer);
            estimateTimer = setTimeout(updateEstimate, 500);
        });

        // Run button
        $("#analysis-run-btn").addEventListener("click", runCouncil);
        $("#analysis-estimate-btn").addEventListener("click", updateEstimate);

        // Memo save
        $("#analysis-memo-save-btn").addEventListener("click", saveMemo);
        $("#analysis-thesis-to-memo-btn").addEventListener("click", copyThesisToMemo);

        // Keyboard: Ctrl+Enter or Cmd+Enter to run council
        $("#analysis-thesis").addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                runCouncil();
            }
        });

        // Global keyboard: Ctrl+Shift+A or Cmd+Shift+A to toggle panel
        document.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "A") {
                e.preventDefault();
                const isOpen = $(".analysis-panel").classList.contains("open");
                if (isOpen) closePanel();
                else openPanel();
            }
            if (e.key === "Escape" && $(".analysis-panel").classList.contains("open")) {
                closePanel();
            }
        });
    }

    // Expose for debugging
    window.Analysis = { state, API, openPanel, closePanel, setActiveTab };

    // Init when DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
