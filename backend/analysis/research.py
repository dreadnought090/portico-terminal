"""Research Pipeline — auto-draft thesis memo from Portico stock data.

MVP: uses existing stock_service functions to gather context,
then Claude Opus composes initial IC memo. User edits the draft.
"""
import os
import logging
import asyncio
from datetime import datetime, timezone

import anthropic

from backend.analysis.prompts import (
    MEMO_DRAFT_MODEL,
    format_memo_draft_input,
    PROMPT_VERSION,
)

logger = logging.getLogger("mybloomberg.research")

ANTHROPIC_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MEMO_MAX_TOKENS = int(os.environ.get("MEMO_DRAFT_MAX_TOKENS", "3000"))

MODEL_COSTS = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    cost = MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens / 1_000_000 * cost["input"]) + (output_tokens / 1_000_000 * cost["output"])


def _gather_context(ticker: str, db) -> dict:
    """
    Gather stock + profile + financials + peers + news using existing Portico services.
    Runs sync calls — acceptable since memo draft is not high-frequency.
    """
    from backend.stock_service import (
        fetch_stock_data,
        fetch_corporate_profile,
        fetch_financials,
    )
    from backend.models import StockCache

    ticker = ticker.upper().strip()

    try:
        stock_data = fetch_stock_data(ticker)
        stock_data["ticker"] = ticker
    except Exception as e:
        logger.exception("Failed fetch_stock_data for %s", ticker)
        stock_data = {"ticker": ticker, "error": str(e)}

    try:
        profile = fetch_corporate_profile(ticker)
    except Exception as e:
        logger.exception("Failed fetch_corporate_profile for %s", ticker)
        profile = {"error": str(e)}

    try:
        financials = fetch_financials(ticker)
    except Exception as e:
        logger.exception("Failed fetch_financials for %s", ticker)
        financials = {"error": str(e)}

    # Peers: query stock_cache table by sub_sector
    peers = []
    sub_sector = stock_data.get("sub_sector") or stock_data.get("industry")
    if sub_sector and db is not None:
        peer_rows = (
            db.query(StockCache)
            .filter(StockCache.sub_sector == sub_sector, StockCache.ticker != ticker)
            .filter(StockCache.pe_ratio > 0)
            .order_by(StockCache.market_cap.desc())
            .limit(5)
            .all()
        )
        peers = [
            {
                "ticker": p.ticker,
                "pe_ratio": round(p.pe_ratio, 2) if p.pe_ratio else None,
                "pb_ratio": round(p.pb_ratio, 2) if p.pb_ratio else None,
                "dividend_yield": round(p.dividend_yield * 100, 2) if p.dividend_yield else 0,
                "market_cap": p.market_cap,
            }
            for p in peer_rows
        ]

    # News (async function — run in sync context via a fresh loop)
    news = []
    try:
        from backend.stock_service import fetch_news_for_ticker
        news = asyncio.run(fetch_news_for_ticker(ticker))
    except Exception as e:
        logger.exception("Failed fetch_news for %s", ticker)
        news = []

    return {
        "stock_data": stock_data,
        "profile": profile,
        "financials": financials,
        "peers": peers,
        "news": news,
    }


async def draft_memo(ticker: str, db) -> dict:
    """
    Draft initial thesis memo for ticker using existing Portico data.

    Returns:
        dict with memo markdown + metadata + cost tracking.
    """
    if not ANTHROPIC_API_KEY:
        return {
            "error": "API key belum diset.",
            "ticker": ticker,
            "memo_md": "",
        }

    start = datetime.now(timezone.utc)

    # Step 1 — gather context (sync calls, ~5-15s depending on network)
    try:
        context = _gather_context(ticker, db)
    except Exception as e:
        logger.exception("Failed to gather context")
        return {"error": f"Gagal fetch data {ticker}: {e}", "ticker": ticker, "memo_md": ""}

    stock_data = context["stock_data"]
    if stock_data.get("error") and not stock_data.get("last_price"):
        return {
            "error": f"Ticker {ticker} tidak ditemukan atau data tidak tersedia.",
            "ticker": ticker,
            "memo_md": "",
        }

    # Step 2 — compose prompt
    prompt_text = format_memo_draft_input(
        stock_data=stock_data,
        profile=context["profile"],
        financials=context["financials"],
        peers=context["peers"],
        news=context["news"],
    )

    # Step 3 — LLM call
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = await client.messages.create(
            model=MEMO_DRAFT_MODEL,
            max_tokens=MEMO_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt_text}],
        )
        memo_md = message.content[0].text if message.content else ""
        usage = message.usage
        cost = _estimate_cost(MEMO_DRAFT_MODEL, usage.input_tokens, usage.output_tokens)
    except Exception as e:
        logger.exception("LLM call failed during memo draft")
        return {
            "error": f"LLM error: {e}",
            "ticker": ticker,
            "memo_md": "",
        }

    duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    return {
        "ticker": ticker,
        "memo_md": memo_md,
        "model": MEMO_DRAFT_MODEL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": cost,
        "duration_ms": duration_ms,
        "prompt_version": PROMPT_VERSION,
        "context_summary": {
            "peers_count": len(context["peers"]),
            "news_count": len(context["news"]),
            "has_profile": bool(context["profile"]),
            "has_financials": bool(context["financials"]),
        },
        "error": None,
    }


def estimate_draft_cost() -> dict:
    """Rough cost estimate for memo draft."""
    # Typical: ~5000 input tokens (stock + profile + peers + news) + ~2000 output
    cost = _estimate_cost(MEMO_DRAFT_MODEL, 5000, 2000)
    return {
        "total_cost_usd": round(cost, 4),
        "model": MEMO_DRAFT_MODEL,
        "estimate_note": "Rough estimate. Actual varies based on profile/news volume ±40%.",
    }
