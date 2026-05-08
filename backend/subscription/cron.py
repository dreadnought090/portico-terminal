"""Expiry reminder + auto-kick cron jobs."""
import logging
from datetime import datetime, timedelta, timezone

from backend.database import SessionLocal
from backend.models import Feedback, Subscriber
from backend.subscription import bot as bot_mod
from backend.subscription import channel as chan
from backend.subscription.config import GRACE_HOURS, REMINDER_DAYS, admin_chat_id

logger = logging.getLogger("mybloomberg.subscription")


async def remind_expiring() -> None:
    """DM subscribers whose subscription is about to expire (7d, 3d, 1d)."""
    app = bot_mod.get_bot()
    if not app:
        return
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    sent = 0
    try:
        subs = db.query(Subscriber).filter(Subscriber.status == "active").all()
        for sub in subs:
            delta = sub.expires_at - now
            days_left = delta.days
            if days_left not in REMINDER_DAYS:
                continue
            reminded = set(int(d) for d in (sub.reminded_days or "").split(",") if d.strip().isdigit())
            if days_left in reminded:
                continue
            try:
                text = (
                    f"⏰ Subscription lu *habis {days_left} hari lagi*.\n"
                    f"Klik /renew buat perpanjang ({sub.plan})."
                ) if days_left > 1 else (
                    "⏰ *Besok* subscription habis. /renew sekarang biar ga ke-kick."
                )
                await app.bot.send_message(chat_id=sub.chat_id, text=text, parse_mode="Markdown")
                reminded.add(days_left)
                sub.reminded_days = ",".join(str(d) for d in sorted(reminded))
                sent += 1
            except Exception:
                logger.exception("reminder failed for %s", sub.chat_id)
        db.commit()
    finally:
        db.close()
    if sent:
        logger.info("sent %d expiry reminders", sent)


async def kick_expired() -> None:
    """Remove subscribers past expiry + grace period from channel."""
    app = bot_mod.get_bot()
    if not app:
        return
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=GRACE_HOURS)
    db = SessionLocal()
    kicked = 0
    try:
        expired = db.query(Subscriber).filter(
            Subscriber.status.in_(["active", "grace"]),
            Subscriber.expires_at < cutoff,
        ).all()
        for sub in expired:
            try:
                ok = await chan.kick_member(app.bot, sub.chat_id)
                sub.status = "expired"
                kicked += 1
                try:
                    await app.bot.send_message(
                        chat_id=sub.chat_id,
                        text="Subscription lu udah habis + 24h grace. Kamu udah di-remove dari channel. /subscribe kapanpun untuk rejoin 👋",
                    )
                except Exception:
                    pass  # user might have blocked bot, don't crash
            except Exception:
                logger.exception("kick failed for %s", sub.chat_id)
        db.commit()
    finally:
        db.close()
    if kicked:
        logger.info("auto-kicked %d expired subscribers", kicked)


async def feedback_digest() -> None:
    """Weekly DM admin with unread feedback entries."""
    app = bot_mod.get_bot()
    admin = admin_chat_id()
    if not app or not admin:
        return
    db = SessionLocal()
    try:
        items = db.query(Feedback).filter_by(status="new").order_by(Feedback.created_at.desc()).limit(50).all()
        if not items:
            return
        lines = [f"📬 *Feedback digest* ({len(items)} item baru)\n"]
        for fb in items:
            who = f"@{fb.username}" if fb.username else f"id:{fb.chat_id}"
            lines.append(f"• _{who}_: {fb.message[:200]}")
        try:
            await app.bot.send_message(
                chat_id=admin, text="\n".join(lines), parse_mode="Markdown",
            )
            # Mark as read after successful DM
            for fb in items:
                fb.status = "read"
            db.commit()
        except Exception:
            logger.exception("feedback digest DM failed")
    finally:
        db.close()


def register_cron(scheduler) -> None:
    """Wire cron jobs into APScheduler. Called from app.py lifespan."""
    # Daily 07:00 WIB — reminder DMs
    scheduler.add_job(remind_expiring, "cron", hour=7, minute=0, id="sub_expiry_reminder")
    # Daily 00:05 WIB — kick expired past grace
    scheduler.add_job(kick_expired, "cron", hour=0, minute=5, id="sub_expiry_kick")
    # Weekly Mon 09:00 WIB — feedback digest
    scheduler.add_job(feedback_digest, "cron", day_of_week="mon", hour=9, minute=0, id="sub_feedback_digest")
