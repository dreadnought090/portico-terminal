"""
TradingView Historical Quarterly Financial Data Fetcher for Indonesian Stocks (IDX)

Uses two TradingView endpoints:
1. Scanner API (REST) at https://scanner.tradingview.com/indonesia/scan
   - Returns historical arrays via fields with the `_fq_h` suffix
   - Available fields: total_revenue, gross_profit, net_income, ebitda,
     earnings_per_share_diluted, total_assets, total_debt, free_cash_flow

2. WebSocket Quote Session at wss://data.tradingview.com/socket.io/websocket
   - Returns period labels (e.g., '2025-Q4') via `fiscal_period_fq_h`
   - Returns earnings release dates via `earnings_release_date_fq_h`

The `_fq_h` suffix means: fiscal quarter, historical array.
Data is returned as arrays ordered from most recent quarter (index 0) to oldest.
Typically returns up to 32 quarters (8 years) of data.

No authentication required.
"""

import requests
import websocket
import json
import random
import string
import time
from datetime import datetime


# =============================================================================
# 1. REST API: Get financial data arrays
# =============================================================================

def get_financial_data_rest(symbol: str, market: str = "indonesia") -> dict:
    """
    Fetch historical quarterly financial data via TradingView Scanner REST API.

    Args:
        symbol: TradingView symbol, e.g. "IDX:INKP"
        market: Scanner market endpoint, e.g. "indonesia", "global", "america"

    Returns:
        Dict mapping field names to lists of quarterly values (most recent first).
    """
    url = f"https://scanner.tradingview.com/{market}/scan"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
    }

    # Historical quarterly financial fields (append _fq_h to base field name)
    columns = [
        # Income Statement
        "total_revenue_fq_h",
        "gross_profit_fq_h",
        "net_income_fq_h",
        "ebitda_fq_h",
        "earnings_per_share_diluted_fq_h",
        # Balance Sheet
        "total_assets_fq_h",
        "total_debt_fq_h",
        # Cash Flow
        "free_cash_flow_fq_h",
    ]

    payload = {
        "symbols": {"tickers": [symbol]},
        "columns": columns,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    result = resp.json()

    if not result.get("data"):
        raise ValueError(f"No data returned for {symbol}: {result}")

    values = result["data"][0]["d"]
    return {col: val for col, val in zip(columns, values)}


# =============================================================================
# 2. WebSocket: Get period labels and additional metadata
# =============================================================================

def _ws_gen_session():
    return "qs_" + "".join(random.choices(string.ascii_lowercase, k=12))


def _ws_send(ws, func, args):
    msg = json.dumps({"m": func, "p": args})
    ws.send(f"~m~{len(msg)}~m~{msg}")


def _ws_parse(raw):
    msgs = []
    parts = raw.split("~m~")
    i = 0
    while i < len(parts):
        if parts[i] == "":
            i += 1
            continue
        try:
            int(parts[i])
            i += 1
            if i < len(parts):
                msgs.append(parts[i])
            i += 1
        except ValueError:
            i += 1
    return msgs


def get_period_labels_ws(symbol: str) -> dict:
    """
    Fetch quarter labels and earnings dates via TradingView WebSocket.

    Returns dict with:
        - fiscal_period_fq_h: list of period labels like ['2025-Q4', '2025-Q3', ...]
        - earnings_release_date_fq_h: list of unix timestamps
        - earnings_fiscal_period_fq_h: list of period labels (may be shorter)
    """
    ws = websocket.create_connection(
        "wss://data.tradingview.com/socket.io/websocket",
        origin="https://www.tradingview.com",
        header=["User-Agent: Mozilla/5.0"],
    )
    ws.recv()  # initial handshake

    _ws_send(ws, "set_auth_token", ["unauthorized_user_token"])

    session = _ws_gen_session()
    _ws_send(ws, "quote_create_session", [session])
    _ws_send(ws, "quote_set_fields", [session,
        "fiscal_period_fq_h",
        "earnings_fiscal_period_fq_h",
        "earnings_release_date_fq_h",
        "fiscal_period_fy",
    ])
    _ws_send(ws, "quote_add_symbols", [session, symbol])

    all_fields = {}
    deadline = time.time() + 8
    while time.time() < deadline:
        ws.settimeout(3)
        try:
            raw = ws.recv()
            if "~h~" in raw:
                ws.send(raw)  # heartbeat
                continue
            for m in _ws_parse(raw):
                try:
                    d = json.loads(m)
                    if d.get("m") == "qsd":
                        v = d["p"][1].get("v", {})
                        all_fields.update(v)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        except (websocket.WebSocketTimeoutException, Exception):
            break

    ws.close()
    return all_fields


# =============================================================================
# 3. Combined: Pretty-print quarterly financial statements
# =============================================================================

def get_quarterly_financials(symbol: str, num_quarters: int = 8, market: str = "indonesia"):
    """
    Get historical quarterly financial data with period labels.

    Args:
        symbol: e.g. "IDX:INKP"
        num_quarters: Number of most recent quarters to return (max ~32)
        market: Scanner market endpoint

    Returns:
        List of dicts, one per quarter, ordered most recent first.
    """
    # Fetch data and labels in parallel-ish
    fin_data = get_financial_data_rest(symbol, market)
    ws_data = get_period_labels_ws(symbol)

    periods = ws_data.get("fiscal_period_fq_h", [])
    release_dates = ws_data.get("earnings_release_date_fq_h", [])

    n = min(num_quarters, len(periods), 32)

    # Field name mapping for display
    field_display = {
        "total_revenue_fq_h": "Total Revenue",
        "gross_profit_fq_h": "Gross Profit",
        "net_income_fq_h": "Net Income",
        "ebitda_fq_h": "EBITDA",
        "earnings_per_share_diluted_fq_h": "EPS (Diluted)",
        "total_assets_fq_h": "Total Assets",
        "total_debt_fq_h": "Total Debt",
        "free_cash_flow_fq_h": "Free Cash Flow",
    }

    quarters = []
    for i in range(n):
        q = {
            "period": periods[i] if i < len(periods) else f"Q-{i}",
            "earnings_release_date": (
                datetime.fromtimestamp(release_dates[i]).strftime("%Y-%m-%d")
                if i < len(release_dates) and release_dates[i]
                else None
            ),
        }
        for field, display_name in field_display.items():
            arr = fin_data.get(field) or []
            q[display_name] = arr[i] if isinstance(arr, list) and i < len(arr) else None
        quarters.append(q)

    return quarters


def format_number(val):
    """Format large numbers in trillions/billions for IDR."""
    if val is None:
        return "N/A"
    if isinstance(val, str):
        return val
    abs_val = abs(val)
    sign = "-" if val < 0 else ""
    if abs_val >= 1e12:
        return f"{sign}{abs_val/1e12:.2f}T"
    elif abs_val >= 1e9:
        return f"{sign}{abs_val/1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val/1e6:.2f}M"
    else:
        return f"{sign}{abs_val:,.2f}"


def print_financials(symbol: str, num_quarters: int = 8, market: str = "indonesia"):
    """Print a formatted table of quarterly financials."""
    quarters = get_quarterly_financials(symbol, num_quarters, market)

    if not quarters:
        print(f"No data available for {symbol}")
        return

    print(f"\n{'='*80}")
    print(f"  Quarterly Financial Data: {symbol}")
    print(f"  {len(quarters)} most recent quarters")
    print(f"{'='*80}\n")

    # Print header
    header_fields = [
        "Total Revenue", "Gross Profit", "Net Income", "EBITDA",
        "EPS (Diluted)", "Total Assets", "Total Debt", "Free Cash Flow",
    ]

    for q in quarters:
        period = q["period"]
        release = q.get("earnings_release_date", "")
        print(f"--- {period} (released: {release or 'N/A'}) ---")
        for field in header_fields:
            val = q.get(field)
            if field == "EPS (Diluted)":
                formatted = f"IDR {val:,.2f}" if val is not None else "N/A"
            else:
                formatted = f"IDR {format_number(val)}"
            print(f"  {field:25s} {formatted}")
        print()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else "IDX:INKP"
    num_q = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    print_financials(symbol, num_q)

    # Also demonstrate raw data access
    print("\n" + "=" * 80)
    print("  Raw API Demo")
    print("=" * 80)

    print("\n1. Scanner REST API request:")
    print(f'   POST https://scanner.tradingview.com/indonesia/scan')
    print(f'   Body: {{"symbols": {{"tickers": ["{symbol}"]}},')
    print(f'          "columns": ["total_revenue_fq_h", "net_income_fq_h", ...]}}')

    print("\n2. WebSocket quote session for period labels:")
    print(f'   Connect: wss://data.tradingview.com/socket.io/websocket')
    print(f'   Fields: fiscal_period_fq_h, earnings_release_date_fq_h')

    print("\n3. Available _fq_h fields for Indonesia:")
    fields = [
        "total_revenue_fq_h", "gross_profit_fq_h", "net_income_fq_h",
        "ebitda_fq_h", "earnings_per_share_diluted_fq_h",
        "total_assets_fq_h", "total_debt_fq_h", "free_cash_flow_fq_h",
    ]
    for f in fields:
        print(f"   - {f}")

    print("\n4. Also available with _fy_h suffix (annual data):")
    print("   - total_revenue_fy_h (20 years)")
    print("   - gross_profit_fy_h, net_income_fy_h, ebitda_fy_h, etc.")
