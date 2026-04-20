# External API Keys — Cheat Sheet

Add to `.env` as you enable each feature.

## Currently used (Stage 0 — existing)

| Key | Service | Purpose | Where used |
|-----|---------|---------|------------|
| `OPENROUTER_API_KEY` | Anthropic API (named OPENROUTER historically) | Claude Vision OCR | `backend/ocr_service.py` |
| `AUTH_PASSWORD` | Portico self-auth | Login | `app.py` |

---

## Stage 1 — Council (this branch)

No new key needed. Reuse existing `OPENROUTER_API_KEY`.

Optional:
| Key | Service | Purpose |
|-----|---------|---------|
| `OLLAMA_BASE_URL` | Ollama local | Privacy mode fallback (default `http://localhost:11434/v1`) |

---

## Stage 2 — Research Pipeline (later)

| Key | Service | Cost | Priority |
|-----|---------|------|----------|
| `SECTORS_APP_API_KEY` | Sectors.app | Paid (~$29-99/mo) | High — best IDX data |
| `FMP_API_KEY` | Financial Modeling Prep | Free tier 250 req/day | Medium — US comparables |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage | Free 25 req/day | Low — backup |
| `NEWS_API_KEY` | NewsAPI.org | Free 100 req/day | Medium — news aggregation |
| `TEGUS_API_KEY` | Tegus | Enterprise | Low — expert call transcripts |

Start with: Sectors.app (if budget allows) + NewsAPI free tier.

---

## Stage 3 — Sentiment Simulation (later)

| Key | Service | Cost | Priority |
|-----|---------|------|----------|
| `NEO4J_URI` + `NEO4J_USER` + `NEO4J_PASSWORD` | Neo4j Aura | Free 50MB | Medium |
| `TWITTER_BEARER_TOKEN` | Twitter/X API | Paid ($100+/mo) | Low — persona seed |
| `REDDIT_CLIENT_ID` + `REDDIT_SECRET` | Reddit API | Free | Medium |

---

## Stage 4 — Morning Brief (later)

| Key | Service | Cost | Priority |
|-----|---------|------|----------|
| `TELEGRAM_BOT_TOKEN` | BotFather | Free | High — notification delivery |
| `RESEND_API_KEY` or `SMTP_*` | Email | Free tier | Medium — email brief |

---

## Stage 5 — Extended

| Key | Service | Cost | Priority |
|-----|---------|------|----------|
| `NANSEN_API_KEY` | Nansen (crypto on-chain) | Pay-per-call | Low — crypto correlation tracking |
| `OPENROUTER_API_KEY` (separate) | OpenRouter | Pay-per-token | Medium — multi-model council |

---

## Key rotation & security

- **Never commit `.env`** — sudah di `.gitignore`
- Rotate Anthropic key every 90 days
- Use budget limits di Anthropic Console (Settings → Limits) untuk prevent runaway cost
- Optional: use API key per environment (dev/prod terpisah)
