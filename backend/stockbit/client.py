"""StockBit API auth client — login + bearer token cache + auto-refresh.

Reverse-engineered API (no official public docs). URLs may break — keep
fallback paths and clear error logs.

Key decisions:
- Token cached in memory only (not persisted). Fresh login on each Portico restart.
- 401 → automatic re-login + retry once (then fail)
- Rate limit conservative: 0.5s sleep between requests to avoid account ban
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from threading import Lock

logger = logging.getLogger("stockbit.client")

# ── Config (all env-driven, with sensible defaults) ──────────────────

LOGIN_URL = os.getenv(
    "STOCKBIT_LOGIN_URL",
    "https://api.stockbit.com/v2.4/login",
)
EXODUS_BASE = os.getenv("STOCKBIT_EXODUS_BASE", "https://exodus.stockbit.com")
RATE_LIMIT_SLEEP = float(os.getenv("STOCKBIT_RATE_LIMIT_SLEEP", "0.5"))
LOGIN_RETRY_ATTEMPTS = 3

# In-memory token state
_TOKEN: str | None = None
_TOKEN_AT: float = 0.0
_TOKEN_TTL_SECONDS = int(os.getenv("STOCKBIT_TOKEN_TTL_SECONDS", "3600"))  # 1h conservative
_TOKEN_LOCK = Lock()


def email() -> str:
    return os.getenv("STOCKBIT_EMAIL", "").strip()


def password() -> str:
    return os.getenv("STOCKBIT_PASSWORD", "").strip()


def is_configured() -> bool:
    """True if both credentials are set in env. Used by callers + endpoints
    to gracefully degrade when StockBit not provisioned."""
    return bool(email()) and bool(password())


def _login_sync() -> str | None:
    """Login to StockBit, return bearer token or None on failure."""
    if not is_configured():
        logger.warning("StockBit not configured — STOCKBIT_EMAIL/STOCKBIT_PASSWORD missing")
        return None

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.exception("curl_cffi missing — required for StockBit login")
        return None

    sess = cffi_requests.Session(impersonate="chrome")
    # Try query-param login (per New-Composite-API pattern)
    url = f"{LOGIN_URL}?user={email()}&password={password()}"
    try:
        resp = sess.post(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        if resp.status_code != 200:
            logger.error("StockBit login HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        # Try common token field names
        for key in ("access_token", "accessToken", "token", "data"):
            v = data.get(key) if isinstance(data, dict) else None
            if isinstance(v, str) and len(v) > 20:
                return v
            if isinstance(v, dict):
                for inner in ("access_token", "accessToken", "token"):
                    if isinstance(v.get(inner), str) and len(v[inner]) > 20:
                        return v[inner]
        logger.error("StockBit login response missing token field: %s", str(data)[:200])
        return None
    except Exception:
        logger.exception("StockBit login failed")
        return None


def get_token(force_refresh: bool = False) -> str | None:
    """Return current token, refreshing if expired or forced."""
    global _TOKEN, _TOKEN_AT
    with _TOKEN_LOCK:
        now = time.time()
        if not force_refresh and _TOKEN and (now - _TOKEN_AT) < _TOKEN_TTL_SECONDS:
            return _TOKEN
    # Login outside lock (network call)
    token = _login_sync()
    if token:
        with _TOKEN_LOCK:
            _TOKEN = token
            _TOKEN_AT = time.time()
        logger.info("StockBit token refreshed")
    return token


def invalidate_token() -> None:
    """Force next call to re-login. Use after a 401."""
    global _TOKEN, _TOKEN_AT
    with _TOKEN_LOCK:
        _TOKEN = None
        _TOKEN_AT = 0.0


def _http_get_sync(url: str, retries: int = LOGIN_RETRY_ATTEMPTS) -> dict | None:
    """Authenticated GET with retry on 401 (re-login + retry once)."""
    if not is_configured():
        return None
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        return None

    last_err: Exception | None = None
    for attempt in range(retries):
        token = get_token(force_refresh=(attempt > 0))
        if not token:
            return None
        sess = cffi_requests.Session(impersonate="chrome")
        try:
            resp = sess.get(url, timeout=15, headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            })
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                logger.info("StockBit 401 — invalidating token, retry attempt %d", attempt + 1)
                invalidate_token()
                continue
            logger.warning("StockBit GET %s → HTTP %d: %s", url, resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            last_err = e
            logger.warning("StockBit GET attempt %d failed: %s", attempt + 1, e)
        time.sleep(RATE_LIMIT_SLEEP)
    if last_err:
        logger.error("StockBit GET failed after %d retries: %s", retries, last_err)
    return None


async def http_get(url: str) -> dict | None:
    """Async wrapper — runs blocking curl_cffi in thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _http_get_sync, url)
