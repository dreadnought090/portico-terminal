"""IDX Pulse Pro subscription system — Telegram Stars payment + auto-invite.

Public API:
    start_bot()     — boot the polling loop (call from app.py lifespan)
    stop_bot()      — graceful shutdown
    register_cron(scheduler) — wire expiry + reminder + feedback-digest jobs

DB models live in backend.models (Subscriber, Payment, Feedback).
"""
from backend.subscription.bot import start_bot, stop_bot
from backend.subscription.cron import register_cron

__all__ = ["start_bot", "stop_bot", "register_cron"]
