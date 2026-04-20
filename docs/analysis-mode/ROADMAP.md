# Analysis Mode — Roadmap

## Vision

Transform Portico dari **portfolio tracker** jadi **thesis-to-decision cockpit**. AI layers as background workers, user focus di judgment.

## Stages

### ✅ Stage 1 — Council (MVP, this branch)

**Status:** Implementing

**What:** 4-agent parallel stress-test untuk thesis. Bull/Bear/Macro/Devil perspectives + synthesizer.

**Files:**
- `backend/analysis/council.py`
- `backend/analysis/prompts.py`
- New models: `AnalysisRun`, `ThesisMemo`
- Routes: `/api/analysis/council/{ticker}`, `/api/analysis/history/{ticker}`, `/api/analysis/run/{run_id}`
- UI: slide-in panel + thesis editor + streaming results

**Success criteria:**
- User input thesis text → 1 click run → 4 parallel LLM responses → 1 synthesized output dalam <60 detik
- Run history per ticker accessible
- Cost tracked per run

---

### ⏳ Stage 2 — Research Pipeline (next branch)

**What:** Auto-draft thesis memo dari stock data + news + filings. User edit, tidak dari zero.

**Flow:**
```
User: "draft memo for $BBCA"
  → Pull 10-K/annual report (IDX)
  → Fetch peer multiples (top 5 banks)
  → Fetch recent news + sentiment
  → Pull management history + board
  → LLM compose memo (sections: thesis, bull case, bear case, catalysts, valuation, risks)
  → Output: draft_memo.md (user edit)
```

**Files to create (blueprint):**
- `backend/analysis/research.py` — orchestrate fetch + compose
- `backend/analysis/sources/`
  - `idx_fetcher.py` — IDX annual reports, financials
  - `news_aggregator.py` — Google News + RSS dengan relevance filtering
  - `peer_selector.py` — comparables auto-selection by sub-sector
- `backend/analysis/prompts.py` — add `MEMO_DRAFT_*` prompts
- Route: `POST /api/analysis/research/{ticker}`

**External APIs needed:**
- Alpha Vantage / Financial Modeling Prep (backup to yfinance)
- (Optional) Sectors.app API — lebih lengkap untuk IDX
- News API (lebih clean daripada Google News RSS)

---

### ⏳ Stage 3 — Sentiment Simulation (next branch)

**What:** Miroshark-style multi-persona simulation buat event-driven alpha.

**Use cases:**
- Pre-earnings: simulate reaction scenarios (beat/meet/miss)
- Pre-corporate action: simulate backlash/support
- Policy impact: simulate market reaction ke regulasi baru

**Files to create (blueprint):**
- `backend/analysis/sentiment.py` — simulation orchestrator
- `backend/analysis/personas.py` — persona templates (retail bullish, retail bearish, analyst, institutional, foreign, crypto-overlap)
- `backend/analysis/graph_store.py` — Neo4j connection untuk entity graph
- Route: `POST /api/analysis/sentiment/{ticker}`

**External tooling needed:**
- Neo4j (local atau Neo4j Aura free tier)
- (Optional) Twitter API / Reddit API untuk seed persona context

**Implementation note:** Start simple — skip Neo4j dulu, pakai SQLite graph-like storage. Upgrade ke Neo4j hanya kalau scale >100 persona.

---

### ⏳ Stage 4 — Morning Brief (nice-to-have)

**What:** Auto-generate daily brief jam 7 pagi. Include:
- Overnight news scan (per portfolio holding + watchlist)
- Macro headline relevant
- Earnings calendar today
- Sentiment anomaly alert (dari Stage 3)
- Yesterday's council runs follow-up

**Implementation:** New scheduler job + templated report → save ke `data/briefs/YYYY-MM-DD.md` + notify via email/Telegram.

---

### ⏳ Stage 5 — Decision Journal (nice-to-have)

**What:** Setiap decision (buy/sell/hold) prompt user untuk explicit rationale. Save ke audit log untuk PA attribution.

**Schema:**
```python
class Decision(Base):
    id, ticker, decision_type (BUY/SELL/HOLD/TRIM)
    date, amount, price
    rationale (Text), expected_catalysts (JSON)
    linked_council_run, linked_memo
    review_date, outcome (filled later)
```

**Review flow:** quarterly PA — which decisions worked, why, attribute ke council/memo quality.

---

## Cost Budget (target)

| Stage | Monthly ceiling |
|-------|-----------------|
| Council (daily use) | $30-60 |
| Research (per initiation) | $1-3 per memo, ~$20-40/month |
| Sentiment (per event) | $5-10 per sim, ~$20-50/month |
| **Total all stages** | **$70-150/month** |

---

## Design Principles (non-negotiable)

1. **Additive, non-breaking** — every feature opt-in via toggle
2. **User ownership** — thesis/memo/decision = local SQLite, ga leak by default
3. **Cost visible** — every button shows estimated cost sebelum run
4. **Auditable** — every AI output saved with model, prompt version, cost
5. **Progressive enhancement** — works via Anthropic API cloud, optionally Ollama local
6. **Opinionated defaults** — prompts tuned for equity research specifically, bukan generic chat
