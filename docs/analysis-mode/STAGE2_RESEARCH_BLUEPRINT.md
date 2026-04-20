# Stage 2 — Research Pipeline Blueprint

Auto-draft thesis memo dari data publik. User edit dari v0.9, ga start from zero.

## High-level flow

```
User input: ticker + (optional) focus_area
        │
        ▼
┌──────────────────────────────────────┐
│  Orchestrator (research.py)           │
└──┬────────────────┬───────────────────┘
   │                │
   ▼                ▼
Data fetch       LLM compose
 │ yfinance       │ Claude Opus
 │ IDX API        │ with structured
 │ News RSS       │ section prompts
 │ Peer selector  │
 ▼                ▼
Structured dict  Memo markdown
        \       /
         \     /
          ▼   ▼
    Final memo.md (saved to ThesisMemo table)
```

## Data sources per section

| Memo section | Source |
|--------------|--------|
| Business description | IDX annual report (PDF parse) atau yfinance `.info` |
| Financial highlights | yfinance `.financials`, `.balance_sheet`, `.cashflow` |
| Valuation multiples | yfinance `.info` (PER, PBV, yield) + peers |
| Peer comparison | Auto-select top 5 by `sub_sector` from `stock_cache` table |
| Management track record | News search "CEO name + company" last 2 years |
| Recent news sentiment | RSS aggregator (existing `fetch_news_for_ticker`) |
| Bull/bear cases | LLM extract dari news + financials |
| Catalysts | LLM identify dari annual report + guidance |
| Risks | LLM extract dari 10-K risk factors + industry context |
| Recommendation | LLM synthesis (BUY/HOLD/SELL with rationale) |

## Prompt structure

```python
MEMO_MASTER_PROMPT = """
You are a senior equity analyst drafting an IC memo for Indonesian stock {ticker}.

Input data:
- Company: {company_name}
- Sector: {sub_sector}
- Current price: {current_price}
- Market cap: {market_cap}
- PER: {pe_ratio}, PBV: {pb_ratio}
- Recent financials: {financials_summary}
- Peer multiples: {peer_table}
- Recent news (last 90 days): {news_list}

Output a structured IC memo in Bahasa Indonesia dengan sections:

## 1. Thesis
## 2. Business Overview
## 3. Financial Analysis  
## 4. Valuation
## 5. Bull Case (3 points)
## 6. Bear Case (3 points)
## 7. Catalysts (next 12 months)
## 8. Risks
## 9. Recommendation

Style: concise, quantitative, cite specific numbers, avoid fluff.
Length: 800-1500 words.
"""
```

## Implementation skeleton

```python
# backend/analysis/research.py
from dataclasses import dataclass
from typing import Optional
import anthropic
from backend.analysis.sources import idx_fetcher, news_aggregator, peer_selector
from backend.analysis.prompts import MEMO_MASTER_PROMPT
from backend.models import ThesisMemo, AnalysisRun


@dataclass
class ResearchInput:
    ticker: str
    company_name: str
    focus_area: Optional[str] = None  # e.g., "merger", "earnings surprise"


async def draft_memo(input: ResearchInput, db) -> ThesisMemo:
    # 1. Fetch data (parallel)
    financials = await idx_fetcher.get_financials(input.ticker)
    news = await news_aggregator.get_recent(input.ticker, days=90)
    peers = await peer_selector.get_comparables(input.ticker, db, n=5)
    
    # 2. Compose prompt context
    context = {
        'ticker': input.ticker,
        'company_name': input.company_name,
        'financials_summary': summarize_financials(financials),
        'peer_table': format_peer_table(peers),
        'news_list': format_news(news),
    }
    
    # 3. Call LLM
    client = anthropic.Anthropic()
    response = await client.messages.create(
        model='claude-opus-4-7',
        max_tokens=4000,
        messages=[{
            'role': 'user', 
            'content': MEMO_MASTER_PROMPT.format(**context)
        }]
    )
    
    # 4. Save
    memo = ThesisMemo(
        ticker=input.ticker,
        version=get_next_version(input.ticker, db),
        content_md=response.content[0].text,
    )
    db.add(memo)
    db.commit()
    
    # 5. Log run
    log_run(db, 'research', ...)
    
    return memo
```

## Frontend integration

- Button "📝 Draft Memo" di Analysis Panel
- After draft ready: open in-app markdown editor (monaco or simpler textarea)
- Save button: store as new `ThesisMemo` version
- History: dropdown of v1, v2, v3 → diff view

## Cost estimate

- Fetch + prompt composition: ~5000 tokens input
- Memo output: ~2000 tokens output
- Claude Opus: ~$0.40-0.80 per memo
- Target: 20-40 memos per month = $10-30/month

## Open design decisions

1. **Memo language** — Bahasa Indonesia full, atau mix (Indonesian narrative + English financial term)?
2. **Length** — 800-1500 words (quick read), atau 2500-4000 (deep)?
3. **Multi-turn?** — auto-draft then user asks follow-up questions dalam panel yang sama?
4. **Template per sector** — Banking memo berbeda dari Mining berbeda dari Telco?

Put decisions here when made.
