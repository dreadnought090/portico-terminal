"""Alert cron — scan armed alerts every 5 min during market hours.

Fetches per-ticker prices via idx_native.fetch_trading_info_daily, evaluates,
fires Telegram notification on cross. One-shot — alert becomes 'triggered'.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.database import SessionLocal
from backend.alerts import config, storage, templates

logger = logging.getLogger("alerts.cron")


def _trigger_buttons(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Done", callback_data=f"adone:{alert_id}"),
    ]])


def _get_bot():
    """Lazy import to avoid circular load. Returns None if Merriot not ready."""
    try:
        from backend.merriot import bot as merriot_bot
        app = merriot_bot.get_app()
        return app.bot if app else None
    except Exception:
        return None


async def _send_notification(bot, chat_id: int, text: str, alert_id: int) -> bool:
    if config.dry_run():
        logger.info("[DRY] alert#%d → chat=%d text-len=%d", alert_id, chat_id, len(text))
        return True
    if bot is None:
        logger.warning("alert#%d: bot down, will retry next cycle", alert_id)
        return False
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=_trigger_buttons(alert_id),
        )
        return True
    except Exception:
        logger.exception("send failed alert#%d", alert_id)
        return False


async def _fetch_prices(tickers: list[str]) -> dict[str, dict | None]:
    """Concurrent fetch with semaphore=5. Returns {ticker: snap_dict | None}."""
    from backend.idx_native import fetch_trading_info_daily

    sem = asyncio.Semaphore(5)

    async def _one(t: str):
        async with sem:
            try:
                return t, await fetch_trading_info_daily(t)
            except Exception as e:
                logger.warning("fetch %s failed: %s", t, e)
                return t, None

    results = await asyncio.gather(*[_one(t) for t in tickers])
    return dict(results)


async def scan_and_evaluate() -> dict:
    """Cron entry. Returns {checked, triggered, errors} for observability."""
    db = SessionLocal()
    try:
        armed = storage.list_armed(db)
        unique_tickers = list({a.ticker for a in armed})
    finally:
        db.close()

    if not armed:
        return {"checked": 0, "triggered": 0, "errors": 0}
    if not unique_tickers:
        return {"checked": 0, "triggered": 0, "errors": 0}

    # Cycle timeout safety — never run longer than 2 min
    try:
        prices = await asyncio.wait_for(
            _fetch_prices(unique_tickers), timeout=120
        )
    except asyncio.TimeoutError:
        logger.error("alert cycle timed out fetching prices")
        return {"checked": 0, "triggered": 0, "errors": len(unique_tickers)}

    # Phase 1: evaluate which alerts SHOULD trigger (cross-event detection).
    # Fire ONLY when price crosses threshold from "wrong" side to "right" side.
    # Prev_price > threshold and current <= threshold (for below alerts) = cross down.
    # Prev_price < threshold and current >= threshold (for above alerts) = cross up.
    # First check (last_checked_at = None) → fire if currently past threshold.
    pending_triggers: list[tuple] = []  # (alert_id, current_price, snap)
    errors = 0

    db = SessionLocal()
    try:
        from backend.models import PriceAlert
        fresh_alerts = (
            db.query(PriceAlert)
            .filter(PriceAlert.status == "armed",
                    PriceAlert.id.in_([a.id for a in armed]))
            .all()
        )
        for a in fresh_alerts:
            snap = prices.get(a.ticker)
            if snap is None:
                errors += 1
                continue
            current = snap.get("close") or 0
            if not current:
                errors += 1
                continue
            prev = float(a.last_check_price or 0)
            # Update tracker
            a.last_check_price = float(current)
            from datetime import datetime, timezone as _tz
            a.last_checked_at = datetime.now(_tz.utc)
            # Cross detection
            should_fire = False
            if a.direction == "above":
                if prev == 0:  # first check
                    should_fire = current >= a.threshold_price
                else:
                    should_fire = prev < a.threshold_price <= current
            elif a.direction == "below":
                if prev == 0:
                    should_fire = current <= a.threshold_price
                else:
                    should_fire = prev > a.threshold_price >= current
            if should_fire:
                pending_triggers.append((a.id, current, snap))
        db.commit()
    finally:
        db.close()

    if not pending_triggers:
        logger.info("alerts: armed=%d tickers=%d triggered=0 errors=%d",
                    len(armed), len(unique_tickers), errors)
        return {"checked": len(armed), "triggered": 0, "errors": errors}

    # Phase 2: send notification FIRST. Only mark_triggered if send succeeds.
    # This prevents silent loss when bot is down — alert stays armed for retry.
    bot = _get_bot()
    sent = 0
    triggered_count = 0
    for alert_id, current, snap in pending_triggers:
        # Re-fetch alert from DB; skip if status changed (e.g., cancelled mid-cycle)
        db = SessionLocal()
        try:
            a = storage.get_alert(db, alert_id)
        finally:
            db.close()
        if not a or a.status != "armed":
            logger.info("alert#%d status changed mid-cycle (now %s) — skipping",
                        alert_id, a.status if a else "deleted")
            continue
        chat_id = a.chat_id or config.admin_chat_id()
        if not chat_id:
            logger.warning("alert#%d has no chat_id — skipping notification", alert_id)
            continue
        text = templates.fmt_triggered(a, snap)
        ok = await _send_notification(bot, chat_id, text, alert_id)
        if ok:
            # Mark triggered AFTER successful send to avoid silent loss
            db = SessionLocal()
            try:
                marked = storage.mark_triggered(db, alert_id, current)
                if marked:
                    sent += 1
                    triggered_count += 1
            finally:
                db.close()
        await asyncio.sleep(0.3)

    logger.info("alerts: armed=%d triggered=%d notified=%d errors=%d",
                len(armed), triggered_count, sent, errors)
    return {"checked": len(armed), "triggered": triggered_count,
            "notified": sent, "errors": errors}


def register_cron(scheduler) -> None:
    """Wire 5-min cron during market hours (Mon-Fri 09:00-16:30 WIB).

    Two cron entries to bound 16:00-16:30 cleanly without firing 16:35-16:55:
    - hour="9-15", minute every N
    - hour=16, minute=0,5,10,...,30 only
    """
    interval = config.cron_interval_minutes()
    minute_pattern = ",".join(str(i) for i in range(0, 60, interval))
    minute_pattern_closing = ",".join(str(i) for i in range(0, 31, interval))
    scheduler.add_job(
        scan_and_evaluate, "cron",
        day_of_week="mon-fri",
        hour="9-15", minute=minute_pattern,
        timezone=config.WIB,
        id="alerts_scan_main",
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        scan_and_evaluate, "cron",
        day_of_week="mon-fri",
        hour="16", minute=minute_pattern_closing,
        timezone=config.WIB,
        id="alerts_scan_close",
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )
    logger.info("alerts cron registered: every %d min, mon-fri 09:00-16:30 WIB", interval)
