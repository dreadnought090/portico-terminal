# Portico Skill Library

Knowledge documents (markdown SKILL.md) and helper code, copied from
[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT licensed).

**Purpose**: reference library for development + on-demand LLM context. Skills
are **NOT** auto-injected into any prompt — they're loaded explicitly when a
specific feature needs the knowledge.

## How to use

### 1. As development reference
Read the SKILL.md files when designing a feature. Each skill explains theory,
gives quant signals, formulas, and code examples.

### 2. As LLM context (on-demand)
```python
from backend.skills._loader import load_skill, list_skills

# List all available skills
print(list_skills())

# Load specific skill content (e.g., into Council prompt)
content = load_skill("asset-allocation")
prompt = f"""You are an investment analyst. Reference framework:

{content}

Analyze portfolio: ..."""
```

### 3. As compact checklist (cost-efficient)
Distill skill into 80-150 token checklist before injecting. Skills full ~300-500
tokens each — bloat heavy if naively injected per call.

## Cost guidance

| Use case | Naive (full skill) | Smart (checklist) |
|---|---|---|
| Merriot extraction (~80×/mo) | +$0.16/mo | $0 (skip) |
| Council (manual) | +$0.05/mo cached | +$0.01/mo |
| Portfolio analyzer (manual) | +$0.02/mo cached | +$0.01/mo |
| Briefing summarizer | +$5/mo | skip |

**Recommendation**: skills for manual-triggered analysis (Council, Portfolio
Analyzer) — fine. Skip auto-loading for high-frequency paths (Merriot, briefing).

## Skill index — relevant for IDX investor

### TIER 1 — directly relevant
| Skill | Use case |
|---|---|
| asset-allocation | Portfolio rebalance recommender (MPT, Black-Litterman, risk parity) |
| behavioral-finance | Bias check on Merriot thesis (overreaction, anchoring) |
| risk-analysis | VaR, drawdown, beta — portfolio dashboard |
| valuation-model | DCF, comparables — Council reference |
| fundamental-filter | Watchlist screening criteria |
| factor-research | Quant factor design |
| multi-factor | Factor combination strategy |
| sentiment-analysis | Market mood read |
| financial-statement | Fundamental analysis frame |
| trade-journal | Journal best practices |

### TIER 2 — situational
| Skill | Use case |
|---|---|
| earnings-forecast / earnings-revision | Pre-earnings thesis |
| correlation-analysis | Portfolio overlap detection |
| sector-rotation | Macro positioning |
| pair-trading | Long-short setup |
| seasonal | Time-of-year patterns |
| event-driven | Catalyst playbook |

### TIER 3 — niche / not IDX-relevant (kept for completeness)
- China A-share specific: `akshare`, `tushare`, `ashare-pre-st-filter`,
  `chanlun`, `adr-hshare`, `hk-connect-flow`
- US-specific: `edgar-sec-filings`, `us-etf-flow`
- Crypto: `ccxt`, `okx-market`, `crypto-derivatives`, `defi-yield`,
  `onchain-analysis`, `stablecoin-flow`, `perp-funding-basis`,
  `liquidation-heatmap`, `token-unlock-treasury`
- TA-heavy (skip if no chart): `ichimoku`, `elliott-wave`, `harmonic`, `smc`,
  `candlestick`
- Export utilities: `vnpy-export`, `pine-script`

## Attribution

Skills copied from Vibe-Trading project:
- Repository: https://github.com/HKUDS/Vibe-Trading
- License: MIT (see LICENSE.upstream in this folder)
- Contributors: Vibe-Trading Contributors © 2026

This project (Portico) is independent. The skill markdowns are reference
documents and don't impose AGPL-style copyleft (MIT permits use with attribution).
