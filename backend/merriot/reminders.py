"""Merriot reminder cron — daily 07:30 WIB scan + triple-pattern delivery.

Scans ThesisNote with status=pending, computes (review_at - today) in days,
maps to {7→H-7, 1→H-1, ≤0→H+0}. Skips kinds already in ThesisReminderLog.
"""
from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.database import SessionLocal
from backend.merriot import bot as merriot_bot
from backend.merriot import config, storage, templates

logger = logging.getLogger("merriot.reminders")


def _kind_buttons(kind: str, note_id: int) -> InlineKeyboardMarkup:
    if kind == "H+0":
        # Full set on day-of
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Reviewed", callback_data=f"rev:{note_id}"),
                InlineKeyboardButton("⏰ +7d", callback_data=f"pp7:{note_id}"),
            ],
            [
                InlineKeyboardButton("📝 Update", callback_data=f"upd:{note_id}"),
                InlineKeyboardButton("💀 Invalid", callback_data=f"inv:{note_id}"),
            ],
        ])
    # H-7 / H-1 — light
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Reviewed", callback_data=f"rev:{note_id}"),
        InlineKeyboardButton("⏰ +7d", callback_data=f"pp7:{note_id}"),
    ]])


def _format_for_kind(note, kind: str) -> str:
    if kind == "H-7":
        return templates.fmt_reminder_h7(note)
    if kind == "H-1":
        return templates.fmt_reminder_h1(note)
    return templates.fmt_reminder_h0(note)


async def _send(bot, chat_id: int, text: str, markup, note_id: int | None = None) -> bool:
    if config.dry_run():
        # Redact thesis content; only log identifiers (logs may end up on disk).
        logger.info("[DRY] →%s note=%s len=%d", chat_id, note_id, len(text))
        return True
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return True
    except Exception:
        logger.exception("send_message failed")
        return False


async def scan_and_send() -> dict:
    """Cron entry. Returns summary dict for observability."""
    if not config.is_configured():
        return {"status": "unconfigured", "sent": 0}

    app = merriot_bot.get_app()
    if app is None and not config.dry_run():
        logger.warning("Merriot bot not running — reminder cron skipped")
        return {"status": "bot_down", "sent": 0}

    db = SessionLocal()
    try:
        pairs = storage.needs_reminders_today(db)
    finally:
        db.close()

    if not pairs:
        return {"status": "ok", "sent": 0, "checked": 0}

    admin = config.admin_chat_id()
    sent_count = 0
    bot = app.bot if app else None

    # Reuse one session for all log writes — saves N session open/close cycles.
    log_db = SessionLocal()
    try:
        for note, kind in pairs:
            text = _format_for_kind(note, kind)
            markup = _kind_buttons(kind, note.id)
            ok = await _send(bot, admin, text, markup, note_id=note.id)
            if ok:
                storage.log_reminder_sent(log_db, note.id, kind)
                sent_count += 1
            await asyncio.sleep(0.3)  # gentle rate-limit between sends
    finally:
        log_db.close()

    logger.info("Merriot reminders sent: %d / %d", sent_count, len(pairs))
    return {"status": "ok", "sent": sent_count, "checked": len(pairs)}


def register_cron(scheduler) -> None:
    """Wire daily reminder scan into APScheduler. Pin to WIB explicitly so the
    job doesn't drift if the host TZ is wrong (containers/CI default to UTC)."""
    hour = config.reminder_hour()
    minute = config.reminder_minute()
    scheduler.add_job(
        scan_and_send, "cron",
        hour=hour, minute=minute,
        timezone=config.WIB,  # pin to WIB regardless of system TZ
        id="merriot_reminders",
        misfire_grace_time=3600,  # if Mac was asleep at 07:30, fire on wake within 1h
        coalesce=True,
        max_instances=1,
    )
    logger.info("Merriot reminder cron registered at %02d:%02d WIB daily", hour, minute)
