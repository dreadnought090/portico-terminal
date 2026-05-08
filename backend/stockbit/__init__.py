"""StockBit integration — per-ticker broker summary (Bandar Detector).

ENV-GATED: only activates if STOCKBIT_EMAIL + STOCKBIT_PASSWORD are set.
Falls back gracefully to existing /api/idx/broker-summary (market-wide).

Exposed:
- is_configured() — bool
- fetch_broker_summary(ticker, date=None) — async, returns dict|None
"""
from backend.stockbit.client import is_configured
from backend.stockbit.broker_summary import fetch_broker_summary

__all__ = ["is_configured", "fetch_broker_summary"]
