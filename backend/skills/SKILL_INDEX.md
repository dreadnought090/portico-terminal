# Portico Skill Library — Status & Use Cases

73 skills total · 2 deployed · 71 dormant (ready on-demand)

Source: [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT)

---

## 🟢 DEPLOYED (2)

Currently injected into Portico LLM prompts.

| Skill | Wired into | Use case |
|---|---|---|
| `valuation-model` | `prompts.py` (all 4 council roles) | DCF/PE-Band/PB-ROE frame; trap detection. Council bull/bear/macro/devil semua dapat baseline. |
| `asset-allocation` | `portfolio_analyzer.py` (SYSTEM_PROMPT) | MPT/BL/risk parity + IDX-specific limits (max 20% single-name, 30% sector). For rebalance recommendations. |

---

## 🟡 TIER 1 — High-value, undeployed (8)

Tinggal pasang kalau butuh. Token cost ~150 each kalau distill.

| Skill | Use case di Portico |
|---|---|
| `behavioral-finance` | Bias check di Merriot thesis review. Catches anchoring/overreaction bias |
| `risk-analysis` | VaR/CVaR/max drawdown — portfolio risk dashboard |
| `factor-research` | IC/IR analysis — quantify factor exposure |
| `multi-factor` | Multi-factor cross-sectional ranking — watchlist screening |
| `sentiment-analysis` | Fear/greed index, Put-Call ratio, North fund flow — IDX market mood |
| `fundamental-filter` | PE/PB/ROE screening — auto-filter watchlist by criteria |
| `financial-statement` | 3-statement deep dive, DuPont, accounting red flags |
| `trade-journal` | Parse broker exports (CSV/Excel) — Merriot integration potential |

---

## 🟠 TIER 2 — Situational (28)

Useful kalau pas butuh fitur tertentu.

### Earnings & catalysts
| Skill | Use case |
|---|---|
| `earnings-forecast` | Pre-earnings positioning, SUE/PEAD signals |
| `earnings-revision` | Analyst consensus tracking, post-earnings drift |
| `corporate-events` | M&A arbitrage, insider sells, ST/delisting alert (A-share specific tapi adaptable) |
| `event-driven` | News/announcement-driven signals |
| `seasonal` | Calendar effects (Jan effect, sell-in-May) |

### Portfolio & risk
| Skill | Use case |
|---|---|
| `correlation-analysis` | Portfolio overlap detection, sector clustering |
| `performance-attribution` | Brinson sector/stock-pick attribution |
| `hedging-strategy` | Beta hedge, tail risk protection |
| `pair-trading` | Mean-reversion long-short |

### Macro & fundamentals
| Skill | Use case |
|---|---|
| `macro-analysis` | GDP/CPI/PMI/rates — top-down positioning |
| `global-macro` | Central bank policy, FX, capital flows |
| `geopolitical-risk` | War/sanctions/election impact |
| `commodity-analysis` | Oil/gold/copper supply-demand cycle |
| `credit-analysis` | Bond spreads, default risk, city-investment bonds |
| `regulatory-knowledge` | A-share/HK/US/crypto regulation reference |
| `sector-rotation` | Industry momentum + valuation comparison |

### Quant & strategy
| Skill | Use case |
|---|---|
| `quant-statistics` | ADF, cointegration, GARCH — academic frame |
| `ml-strategy` | sklearn walk-forward, feature engineering |
| `strategy-generate` | Strategy creation framework |
| `backtest-diagnose` | Why my backtest failed (root-cause) |
| `execution-model` | Slippage modeling for backtests |
| `minute-analysis` | Intraday data signals |
| `shadow-account` | Trade journal → 3-5 rules → cross-market backtest |

### ETF & funds
| Skill | Use case |
|---|---|
| `etf-analysis` | ETF screening, tracking error |
| `fund-analysis` | Sharpe/IR, style box, manager evaluation |
| `convertible-bond` | Convert/pure-bond/option valuation |

### Sentiment & data
| Skill | Use case |
|---|---|
| `social-media-intelligence` | Twitter/Telegram/Discord signals |
| `data-routing` | Smart data source selection |
| `doc-reader` | Multi-format file parsing (PDF/Word/Excel/PPT) |
| `report-generate` | Professional research report scaffold |

---

## ⚪ TIER 3 — Niche / not IDX-relevant (35)

Kept for completeness. Skip kecuali expand ke market lain.

### China A-share specific
`akshare`, `tushare`, `ashare-pre-st-filter`, `chanlun`, `adr-hshare`, `hk-connect-flow`

### US-specific
`edgar-sec-filings`, `us-etf-flow`

### Crypto-only
`ccxt`, `okx-market`, `crypto-derivatives`, `defi-yield`, `onchain-analysis`,
`stablecoin-flow`, `perp-funding-basis`, `liquidation-heatmap`,
`token-unlock-treasury`

### TA-heavy (pattern recognition)
`candlestick`, `ichimoku`, `elliott-wave`, `harmonic`, `smc`, `technical-basic`,
`market-microstructure`

### Options-specific
`options-strategy`, `options-payoff`, `options-advanced`, `volatility`

### Cross-market / export
`cross-market-strategy`, `vnpy-export`, `pine-script`

### Misc / utility
`web-reader`, `yfinance`

---

## How to deploy a skill

### 1. Compact checklist (recommended)
Edit `backend/skills/_checklists.py`, distill skill → 100-150 token constant.
Wire into target prompt:
```python
from backend.skills._checklists import MY_SKILL_CHECKLIST
SYSTEM_PROMPT += "\n\n" + MY_SKILL_CHECKLIST
```

### 2. Full skill load (heavier, but more context)
```python
from backend.skills._loader import load_skill
content = load_skill("risk-analysis")
prompt = base_prompt + "\n\n" + content
```

### 3. Dev reference only (zero LLM cost)
Read SKILL.md when designing a feature. Use as algorithm spec.

---

## Cost guidance

| Approach | Token cost | Recommended for |
|---|---|---|
| Compact checklist (~150 tok) | $0.001-0.005 per call | Manual-triggered (Council, Analyzer) |
| Full skill (~3000 tok) | $0.05+ per call | Rare deep-dive analysis |
| Dev reference only | $0 | Development design phase |
| Naive auto-inject all calls | $5+/mo | ❌ Don't |
