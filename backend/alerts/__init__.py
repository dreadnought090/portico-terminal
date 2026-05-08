"""Alerts — price-cross alerts, embedded in Merriot bot.

Independent code from backend/merriot/. Reuses Merriot's Telegram bot and
Portico APScheduler. PriceAlert table has no FK to ThesisNote.
"""
from backend.alerts.cron import register_cron, scan_and_evaluate
from backend.alerts.handlers import register_handlers
from backend.alerts.routes import router

__all__ = ["register_cron", "register_handlers", "router", "scan_and_evaluate"]
