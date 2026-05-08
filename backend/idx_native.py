"""IDX native data endpoints (broker summary, foreign flow, dividend, movers).

Ports the URL patterns from NeaByteLab/IDX-API (MIT) to Python using the same
curl_cffi browser-emulation pattern already used in stock_service.py. No new
dependencies. In-memory TTL cache + LRU cap + in-flight dedup keep IDX hits low.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, date as date_cls
from threading import Lock
from typing import Any

# Single shared session — cookies populated lazily, refreshed on staleness.
_SESSION = None
_SESSION_LOCK = Lock()
_SESSION_AT = 0.0
_SESSION_TTL = 1800  # refresh cookies every 30 min

# Endpoint result cache — OrderedDict acts as LRU; capped to prevent leaks.
_CACHE: "OrderedDict[tuple, tuple[float, Any]]" = OrderedDict()
_CACHE_LOCK = Lock()
_CACHE_MAX = 128
_DEFAULT_TTL = 300  # 5 min — for current-day data
_PAST_TTL = 86400   # 24 h — past dates are immutable

# In-flight dedup: collapses concurrent fetches for the same key into one IDX hit.
_INFLIGHT: dict[tuple, asyncio.Future] = {}
_INFLIGHT_LOCK = Lock()


def _get_session():
    """Return a curl_cffi session with valid IDX cookies. Network call happens
    OUTSIDE the lock to avoid thundering-herd stalls on session refresh."""
    from curl_cffi import requests as cffi_requests

    global _SESSION, _SESSION_AT
    now = time.time()
    with _SESSION_LOCK:
        if _SESSION is not None and (now - _SESSION_AT) <= _SESSION_TTL:
            return _SESSION

    # Build new session outside the lock (15s network call).
    sess = cffi_requests.Session(impersonate="chrome")
    try:
        sess.get("https://www.idx.co.id/id", timeout=15)
    except Exception:
        pass

    with _SESSION_LOCK:
        # Another thread may have built one already; if it's fresh, prefer it.
        if _SESSION is None or (time.time() - _SESSION_AT) > _SESSION_TTL:
            _SESSION = sess
            _SESSION_AT = time.time()
        return _SESSION


def _invalidate_session() -> None:
    global _SESSION, _SESSION_AT
    with _SESSION_LOCK:
        _SESSION = None
        _SESSION_AT = 0.0


def _cache_get(key: tuple):
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        expiry, value = entry
        if time.time() >= expiry:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)  # mark recently-used
        return value


def _cache_set(key: tuple, value: Any, ttl: int) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time() + ttl, value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def _ttl_for_date(d_yyyymmdd: str) -> int:
    """Past dates are immutable → cache 24h. Today/future → 5 min."""
    today = datetime.now().strftime("%Y%m%d")
    return _PAST_TTL if d_yyyymmdd < today else _DEFAULT_TTL


def _to_num(v, default=0):
    """Coerce IDX response field to int/float; tolerates None and stringy numbers."""
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _http_get_json(url: str, retries: int = 4) -> Any:
    """Synchronous GET → JSON. Exponential backoff up to ~15s, sleeps only between
    attempts (not after the last). Refreshes session on auth-style failures."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            sess = _get_session()
            resp = sess.get(url, timeout=20, headers={"X-Requested-With": "XMLHttpRequest"})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403, 419):
                _invalidate_session()
            last_err = RuntimeError(f"HTTP {resp.status_code} for {url}")
        except Exception as e:
            last_err = e
            _invalidate_session()
        if attempt < retries:
            time.sleep(min(1.0 * (2 ** attempt), 15.0))
    raise last_err if last_err else RuntimeError("unknown fetch error")


async def _run_in_thread(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


def _normalize_date(value) -> str:
    """Accept 'YYYY-MM-DD', 'YYYYMMDD', date, datetime; return 'YYYYMMDD'."""
    if isinstance(value, (datetime, date_cls)):
        return value.strftime("%Y%m%d")
    s = str(value).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"invalid date: {value!r} (want YYYY-MM-DD or YYYYMMDD)")
    return s


async def _cached_or_fetch(key: tuple, blocking_fn, ttl: int):
    """Cache + in-flight dedup wrapper. Returns cached value, awaits an in-flight
    fetch for the same key, or runs blocking_fn in a thread."""
    cached = _cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    with _INFLIGHT_LOCK:
        existing = _INFLIGHT.get(key)
        if existing is not None:
            fut = existing
        else:
            fut = loop.create_future()
            _INFLIGHT[key] = fut
            owner = True
        if existing is not None:
            owner = False

    if not owner:
        return await fut

    try:
        result = await loop.run_in_executor(None, blocking_fn)
        _cache_set(key, result, ttl)
        if not fut.done():
            fut.set_result(result)
        return result
    except BaseException as e:
        # Catch BaseException (incl. asyncio.CancelledError) so non-owner
        # waiters never hang on an orphaned in-flight future.
        if not fut.done():
            fut.set_exception(e)
        raise
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.pop(key, None)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def fetch_broker_summary(date_str: str | None = None, length: int = 200) -> list[dict]:
    """Top brokers by trading value for a given date."""
    d = _normalize_date(date_str or datetime.now())
    length = max(1, min(int(length), 9999))
    key = ("broker_summary", d, length)

    def _do():
        url = (
            f"https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary"
            f"?length={length}&start=0&date={d}"
        )
        raw = _http_get_json(url)
        items = (raw or {}).get("data") or []
        out = []
        for it in items:
            try:
                out.append({
                    "brokerCode": str(it.get("IDFirm", "") or ""),
                    "brokerName": str(it.get("FirmName", "") or ""),
                    "value": _to_num(it.get("Value")),
                    "volume": _to_num(it.get("Volume")),
                    "frequency": _to_num(it.get("Frequency")),
                })
            except Exception:
                continue
        out.sort(key=lambda x: x["value"], reverse=True)
        return out

    return await _cached_or_fetch(key, _do, _ttl_for_date(d))


async def fetch_stock_summary(date_str: str | None = None) -> list[dict]:
    """Daily OHLC + foreign buy/sell for ALL stocks on given date."""
    d = _normalize_date(date_str or datetime.now())
    key = ("stock_summary", d)

    def _do():
        url = f"https://www.idx.co.id/primary/TradingSummary/GetStockSummary?date={d}"
        raw = _http_get_json(url)
        items = (raw or {}).get("data") or []
        out = []
        for it in items:
            try:
                prev = _to_num(it.get("Previous"))
                close = _to_num(it.get("Close"))
                change = _to_num(it.get("Change"))
                percent = round((change / prev) * 100, 2) if prev else 0.0
                fb = _to_num(it.get("ForeignBuy"))
                fs = _to_num(it.get("ForeignSell"))
                out.append({
                    "code": str(it.get("StockCode", "") or ""),
                    "name": str(it.get("StockName", "") or ""),
                    "open": _to_num(it.get("OpenPrice")),
                    "high": _to_num(it.get("High")),
                    "low": _to_num(it.get("Low")),
                    "close": close,
                    "previous": prev,
                    "change": change,
                    "percent": percent,
                    "volume": _to_num(it.get("Volume")),
                    "value": _to_num(it.get("Value")),
                    "frequency": _to_num(it.get("Frequency")),
                    "foreignBuy": fb,
                    "foreignSell": fs,
                    "foreignNet": fb - fs,
                    "listedShares": _to_num(it.get("ListedShares")),
                })
            except Exception:
                continue
        return out

    return await _cached_or_fetch(key, _do, _ttl_for_date(d))


async def fetch_foreign_flow(ticker: str, date_str: str | None = None) -> dict | None:
    """Foreign buy/sell/net for a single ticker on given date."""
    code = ticker.upper().replace(".JK", "").strip()
    d = _normalize_date(date_str or datetime.now())
    rows = await fetch_stock_summary(d)
    for r in rows:
        if r["code"] == code:
            return {
                "code": r["code"],
                "name": r["name"],
                "date": d,
                "foreignBuy": r["foreignBuy"],
                "foreignSell": r["foreignSell"],
                "foreignNet": r["foreignNet"],
                "value": r["value"],
                "close": r["close"],
                "percent": r["percent"],
            }
    return None


async def fetch_dividend_calendar(year: int | None = None, month: int | None = None,
                                  page_size: int = 100) -> list[dict]:
    """Dividend announcements for given month. Defaults to current month."""
    now = datetime.now()
    y = int(year) if year else now.year
    m = int(month) if month else now.month
    if not (1 <= m <= 12):
        raise ValueError(f"invalid month: {m}")
    if not (2000 <= y <= 2100):
        raise ValueError(f"invalid year: {y}")
    page_size = max(1, min(int(page_size), 500))
    key = ("dividend", y, m, page_size)

    def _do():
        url = (
            "https://www.idx.co.id/primary/DigitalStatistic/GetApiDataPaginated"
            f"?urlName=LINK_DIVIDEND&periodYear={y}&periodMonth={m}"
            f"&periodType=monthly&isPrint=False&cumulative=false"
            f"&pageSize={page_size}&pageNumber=1"
        )
        raw = _http_get_json(url)
        items = (raw or {}).get("data") or []
        out = []
        for it in items:
            try:
                out.append({
                    "code": str(it.get("code", "") or ""),
                    "name": str(it.get("name", "") or ""),
                    "cashDividend": _to_num(it.get("cashDividend")),
                    "cumDate": str(it.get("cumDividend", "") or ""),
                    "exDate": str(it.get("exDividend", "") or ""),
                    "recordDate": str(it.get("recordDate", "") or ""),
                    "paymentDate": str(it.get("paymentDate", "") or ""),
                })
            except Exception:
                continue
        return out

    # Dividend ttl: past month immutable, current/future 1h.
    today = datetime.now()
    is_past = (y, m) < (today.year, today.month)
    return await _cached_or_fetch(key, _do, _PAST_TTL if is_past else 3600)


async def fetch_trading_info_daily(ticker: str) -> dict | None:
    """Per-ticker intraday snapshot — refreshes every ~1-5 min during market
    hours via IDX GetTradingInfoDaily. Used by price alert cron.

    Returns None if ticker not found. 60s cache TTL — finer than _DEFAULT_TTL
    so a 5-min cron always misses cache, but bursty re-checks within 60s collapse.
    """
    code = ticker.upper().replace(".JK", "").strip()
    if not code:
        return None
    key = ("trading_info_daily", code)

    def _do():
        url = f"https://www.idx.co.id/primary/ListedCompany/GetTradingInfoDaily?code={code}"
        raw = _http_get_json(url)
        # Try common response shapes
        it = raw if isinstance(raw, dict) else None
        if it and not (it.get("SecurityCode") or it.get("StockCode")):
            for k in ("Replies", "data"):
                arr = (raw or {}).get(k)
                if isinstance(arr, list) and arr:
                    it = arr[0]
                    break
            else:
                it = None
        if not it:
            return None
        prev = _to_num(it.get("PreviousPrice") or it.get("Previous"))
        close = _to_num(it.get("ClosingPrice") or it.get("Close"))
        open_p = _to_num(it.get("OpeningPrice") or it.get("OpenPrice"))
        high = _to_num(it.get("HighestPrice") or it.get("High"))
        low = _to_num(it.get("LowestPrice") or it.get("Low"))
        change = _to_num(it.get("Change"))
        return {
            "code": code,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "previous": prev,
            "change": change,
            "percent": round((change / prev) * 100, 2) if prev else 0.0,
            "volume": _to_num(it.get("TradedVolume") or it.get("Volume")),
            "value": _to_num(it.get("TradedValue") or it.get("Value")),
            "frequency": _to_num(it.get("TradedFrequency") or it.get("Frequency")),
            "foreign_buy": _to_num(it.get("ForeignBuy")),
            "foreign_sell": _to_num(it.get("ForeignSell")),
            "updated_at": str(it.get("DTCreate") or ""),
        }

    return await _cached_or_fetch(key, _do, 60)


async def fetch_movers(date_str: str | None = None, top_n: int = 20) -> dict:
    """Daily top gainers and losers (derived from stock_summary).

    Excludes illiquid (<Rp 100jt traded) and stocks without a previous close.
    """
    top_n = max(1, min(int(top_n), 100))
    rows = await fetch_stock_summary(date_str)
    eligible = [
        r for r in rows
        if r["previous"] > 0 and r["value"] >= 100_000_000
    ]
    gainers = sorted(eligible, key=lambda r: r["percent"], reverse=True)[:top_n]
    losers = sorted(eligible, key=lambda r: r["percent"])[:top_n]
    fields = ("code", "name", "close", "previous", "change", "percent", "value", "volume")
    return {
        "gainers": [{k: r[k] for k in fields} for r in gainers],
        "losers": [{k: r[k] for k in fields} for r in losers],
    }
