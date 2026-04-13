import yfinance as yf
import httpx
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime, timezone, timedelta
from typing import Optional
import asyncio
import re
import math


def _safe_val(val):
    """Convert value to JSON-safe type. NaN/Inf become None."""
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if hasattr(val, 'item'):
        v = val.item()
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    return val


def _validated_pe(info: dict) -> float:
    """Get PE ratio with validation against profit margins and net income.

    yfinance sometimes returns positive PE for loss-making companies.
    Cross-check with profitMargins and netIncomeToCommon.
    """
    pe = info.get("trailingPE")
    if pe is None or (isinstance(pe, float) and (math.isnan(pe) or math.isinf(pe))):
        return 0

    net_income = info.get("netIncomeToCommon")
    profit_margin = info.get("profitMargins")
    roe = info.get("returnOnEquity")

    # If net income is negative, PE should not be positive
    if net_income is not None and net_income < 0:
        return 0  # N/A for loss-making companies

    # If profit margin is negative, PE should not be positive
    if profit_margin is not None and profit_margin < 0:
        return 0

    # If ROE is deeply negative, likely loss-making
    if roe is not None and roe < -0.05:
        return 0

    return pe or 0


def _validated_eps(info: dict) -> float:
    """Get EPS with cross-validation against net income."""
    eps = info.get("trailingEps")
    if eps is None or (isinstance(eps, float) and (math.isnan(eps) or math.isinf(eps))):
        return 0

    net_income = info.get("netIncomeToCommon")
    profit_margin = info.get("profitMargins")

    # If net income is negative but EPS is positive, yfinance is wrong
    if net_income is not None and net_income < 0 and eps > 0:
        shares = info.get("sharesOutstanding", 0) or 1
        return net_income / shares  # Calculate real EPS

    if profit_margin is not None and profit_margin < 0 and eps > 0:
        return 0

    return eps or 0


def _validated_pe_forward(info: dict) -> float:
    """Get forward PE with validation."""
    pe = info.get("forwardPE")
    if pe is None or (isinstance(pe, float) and (math.isnan(pe) or math.isinf(pe))):
        return 0
    forward_eps = info.get("forwardEps")
    if forward_eps is not None and forward_eps < 0:
        return 0
    return pe or 0


IDX_SECTORS = {
    "BBCA": "Banking", "BBRI": "Banking", "BMRI": "Banking", "BBNI": "Banking",
    "BRIS": "Banking", "BTPS": "Banking", "ARTO": "Banking", "BNGA": "Banking",
    "BDMN": "Banking", "MEGA": "Banking", "NISP": "Banking", "PNBN": "Banking",
    "ADRO": "Mining", "PTBA": "Mining", "ITMG": "Mining", "ANTM": "Mining",
    "INCO": "Mining", "MDKA": "Mining", "TINS": "Mining", "MEDC": "Energy",
    "PGAS": "Energy", "AKRA": "Energy", "ELSA": "Energy",
    "TLKM": "Telecommunication", "EXCL": "Telecommunication", "ISAT": "Telecommunication",
    "TOWR": "Telecommunication", "TBIG": "Telecommunication",
    "ASII": "Misc Industry", "UNTR": "Trade & Services",
    "ICBP": "Consumer Goods", "INDF": "Consumer Goods", "UNVR": "Consumer Goods",
    "MYOR": "Consumer Goods", "KLBF": "Healthcare", "SIDO": "Healthcare",
    "HMSP": "Consumer Goods", "GGRM": "Consumer Goods",
    "CPIN": "Basic Industry & Chemical", "INKP": "Basic Industry & Chemical",
    "TKIM": "Basic Industry & Chemical", "SMGR": "Basic Industry & Chemical",
    "INTP": "Basic Industry & Chemical", "BRPT": "Basic Industry & Chemical",
    "BSDE": "Property & Real Estate", "CTRA": "Property & Real Estate",
    "SMRA": "Property & Real Estate", "PWON": "Property & Real Estate",
    "EMTK": "Technology", "GOTO": "Technology", "BUKA": "Technology",
    "AMMN": "Mining", "HRUM": "Mining", "PGEO": "Energy",
}


def _parse_div_yield(raw) -> float:
    """Parse dividend yield from yfinance.

    yfinance consistently returns dividendYield as a decimal fraction
    (e.g., 0.02 = 2%, 0.008 = 0.8%). We always multiply by 100.
    Values that are already > 0.5 (50%) are almost certainly already
    in percent form (no IDX stock yields 50%+), so we return as-is.
    """
    val = raw or 0
    if val == 0:
        return 0.0
    if val > 0.5:
        # Already in percentage form (sanity: no stock yields 50%+)
        return round(val, 2)
    return round(val * 100, 2)


def get_idx_ticker(ticker: str) -> str:
    """Convert ticker to Yahoo Finance IDX format."""
    ticker = ticker.upper().strip()
    if not ticker.endswith(".JK"):
        ticker = f"{ticker}.JK"
    return ticker


def fetch_stock_data(ticker: str) -> dict:
    """Fetch stock data from Yahoo Finance for IDX stocks."""
    yf_ticker = get_idx_ticker(ticker)
    clean_ticker = ticker.upper().replace(".JK", "")

    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        if not info or info.get("regularMarketPrice") is None:
            hist = stock.history(period="5d")
            if hist.empty:
                return {"error": f"Data tidak ditemukan untuk {clean_ticker}"}

            last_row = hist.iloc[-1]
            prev_row = hist.iloc[-2] if len(hist) > 1 else last_row
            last_price = float(last_row["Close"])
            prev_close = float(prev_row["Close"])

            return {
                "ticker": clean_ticker,
                "company_name": info.get("shortName", info.get("longName", clean_ticker)),
                "sector": IDX_SECTORS.get(clean_ticker, info.get("sector", "Other")),
                "last_price": last_price,
                "prev_close": prev_close,
                "open_price": float(last_row.get("Open", 0)),
                "high": float(last_row.get("High", 0)),
                "low": float(last_row.get("Low", 0)),
                "volume": int(last_row.get("Volume", 0)),
                "market_cap": info.get("marketCap", 0) or 0,
                "pe_ratio": _validated_pe(info),
                "pb_ratio": info.get("priceToBook", 0) or 0,
                "dividend_yield": _parse_div_yield(info.get("dividendYield", 0)),
                "change": last_price - prev_close,
                "change_pct": ((last_price - prev_close) / prev_close * 100) if prev_close else 0,
            }

        last_price = info.get("regularMarketPrice", info.get("currentPrice", 0)) or 0
        prev_close = info.get("regularMarketPreviousClose", info.get("previousClose", 0)) or 0
        change = last_price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        return {
            "ticker": clean_ticker,
            "company_name": info.get("shortName", info.get("longName", clean_ticker)),
            "sector": IDX_SECTORS.get(clean_ticker, info.get("sector", "Other")),
            "last_price": last_price,
            "prev_close": prev_close,
            "open_price": info.get("regularMarketOpen", info.get("open", 0)) or 0,
            "high": info.get("regularMarketDayHigh", info.get("dayHigh", 0)) or 0,
            "low": info.get("regularMarketDayLow", info.get("dayLow", 0)) or 0,
            "volume": info.get("regularMarketVolume", info.get("volume", 0)) or 0,
            "market_cap": info.get("marketCap", 0) or 0,
            "pe_ratio": _validated_pe(info),
            "pb_ratio": info.get("priceToBook", 0) or 0,
            "dividend_yield": _parse_div_yield(info.get("dividendYield", 0)),
            "change": change,
            "change_pct": change_pct,
        }

    except Exception as e:
        return {"error": str(e), "ticker": clean_ticker}


# ── Reksadana NAV from Bareksa ──────────────────────────────────────

_nav_cache = {"data": None, "ts": 0}
_NAV_CACHE_TTL = 3600  # 1 hour


def fetch_bareksa_nav() -> list:
    """Fetch all mutual fund NAV data from Bareksa (cached 1hr)."""
    import time, json as _json, requests as _req
    now = time.time()
    if _nav_cache["data"] and (now - _nav_cache["ts"]) < _NAV_CACHE_TTL:
        return _nav_cache["data"]

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = _req.get("https://www.bareksa.com/id/data/reksadana/daftar?trans=1", headers=headers, timeout=15)
        match = re.search(r"var data = '(\[.*?\])'", r.text, re.DOTALL)
        if not match:
            return []
        data = _json.loads(match.group(1))
        _nav_cache["data"] = data
        _nav_cache["ts"] = now
        return data
    except Exception:
        return _nav_cache["data"] or []


def search_reksadana(query: str) -> list:
    """Search mutual funds by name. Returns list of {name, code, nav, nav_date, type}."""
    data = fetch_bareksa_nav()
    q = query.lower()
    results = []
    for d in data:
        name = d.get("name", "")
        code = d.get("code", "")
        if q in name.lower() or q in code.lower():
            nav = d.get("nav", {})
            results.append({
                "name": name,
                "code": code,
                "nav_value": float(nav.get("value", 0)),
                "nav_date": nav.get("date", ""),
                "type": d.get("ptype_name", ""),
                "im": d.get("im", {}).get("name", ""),
            })
    return results


def get_reksadana_nav(name: str) -> dict | None:
    """Get NAV for a specific mutual fund by exact or partial name match."""
    data = fetch_bareksa_nav()
    q = name.lower()
    # Try exact match first, then partial
    for d in data:
        if d.get("name", "").lower() == q or d.get("code", "").lower() == q:
            nav = d.get("nav", {})
            return {
                "name": d["name"],
                "code": d.get("code", ""),
                "nav_value": float(nav.get("value", 0)),
                "nav_date": nav.get("date", ""),
                "type": d.get("ptype_name", ""),
            }
    for d in data:
        if q in d.get("name", "").lower():
            nav = d.get("nav", {})
            return {
                "name": d["name"],
                "code": d.get("code", ""),
                "nav_value": float(nav.get("value", 0)),
                "nav_date": nav.get("date", ""),
                "type": d.get("ptype_name", ""),
            }
    return None


def fetch_stock_history(ticker: str, period: str = "1mo") -> list:
    """Fetch historical price data."""
    yf_ticker = get_idx_ticker(ticker)
    try:
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period=period)
        if hist.empty:
            return []

        result = []
        for date, row in hist.iterrows():
            o = _safe_val(row["Open"])
            h = _safe_val(row["High"])
            l = _safe_val(row["Low"])
            c = _safe_val(row["Close"])
            v = _safe_val(row["Volume"])
            if c is None:
                continue
            result.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(o), 2) if o is not None else 0,
                "high": round(float(h), 2) if h is not None else 0,
                "low": round(float(l), 2) if l is not None else 0,
                "close": round(float(c), 2),
                "volume": int(v) if v is not None else 0,
            })
        return result
    except Exception:
        return []


async def fetch_news_for_ticker(ticker: str) -> list:
    """Fetch news from Google News RSS for a specific ticker."""
    clean_ticker = ticker.upper().replace(".JK", "")
    query = f"{clean_ticker} saham IDX"
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

        feed = feedparser.parse(resp.text)
        news = []
        for entry in feed.entries[:10]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            source = ""
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source = entry.source.title
            elif " - " in entry.title:
                parts = entry.title.rsplit(" - ", 1)
                if len(parts) == 2:
                    source = parts[1]

            news.append({
                "ticker": clean_ticker,
                "title": entry.title,
                "link": entry.link,
                "source": source,
                "published": published or datetime.now(timezone.utc),
                "summary": getattr(entry, "summary", ""),
            })
        return news
    except Exception:
        return []


async def fetch_idx_disclosure(ticker: str = "", page: int = 0, page_size: int = 50) -> list:
    """Fetch corporate disclosures/keterbukaan informasi from IDX using curl_cffi."""
    try:
        from curl_cffi import requests as cffi_requests

        def _fetch_sync():
            session = cffi_requests.Session(impersonate="chrome")
            # Step 1: Get session cookies (bypass Cloudflare)
            session.get("https://www.idx.co.id/id", timeout=15)

            # Step 2: Fetch announcements
            url = "https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"
            params = {"indexFrom": page * page_size, "pageSize": page_size, "lang": "id"}
            if ticker:
                params["kodeEmiten"] = ticker.upper().replace(".JK", "")

            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                return []

            data = resp.json()
            replies = data.get("Replies", data.get("data", []))
            disclosures = []

            for item in replies:
                peng = item.get("pengumuman", item) if isinstance(item, dict) else {}
                attachments = item.get("attachments", [])

                link = ""
                if attachments and isinstance(attachments, list):
                    for att in attachments:
                        full_path = att.get("FullSavePath", "")
                        if full_path:
                            link = full_path
                            break

                disc_ticker = peng.get("Kode_Emiten", "").strip()
                title = peng.get("JudulPengumuman", "")
                perihal = peng.get("PerihalPengumuman", "")
                date_raw = peng.get("TglPengumuman", "")
                disc_type = peng.get("JenisPengumuman", "")

                disclosures.append({
                    "ticker": disc_ticker,
                    "title": title or perihal,
                    "date": date_raw,
                    "type": disc_type,
                    "link": link,
                })
            return disclosures

        # Run sync curl_cffi in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch_sync)
    except Exception as e:
        print(f"[DISCLOSURE ERROR] {e}")
        return []


def fetch_corporate_profile(ticker: str) -> dict:
    """Fetch detailed corporate profile from yfinance."""
    yf_ticker = get_idx_ticker(ticker)
    clean_ticker = ticker.upper().replace(".JK", "")

    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        profile = {
            "ticker": clean_ticker,
            "company_name": info.get("longName", info.get("shortName", clean_ticker)),
            "short_name": info.get("shortName", clean_ticker),
            "business_summary": info.get("longBusinessSummary", ""),
            "sector": info.get("sector", IDX_SECTORS.get(clean_ticker, "Other")),
            "industry": info.get("industry", ""),
            "website": info.get("website", ""),
            "address": info.get("address1", ""),
            "city": info.get("city", ""),
            "country": info.get("country", "Indonesia"),
            "phone": info.get("phone", ""),
            "employees": info.get("fullTimeEmployees", 0) or 0,
            "officers": [],
            "listing_date": info.get("firstTradeDateEpochUtc", ""),
        }

        # Company officers
        officers = info.get("companyOfficers", [])
        for officer in officers[:8]:
            profile["officers"].append({
                "name": officer.get("name", ""),
                "title": officer.get("title", ""),
                "age": officer.get("age", ""),
                "year_born": officer.get("yearBorn", ""),
            })

        return profile
    except Exception as e:
        return {"ticker": clean_ticker, "error": str(e)}


def fetch_ownership_data(ticker: str) -> dict:
    """Fetch institutional and major holders data."""
    yf_ticker = get_idx_ticker(ticker)
    clean_ticker = ticker.upper().replace(".JK", "")

    try:
        stock = yf.Ticker(yf_ticker)
        result = {
            "ticker": clean_ticker,
            "major_holders": [],
            "institutional_holders": [],
            "insider_holders": [],
        }

        # Major holders summary
        try:
            mh = stock.major_holders
            if mh is not None and not mh.empty:
                label_map = {
                    "insidersPercentHeld": ("Insider (Pendiri, Direksi, Komisaris)", True),
                    "institutionsPercentHeld": ("Institusi (Fund Manager, Bank, Asuransi)", True),
                    "institutionsFloatPercentHeld": ("Institusi dari Float (saham beredar)", True),
                    "institutionsCount": ("Jumlah Institusi Pemegang Saham", False),
                }
                insider_pct = 0
                inst_pct = 0
                for idx, row in mh.iterrows():
                    raw_val = row.iloc[0] if len(row) > 0 else 0
                    val = _safe_val(raw_val)
                    if val is None:
                        val = 0
                    key = str(idx)
                    label, is_pct = label_map.get(key, (key, False))
                    if key == "insidersPercentHeld":
                        insider_pct = val
                    elif key == "institutionsPercentHeld":
                        inst_pct = val
                    if is_pct:
                        display_val = f"{val * 100:.2f}%"
                    elif "Count" in key or "count" in key:
                        display_val = f"{int(val)}"
                    else:
                        display_val = str(val)
                    result["major_holders"].append({
                        "value": display_val,
                        "label": label,
                    })
                # Calculate public/retail ownership
                public_pct = max(0, 1.0 - insider_pct - inst_pct)
                result["major_holders"].insert(2, {
                    "value": f"{public_pct * 100:.2f}%",
                    "label": "Masyarakat / Publik (Ritel)",
                })
        except Exception:
            pass

        # Institutional holders
        try:
            ih = stock.institutional_holders
            if ih is not None and not ih.empty:
                for _, row in ih.iterrows():
                    holder = {}
                    for col in ih.columns:
                        val = row[col]
                        if hasattr(val, 'isoformat'):
                            val = val.isoformat()
                        else:
                            val = _safe_val(val)
                        holder[col] = val
                    result["institutional_holders"].append(holder)
        except Exception:
            pass

        # Insider/mutualfund holders
        try:
            mfh = stock.mutualfund_holders
            if mfh is not None and not mfh.empty:
                for _, row in mfh.iterrows():
                    holder = {}
                    for col in mfh.columns:
                        val = row[col]
                        if hasattr(val, 'isoformat'):
                            val = val.isoformat()
                        else:
                            val = _safe_val(val)
                        holder[col] = val
                    result["insider_holders"].append(holder)
        except Exception:
            pass

        return result
    except Exception as e:
        return {"ticker": clean_ticker, "error": str(e)}


def _tv_get(d: dict, key: str, default=0):
    """Safely get a value from TradingView data dict."""
    val = d.get(key)
    if val is None:
        return default
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return default
    return val


def _fetch_tradingview_financials(ticker: str) -> dict | None:
    """Fetch financial data from TradingView scanner API."""
    symbol = f"IDX:{ticker.upper().replace('.JK', '')}"

    # TradingView scanner fields for fundamental data
    fields = [
        # Income Statement
        "total_revenue", "gross_profit", "net_income",
        "total_revenue_yoy_growth_ttm", "net_income_yoy_growth_ttm",
        "earnings_per_share_basic_ttm", "earnings_per_share_diluted_ttm",
        "earnings_per_share_fq", "revenue_per_share_ttm",
        "ebitda", "gross_margin", "operating_margin",
        "pre_tax_margin", "net_margin", "free_cash_flow_margin_ttm",
        # Balance Sheet
        "total_assets", "total_debt", "total_current_assets",
        "book_value_per_share_fq", "total_shares_outstanding",
        "float_shares_outstanding",
        # Cash Flow
        "free_cash_flow",
        # Valuation
        "price_earnings_ttm", "price_earnings_growth_ttm",
        "price_book_fq", "price_revenue_ttm",
        "enterprise_value_ebitda_ttm", "enterprise_value_fq",
        # Returns & Ratios
        "return_on_equity", "return_on_assets", "return_on_invested_capital",
        "debt_to_equity", "current_ratio", "quick_ratio",
        # Dividends
        "dividends_yield", "dividends_per_share_fq",
        # Technical
        "beta_1_year", "price_52_week_high", "price_52_week_low",
        "EMA50", "EMA200", "average_volume_10d_calc",
        # Quarterly
        "total_revenue_fq", "gross_profit_fq",
        "net_income_fq", "ebitda_fq",
        "total_revenue_qoq_growth_fq", "net_income_qoq_growth_fq",
        "total_assets_fq", "total_debt_fq",
        "total_revenue_yoy_growth_fq", "net_income_yoy_growth_fq",
        # TTM
        "total_revenue_ttm", "gross_profit_ttm", "oper_income_ttm",
        "net_income_ttm", "ebitda_ttm",
        # Annual (FY)
        "total_revenue_fy", "gross_profit_fy", "net_income_fy", "ebitda_fy",
        "total_revenue_yoy_growth_fy", "net_income_yoy_growth_fy",
        "gross_profit_margin_fy", "net_margin_fy", "operating_margin_fy",
        "earnings_per_share_basic_fy", "earnings_per_share_diluted_fy",
        # Additional
        "market_cap_basic", "number_of_employees",
        "after_tax_margin",
    ]

    try:
        url = "https://scanner.tradingview.com/indonesia/scan"
        payload = {
            "symbols": {"tickers": [symbol]},
            "columns": fields,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("data") or len(data["data"]) == 0:
            return None
        # Map column values to field names
        values = data["data"][0].get("d", [])
        result = {}
        for i, field in enumerate(fields):
            if i < len(values):
                result[field] = values[i]
        return result
    except Exception:
        return None


def fetch_financials(ticker: str) -> dict:
    """Fetch key financial data from TradingView (primary) with yfinance fallback."""
    clean_ticker = ticker.upper().replace(".JK", "")

    # Try TradingView first
    tv = _fetch_tradingview_financials(clean_ticker)
    if tv:
        financials = {
            "ticker": clean_ticker,
            "source": "tradingview",
            # Income Statement
            "revenue": _tv_get(tv, "total_revenue_ttm") or _tv_get(tv, "total_revenue"),
            "gross_profit": _tv_get(tv, "gross_profit_ttm") or _tv_get(tv, "gross_profit"),
            "ebitda": _tv_get(tv, "ebitda_ttm") or _tv_get(tv, "ebitda"),
            "operating_income": _tv_get(tv, "oper_income_ttm"),
            "net_income": _tv_get(tv, "net_income_ttm") or _tv_get(tv, "net_income"),
            # Balance Sheet
            "total_assets": _tv_get(tv, "total_assets"),
            "total_debt": _tv_get(tv, "total_debt"),
            "total_cash": 0,
            "total_current_assets": _tv_get(tv, "total_current_assets"),
            "total_current_liabilities": 0,
            # Cash Flow
            "free_cashflow": _tv_get(tv, "free_cash_flow"),
            "operating_cashflow": 0,
            "capital_expenditures": 0,
            # Valuation
            "pe_trailing": _tv_get(tv, "price_earnings_ttm"),
            "peg_ratio": _tv_get(tv, "price_earnings_growth_ttm"),
            "pb_ratio": _tv_get(tv, "price_book_fq"),
            "ps_ratio": _tv_get(tv, "price_revenue_ttm"),
            "ev_ebitda": _tv_get(tv, "enterprise_value_ebitda_ttm"),
            "enterprise_value": _tv_get(tv, "enterprise_value_fq"),
            "market_cap": _tv_get(tv, "market_cap_basic"),
            # Margins
            "gross_margin": _tv_get(tv, "gross_margin"),
            "operating_margin": _tv_get(tv, "operating_margin"),
            "profit_margin": _tv_get(tv, "net_margin"),
            "pretax_margin": _tv_get(tv, "pre_tax_margin"),
            "fcf_margin": _tv_get(tv, "free_cash_flow_margin_ttm"),
            # Returns
            "roe": _tv_get(tv, "return_on_equity"),
            "roa": _tv_get(tv, "return_on_assets"),
            "roic": _tv_get(tv, "return_on_invested_capital"),
            # Ratios
            "debt_to_equity": _tv_get(tv, "debt_to_equity"),
            "current_ratio": _tv_get(tv, "current_ratio"),
            "quick_ratio": _tv_get(tv, "quick_ratio"),
            # Per Share
            "eps_trailing": _tv_get(tv, "earnings_per_share_basic_ttm"),
            "eps_diluted": _tv_get(tv, "earnings_per_share_diluted_ttm"),
            "eps_quarterly": _tv_get(tv, "earnings_per_share_fq"),
            "book_value": _tv_get(tv, "book_value_per_share_fq"),
            "revenue_per_share": _tv_get(tv, "revenue_per_share_ttm"),
            # Growth
            "revenue_growth": _tv_get(tv, "total_revenue_yoy_growth_ttm"),
            "earnings_growth": _tv_get(tv, "net_income_yoy_growth_ttm"),
            "revenue_growth_qoq": _tv_get(tv, "total_revenue_qoq_growth_fq"),
            "earnings_growth_qoq": _tv_get(tv, "net_income_qoq_growth_fq"),
            # Dividends
            "dividend_yield": _tv_get(tv, "dividends_yield"),
            "dividend_per_share": _tv_get(tv, "dividends_per_share_fq"),
            "payout_ratio": 0,
            # Technical
            "beta": _tv_get(tv, "beta_1_year"),
            "fifty_two_week_high": _tv_get(tv, "price_52_week_high"),
            "fifty_two_week_low": _tv_get(tv, "price_52_week_low"),
            "fifty_day_avg": _tv_get(tv, "EMA50"),
            "two_hundred_day_avg": _tv_get(tv, "EMA200"),
            "avg_volume_10d": _tv_get(tv, "average_volume_10d_calc"),
            # Shares
            "shares_outstanding": _tv_get(tv, "total_shares_outstanding"),
            "float_shares": _tv_get(tv, "float_shares_outstanding"),
            "employees": _tv_get(tv, "number_of_employees"),
            # Quarterly snapshot (latest)
            "quarterly_revenue": _tv_get(tv, "total_revenue_fq"),
            "quarterly_gross_profit": _tv_get(tv, "gross_profit_fq"),
            "quarterly_operating_income": 0,
            "quarterly_net_income": _tv_get(tv, "net_income_fq"),
            "quarterly_ebitda": _tv_get(tv, "ebitda_fq"),
            "quarterly_total_assets": _tv_get(tv, "total_assets_fq"),
            "quarterly_total_debt": _tv_get(tv, "total_debt_fq"),
            "quarterly_revenue_yoy": _tv_get(tv, "total_revenue_yoy_growth_fq"),
            "quarterly_earnings_yoy": _tv_get(tv, "net_income_yoy_growth_fq"),
            # Annual (FY)
            "annual_revenue": _tv_get(tv, "total_revenue_fy"),
            "annual_gross_profit": _tv_get(tv, "gross_profit_fy"),
            "annual_net_income": _tv_get(tv, "net_income_fy"),
            "annual_ebitda": _tv_get(tv, "ebitda_fy"),
            "annual_revenue_growth": _tv_get(tv, "total_revenue_yoy_growth_fy"),
            "annual_earnings_growth": _tv_get(tv, "net_income_yoy_growth_fy"),
            "annual_gross_margin": _tv_get(tv, "gross_profit_margin_fy"),
            "annual_net_margin": _tv_get(tv, "net_margin_fy"),
            "annual_operating_margin": _tv_get(tv, "operating_margin_fy"),
            "annual_eps": _tv_get(tv, "earnings_per_share_basic_fy"),
            "annual_eps_diluted": _tv_get(tv, "earnings_per_share_diluted_fy"),
            # Backward compat fields
            "pe_forward": 0,
            "dividend_rate": _tv_get(tv, "dividends_per_share_fq"),
        }

        # Convert TradingView percentage values (they come as decimals 0.xx)
        for key in ["gross_margin", "operating_margin", "profit_margin",
                     "pretax_margin", "fcf_margin", "roe", "roa", "roic",
                     "revenue_growth", "earnings_growth",
                     "revenue_growth_qoq", "earnings_growth_qoq",
                     "dividend_yield", "payout_ratio"]:
            val = financials.get(key, 0)
            if val and abs(val) < 5:  # likely decimal form
                financials[key] = val  # keep as-is, frontend handles both

        return financials

    # Fallback to yfinance
    yf_ticker = get_idx_ticker(ticker)
    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        financials = {
            "ticker": clean_ticker,
            "source": "yfinance",
            "revenue": info.get("totalRevenue", 0) or 0,
            "gross_profit": info.get("grossProfits", 0) or 0,
            "ebitda": info.get("ebitda", 0) or 0,
            "operating_income": 0,
            "net_income": info.get("netIncomeToCommon", 0) or 0,
            "total_assets": info.get("totalAssets", 0) or 0,
            "total_debt": info.get("totalDebt", 0) or 0,
            "total_cash": info.get("totalCash", 0) or 0,
            "total_current_assets": 0,
            "total_current_liabilities": 0,
            "free_cashflow": info.get("freeCashflow", 0) or 0,
            "operating_cashflow": info.get("operatingCashflow", 0) or 0,
            "capital_expenditures": 0,
            "book_value": info.get("bookValue", 0) or 0,
            "eps_trailing": _validated_eps(info),
            "eps_diluted": 0,
            "eps_quarterly": 0,
            "revenue_per_share": 0,
            "pe_trailing": _validated_pe(info),
            "pe_forward": _validated_pe_forward(info),
            "peg_ratio": info.get("pegRatio", 0) or 0,
            "pb_ratio": 0,
            "ps_ratio": 0,
            "ev_ebitda": 0,
            "enterprise_value": 0,
            "market_cap": 0,
            "gross_margin": (info.get("profitMargins", 0) or 0),
            "operating_margin": (info.get("operatingMargins", 0) or 0),
            "profit_margin": (info.get("profitMargins", 0) or 0),
            "pretax_margin": 0,
            "fcf_margin": 0,
            "roe": (info.get("returnOnEquity", 0) or 0),
            "roa": (info.get("returnOnAssets", 0) or 0),
            "roic": 0,
            "debt_to_equity": info.get("debtToEquity", 0) or 0,
            "current_ratio": info.get("currentRatio", 0) or 0,
            "quick_ratio": info.get("quickRatio", 0) or 0,
            "revenue_growth": (info.get("revenueGrowth", 0) or 0),
            "earnings_growth": (info.get("earningsGrowth", 0) or 0),
            "revenue_growth_qoq": 0,
            "earnings_growth_qoq": 0,
            "dividend_yield": _parse_div_yield(info.get("dividendYield")),
            "dividend_per_share": 0,
            "dividend_rate": info.get("dividendRate", 0) or 0,
            "payout_ratio": (info.get("payoutRatio", 0) or 0),
            "beta": info.get("beta", 0) or 0,
            "shares_outstanding": info.get("sharesOutstanding", 0) or 0,
            "float_shares": info.get("floatShares", 0) or 0,
            "employees": 0,
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0) or 0,
            "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0) or 0,
            "fifty_day_avg": info.get("fiftyDayAverage", 0) or 0,
            "two_hundred_day_avg": info.get("twoHundredDayAverage", 0) or 0,
            "avg_volume_10d": info.get("averageDailyVolume10Day", 0) or 0,
            "quarterly_revenue": 0,
            "quarterly_gross_profit": 0,
            "quarterly_operating_income": 0,
            "quarterly_net_income": 0,
            "quarterly_ebitda": 0,
            "quarterly_total_assets": 0,
            "quarterly_total_debt": 0,
            "quarterly_revenue_yoy": 0,
            "quarterly_earnings_yoy": 0,
            "annual_revenue": 0,
            "annual_gross_profit": 0,
            "annual_net_income": 0,
            "annual_ebitda": 0,
            "annual_revenue_growth": 0,
            "annual_earnings_growth": 0,
            "annual_gross_margin": 0,
            "annual_net_margin": 0,
            "annual_operating_margin": 0,
            "annual_eps": 0,
            "annual_eps_diluted": 0,
        }
        return financials
    except Exception as e:
        return {"ticker": clean_ticker, "error": str(e)}


def fetch_financial_statements(ticker: str, num_quarters: int = 8) -> dict:
    """Fetch quarterly financial statement data (Income Statement, Balance Sheet, Cash Flow)
    from TradingView using _fq_h (fiscal quarter historical) fields.
    Returns up to num_quarters of data, most recent first."""
    clean_ticker = ticker.upper().replace(".JK", "")
    symbol = f"IDX:{clean_ticker}"

    fields = [
        "total_revenue_fq_h",
        "gross_profit_fq_h",
        "net_income_fq_h",
        "ebitda_fq_h",
        "earnings_per_share_diluted_fq_h",
        "total_assets_fq_h",
        "total_debt_fq_h",
        "free_cash_flow_fq_h",
    ]
    field_keys = [
        "revenue", "gross_profit", "net_income", "ebitda",
        "eps", "total_assets", "total_debt", "free_cash_flow",
    ]

    try:
        url = "https://scanner.tradingview.com/indonesia/scan"
        payload = {
            "symbols": {"tickers": [symbol]},
            "columns": fields,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            return {"ticker": clean_ticker, "quarters": [], "error": "TradingView unavailable"}

        data = resp.json()
        if not data.get("data") or len(data["data"]) == 0:
            return {"ticker": clean_ticker, "quarters": [], "error": "No data"}

        values = data["data"][0].get("d", [])
        raw = {}
        for i, key in enumerate(field_keys):
            arr = values[i] if i < len(values) else None
            if isinstance(arr, list):
                raw[key] = arr[:num_quarters]
            else:
                raw[key] = []

        # Determine quarter labels: most recent quarter first, going backwards
        # We use current date to estimate. Indonesian companies typically report Dec FY.
        from datetime import datetime
        now = datetime.now()
        # Most recent quarter end: work backwards from current date
        q_month = ((now.month - 1) // 3) * 3  # 0,3,6,9
        q_year = now.year
        if q_month == 0:
            q_month = 12
            q_year -= 1

        labels = []
        m, y = q_month, q_year
        for _ in range(num_quarters):
            q_num = m // 3  # 3->Q1, 6->Q2, 9->Q3, 12->Q4
            labels.append(f"Q{q_num}'{str(y)[2:]}")
            m -= 3
            if m <= 0:
                m += 12
                y -= 1

        # Build quarters array
        count = min(num_quarters, max(len(v) for v in raw.values()) if raw.values() else 0)
        quarters = []
        for i in range(count):
            q = {"label": labels[i] if i < len(labels) else f"Q-{i+1}"}
            for key in field_keys:
                arr = raw.get(key, [])
                val = arr[i] if i < len(arr) else None
                if val is not None and isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    val = None
                q[key] = val
            # Derive operating income = gross_profit - (revenue - gross_profit is wrong)
            # Derive: operating_income ≈ ebitda (approximation since we don't have it separately)
            # Derive: gross_margin, net_margin
            rev = q.get("revenue")
            gp = q.get("gross_profit")
            ni = q.get("net_income")
            if rev and gp:
                q["gross_margin"] = round(gp / rev * 100, 2)
            else:
                q["gross_margin"] = None
            if rev and ni:
                q["net_margin"] = round(ni / rev * 100, 2)
            else:
                q["net_margin"] = None
            # Derive equity = total_assets - total_debt (rough approximation)
            ta = q.get("total_assets")
            td = q.get("total_debt")
            if ta and td:
                q["total_equity"] = ta - td
            else:
                q["total_equity"] = None
            quarters.append(q)

        return {
            "ticker": clean_ticker,
            "source": "tradingview",
            "quarters": quarters,
        }
    except Exception as e:
        return {"ticker": clean_ticker, "quarters": [], "error": str(e)}


async def fetch_market_summary() -> dict:
    """Fetch IHSG and market summary."""
    try:
        ihsg = yf.Ticker("^JKSE")
        info = ihsg.info
        hist = ihsg.history(period="2d")

        if not hist.empty:
            last = float(hist.iloc[-1]["Close"])
            prev = float(hist.iloc[-2]["Close"]) if len(hist) > 1 else last
            return {
                "ihsg": last,
                "ihsg_change": last - prev,
                "ihsg_change_pct": ((last - prev) / prev * 100) if prev else 0,
                "ihsg_volume": int(hist.iloc[-1].get("Volume", 0)),
            }
        return {"ihsg": 0, "ihsg_change": 0, "ihsg_change_pct": 0, "ihsg_volume": 0}
    except Exception:
        return {"ihsg": 0, "ihsg_change": 0, "ihsg_change_pct": 0, "ihsg_volume": 0}
