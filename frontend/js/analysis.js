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

        draftMemo: (ticker) =>
            fetch(`/api/analysis/research/${ticker}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
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

    async function draftFromScratch() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase();
        if (!ticker) {
            setStatus("Ticker kosong — isi ticker dulu sebelum draft", "error");
            return;
        }

        const currentThesis = $("#analysis-thesis").value.trim();
        if (currentThesis.length > 50) {
            const confirmOverwrite = confirm(
                "Thesis existing akan di-overwrite dengan draft baru. Lanjutkan?\n\n" +
                "Tip: save dulu ke tab Memo sebelum draft (klik '→ Memo')."
            );
            if (!confirmOverwrite) return;
        }

        state.currentTicker = ticker;
        state.isRunning = true;
        $("#analysis-draft-btn").disabled = true;
        $("#analysis-run-btn").disabled = true;
        setStatus("Drafting thesis dari data Portico... (15-30 detik)", "running");

        try {
            const result = await API.draftMemo(ticker);

            if (result.error) {
                setStatus("Draft error: " + result.error, "error");
            } else {
                $("#analysis-thesis").value = result.memo_md || "";
                const ctx = result.context_summary || {};
                setStatus(
                    `Draft ready (${(result.duration_ms / 1000).toFixed(1)}s, $${result.cost_usd.toFixed(4)}) • ${ctx.peers_count || 0} peers, ${ctx.news_count || 0} news • Edit sesuai view lo, lalu Run Council`,
                    ""
                );
                updateEstimate();
            }
        } catch (e) {
            setStatus("Network error: " + e.message, "error");
        } finally {
            state.isRunning = false;
            $("#analysis-draft-btn").disabled = false;
            $("#analysis-run-btn").disabled = false;
        }
    }

    // ── Deep Research tab ────────────────────────────────────────
    // Pricing per 1M tokens (input / output USD)
    const DR_PRICING = {
        sonnet46: { input: 3.0, output: 15.0, label: "Sonnet 4.6" },
        opus47:   { input: 15.0, output: 75.0, label: "Opus 4.7" },
        haiku45:  { input: 0.80, output: 4.0, label: "Haiku 4.5" },
    };
    let drCurrentModel = "sonnet46";

    function drCharsToTokens(chars) {
        // Rough heuristic: English/Indo mix ~4 chars per token
        return Math.ceil((chars || 0) / 4);
    }

    function drUpdateCostEstimate() {
        const thesisTok = drCharsToTokens($("#dr-thesis").value.length);
        const claudeTok = drCharsToTokens($("#dr-paste-claude").value.length);
        const geminiTok = drCharsToTokens($("#dr-paste-gemini").value.length);
        const gptTok    = drCharsToTokens($("#dr-paste-gpt").value.length);

        $("#dr-tok-claude").textContent = claudeTok.toLocaleString() + " tok";
        $("#dr-tok-gemini").textContent = geminiTok.toLocaleString() + " tok";
        $("#dr-tok-gpt").textContent    = gptTok.toLocaleString() + " tok";

        const totalInput = thesisTok + claudeTok + geminiTok + gptTok;
        $("#dr-total-tokens").textContent = totalInput.toLocaleString() + " tok";

        const p = DR_PRICING[drCurrentModel];
        const M = 1_000_000;

        // Briefing pass: input = all pastes + thesis; output ~3k tokens summary
        const briefingOut = 3000;
        const briefingCost = (totalInput * p.input + briefingOut * p.output) / M;

        // Council v2: 5 agents + synthesizer
        // Each agent input ~ briefing (3k) + thesis + priming (~1k) = ~5k in, ~2k out
        const agentIn = 5000, agentOut = 2000;
        const agentCost = 5 * (agentIn * p.input + agentOut * p.output) / M;
        // Synthesizer: 5 × agent outputs (10k) + prompt (2k) in, 3k out
        const synthIn = 12000, synthOut = 3000;
        const synthCost = (synthIn * p.input + synthOut * p.output) / M;
        const councilCost = agentCost + synthCost;

        const total = briefingCost + councilCost;

        $("#dr-cost-briefing").textContent = "$" + briefingCost.toFixed(4);
        $("#dr-cost-council").textContent  = "$" + councilCost.toFixed(4);
        $("#dr-cost-total").textContent    = "$" + total.toFixed(4);
    }

    function drCopyMasterPrompt() {
        const el = document.getElementById("dr-master-prompt");
        if (!el) return;
        const ticker = ($("#analysis-ticker").value.trim().toUpperCase()) || "<TICKER>";
        const today = new Date().toISOString().slice(0, 10);
        const text = el.textContent
            .replace(/<TICKER>/g, ticker)
            .replace(/<YYYY-MM-DD>/g, today)
            .trim();
        navigator.clipboard.writeText(text).then(() => {
            const s = $("#dr-copy-status");
            s.textContent = "✓ Copied • paste ke Claude/Gemini/ChatGPT Deep Research";
            setTimeout(() => { s.textContent = ""; }, 4000);
        }).catch((e) => {
            $("#dr-copy-status").textContent = "Copy failed: " + e.message;
        });
    }

    function drSwitchPasteTab(tabName) {
        $$(".dr-paste-tab").forEach((t) => t.classList.toggle("active", t.dataset.pasteTab === tabName));
        $$(".dr-paste-area").forEach((a) => { a.style.display = a.dataset.pasteContent === tabName ? "block" : "none"; });
    }

    function drSetStatus(text, type = "") {
        const el = $("#dr-status");
        el.textContent = text;
        el.className = "analysis-status " + type;
    }

    function drCollectPayload() {
        return {
            thesis: $("#dr-thesis").value.trim(),
            model: drCurrentModel,
            sources: {
                claude: $("#dr-paste-claude").value,
                gemini: $("#dr-paste-gemini").value,
                gpt:    $("#dr-paste-gpt").value,
            },
        };
    }

    function drValidate() {
        const ticker = $("#analysis-ticker").value.trim().toUpperCase();
        if (!ticker) { drSetStatus("Ticker kosong (isi di atas)", "error"); return null; }
        const payload = drCollectPayload();
        const anyPaste = payload.sources.claude || payload.sources.gemini || payload.sources.gpt;
        if (!anyPaste) { drSetStatus("Minimal 1 deep research output harus dipaste", "error"); return null; }
        if (!payload.thesis) { drSetStatus("Thesis kosong — tulis 1-3 kalimat konviksi lu", "error"); return null; }
        return { ticker, payload };
    }

    async function drBuildBriefing() {
        const v = drValidate();
        if (!v) return;
        drSetStatus("Building briefing... (10-30s)", "running");
        $("#dr-briefing-btn").disabled = true;
        try {
            const r = await fetch(`/api/analysis/briefing/${v.ticker}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(v.payload),
            });
            if (r.status === 404 || r.status === 501) {
                drSetStatus("Backend endpoint /api/analysis/briefing belum diimplementasi (next step)", "error");
                return;
            }
            const data = await r.json();
            if (data.error) { drSetStatus("Error: " + data.error, "error"); return; }
            drSetStatus(`Briefing ready • $${(data.cost_usd || 0).toFixed(4)}`, "");
            $("#dr-results").innerHTML = "";
            $("#dr-results").appendChild(drBlock("briefing", "Council Briefing Doc", data.briefing_md || "", false));
        } catch (e) {
            drSetStatus("Network error: " + e.message, "error");
        } finally {
            $("#dr-briefing-btn").disabled = false;
        }
    }

    async function drRunFullAnalysis() {
        const v = drValidate();
        if (!v) return;
        drSetStatus("Running full analysis: briefing → council v2 → memo... (60-180s)", "running");
        $("#dr-full-run-btn").disabled = true;
        $("#dr-briefing-btn").disabled = true;
        $("#dr-results").innerHTML = "";
        try {
            const r = await fetch(`/api/analysis/deep-council/${v.ticker}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(v.payload),
            });
            if (r.status === 404 || r.status === 501) {
                drSetStatus("Backend endpoint /api/analysis/deep-council belum diimplementasi (next step)", "error");
                return;
            }
            const data = await r.json();
            if (data.error) { drSetStatus("Error: " + data.error, "error"); return; }
            drSetStatus(`Done • $${(data.total_cost_usd || 0).toFixed(4)} • ${((data.total_duration_ms || 0)/1000).toFixed(1)}s`, "");
            drRenderFullResult(data);
        } catch (e) {
            drSetStatus("Network error: " + e.message, "error");
        } finally {
            $("#dr-full-run-btn").disabled = false;
            $("#dr-briefing-btn").disabled = false;
        }
    }

    function drRenderFullResult(data) {
        const c = $("#dr-results");
        c.innerHTML = "";
        if (data.briefing_md) c.appendChild(drBlock("briefing", "Council Briefing Doc", data.briefing_md, true));
        if (data.panel) {
            const order = ["bull", "bear", "macro", "devil", "variant"];
            const labels = { bull: "Bull", bear: "Bear", macro: "Macro", devil: "Devil's Advocate", variant: "Variant Perception" };
            order.forEach((k) => {
                if (data.panel[k]) c.appendChild(drBlock(k, labels[k], data.panel[k].output || "", false));
            });
        }
        if (data.memo_md) c.appendChild(drBlock("synthesis", "Citrini-style Memo", data.memo_md, false));
    }

    function drBlock(roleKey, label, md, collapsed) {
        const block = document.createElement("div");
        block.className = "analysis-result-block";
        block.innerHTML = `
            <div class="analysis-result-header" style="cursor:pointer;user-select:none;">
                <span class="analysis-result-role ${roleKey}">${label}</span>
                <span class="analysis-result-meta">${collapsed ? "[+] click to expand" : "[−] click to collapse"}</span>
            </div>
            <div class="analysis-result-body" style="${collapsed ? "display:none;" : ""}">${renderMarkdown(md)}</div>
        `;
        const header = block.querySelector(".analysis-result-header");
        const body = block.querySelector(".analysis-result-body");
        const meta = block.querySelector(".analysis-result-meta");
        header.addEventListener("click", () => {
            const nowHidden = body.style.display === "none";
            body.style.display = nowHidden ? "block" : "none";
            meta.textContent = nowHidden ? "[−] click to collapse" : "[+] click to expand";
        });
        return block;
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

        // Draft from scratch
        $("#analysis-draft-btn").addEventListener("click", draftFromScratch);

        // Keyboard: Ctrl+Enter or Cmd+Enter to run council
        $("#analysis-thesis").addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                runCouncil();
            }
        });

        // Deep Research bindings
        $("#dr-copy-prompt-btn").addEventListener("click", drCopyMasterPrompt);
        $$(".dr-paste-tab").forEach((t) => {
            t.addEventListener("click", () => drSwitchPasteTab(t.dataset.pasteTab));
        });

        let drEstTimer;
        const drDebounced = () => { clearTimeout(drEstTimer); drEstTimer = setTimeout(drUpdateCostEstimate, 250); };
        ["dr-thesis", "dr-paste-claude", "dr-paste-gemini", "dr-paste-gpt"].forEach((id) => {
            const el = $("#" + id);
            if (el) el.addEventListener("input", drDebounced);
        });

        const modelSel = $("#dr-model-select");
        if (modelSel) {
            modelSel.addEventListener("change", (e) => {
                drCurrentModel = e.target.value;
                drUpdateCostEstimate();
            });
        }

        $("#dr-briefing-btn").addEventListener("click", drBuildBriefing);
        $("#dr-full-run-btn").addEventListener("click", drRunFullAnalysis);
        drUpdateCostEstimate();

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
