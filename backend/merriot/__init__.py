"""Merriot — thesis tracker bot embedded in Portico.

Captures stock thesis notes via Telegram (LLM-extracted structure +
smart reminder dates), shares Portico SQLite DB so notes are also
visible in the web Thesis tab.
"""
from backend.merriot.bot import start_bot, stop_bot
from backend.merriot.reminders import register_cron
from backend.merriot.routes import router

__all__ = ["start_bot", "stop_bot", "register_cron", "router"]
