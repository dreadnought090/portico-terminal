"""Per-ticker broker summary fetcher (StockBit's "Bandar Detector").

URL TEMPLATES are educated guesses — actual endpoint discoverable by
logging into StockBit web, opening F12 → Network on broker-summary tab,
copying URL. Override via env STOCKBIT_BROKER_SUMMARY_URL_TEMPLATE
without code change.

Default attempts (in order):
1. exodus.stockbit.com/company-page/v1/broker-summary/{ticker}?date={YYYYMMDD}
2. exodus.stockbit.com/broker-summary/v1/{ticker}?date={YYYYMMDD}
3. api.stockbit.com/v2.4/company/{ticker}/broker-summary?date={YYYYMMDD}

If none match, return error dict explaining how to discover correct URL.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from backend.stockbit.client import EXODUS_BASE, http_get, is_configured

logger = logging.getLogger("stockbit.broker_summary")

WIB = timezone(timedelta(hours=7))

# User-overridable URL template (set via env once correct URL discovered).
URL_TEMPLATE_ENV = os.getenv("STOCKBIT_BROKER_SUMMARY_URL_TEMPLATE", "")

# Fallback URL templates to try in order (educated guesses).
_FALLBACK_TEMPLATES = [
    f"{EXODUS_BASE}/company-page/v1/broker-summary/{{ticker}}?date={{date}}",
    f"{EXODUS_BASE}/broker-summary/v1/{{ticker}}?date={{date}}",
    f"{EXODUS_BASE}/company-price-feed/v2/broker-summary/{{ticker}}?date={{date}}",
    "https://api.stockbit.com/v2.4/company/{ticker}/broker-summary?date={date}",
]


def _normalize_date(date_str: str | None) -> str:
    """Default to today (WIB), format YYYYMMDD."""
    if date_str:
        # Accept YYYY-MM-DD or YYYYMMDD
        return date_str.replace("-", "")[:8]
    return datetime.now(WIB).strftime("%Y%m%d")


async def fetch_broker_summary(ticker: str, date_str: str | None = None) -> dict:
    """Fetch broker summary for one ticker.

    Returns:
        {
            "configured": bool,
            "ticker": str,
            "date": "YYYYMMDD",
            "rows": [{broker, buy_value, sell_value, net_value, ...}, ...]
              (when successful)
            "error": str (when failed)
            "discovery_hint": str (when all URL templates 404 — guide user)
        }
    """
    if not is_configured():
        return {
            "configured": False,
            "ticker": ticker.upper(),
            "error": "StockBit not configured",
            "hint": "Set STOCKBIT_EMAIL and STOCKBIT_PASSWORD in .env, then restart Portico.",
        }

    code = ticker.upper().replace(".JK", "").strip()
    date_norm = _normalize_date(date_str)

    # Build URL list — env override takes priority
    templates = []
    if URL_TEMPLATE_ENV:
        templates.append(URL_TEMPLATE_ENV)
    templates.extend(_FALLBACK_TEMPLATES)

    last_attempt = None
    for tmpl in templates:
        url = tmpl.format(ticker=code, date=date_norm)
        last_attempt = url
        result = await http_get(url)
        if result is not None:
            # Got JSON — try to normalize structure
            normalized = _normalize_response(result, code, date_norm)
            if normalized:
                return {
                    "configured": True,
                    "ticker": code,
                    "date": date_norm,
                    "rows": normalized,
                    "source_url": url,
                }
        # Sleep between template attempts to avoid spam
        await asyncio.sleep(0.3)

    # All templates failed
    return {
        "configured": True,
        "ticker": code,
        "date": date_norm,
        "error": "All URL templates returned no data — endpoint may have changed.",
        "discovery_hint": (
            "Login to stockbit.com → open ticker page → F12 Network tab → "
            "click 'Broker Summary' → copy the request URL. Then set in .env:\n"
            "STOCKBIT_BROKER_SUMMARY_URL_TEMPLATE='<your-url-here>'\n"
            "Use {ticker} and {date} as placeholders."
        ),
        "tried_urls": templates,
        "last_attempt": last_attempt,
    }


def _normalize_response(raw: dict, ticker: str, date: str) -> list[dict] | None:
    """Try to extract broker rows from various response shapes.

    StockBit's actual schema unknown — be defensive. Look for common patterns:
    - {"data": [{"broker_code", "buy_val", "sell_val", ...}, ...]}
    - {"brokers": [...]}
    - List of dicts directly
    """
    if not raw:
        return None

    # Direct list
    if isinstance(raw, list) and raw:
        return [_normalize_row(r) for r in raw if isinstance(r, dict)]

    if isinstance(raw, dict):
        for key in ("data", "brokers", "rows", "result", "items"):
            v = raw.get(key)
            if isinstance(v, list) and v:
                return [_normalize_row(r) for r in v if isinstance(r, dict)]
            # Sometimes nested deeper
            if isinstance(v, dict):
                for inner in ("data", "brokers", "rows", "items"):
                    inner_v = v.get(inner)
                    if isinstance(inner_v, list) and inner_v:
                        return [_normalize_row(r) for r in inner_v if isinstance(r, dict)]

    return None


def _normalize_row(r: dict) -> dict:
    """Normalize one broker row to consistent keys (best-effort)."""
    return {
        "broker_code": (r.get("broker_code") or r.get("code") or r.get("brokerCode") or
                        r.get("BrokerCode") or r.get("id_firm") or ""),
        "broker_name": (r.get("broker_name") or r.get("name") or r.get("brokerName") or
                        r.get("BrokerName") or r.get("firm_name") or ""),
        "buy_value": (r.get("buy_value") or r.get("buyValue") or r.get("BuyValue") or
                      r.get("buy_val") or r.get("totalBuyValue") or 0),
        "sell_value": (r.get("sell_value") or r.get("sellValue") or r.get("SellValue") or
                       r.get("sell_val") or r.get("totalSellValue") or 0),
        "net_value": (r.get("net_value") or r.get("netValue") or r.get("NetValue") or
                      r.get("net_val") or 0),
        "buy_volume": (r.get("buy_volume") or r.get("buyVolume") or r.get("buy_vol") or 0),
        "sell_volume": (r.get("sell_volume") or r.get("sellVolume") or r.get("sell_vol") or 0),
        "buy_avg_price": (r.get("buy_avg_price") or r.get("buyAvgPrice") or
                          r.get("avg_buy_price") or 0),
        "sell_avg_price": (r.get("sell_avg_price") or r.get("sellAvgPrice") or
                           r.get("avg_sell_price") or 0),
    }
