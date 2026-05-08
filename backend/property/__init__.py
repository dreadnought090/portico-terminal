"""Property — rental property tracker bot embedded in Portico.

Telegram bot for managing rental income/expenses across owned units.
Backend storage: per-year Excel workbooks at backend/property/data/.
"""
from backend.property.bot import start_bot, stop_bot
from backend.property.reminders import register_cron

__all__ = ["start_bot", "stop_bot", "register_cron"]
