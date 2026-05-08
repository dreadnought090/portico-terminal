"""Telegram bot command + payment handlers for IDX Pulse Pro."""
import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import ContextTypes

from backend.briefing import get_state as briefing_get_state
from backend.briefing import run_briefing
from backend.briefing import set_intraday_enabled as briefing_set_intraday
from backend.briefing import set_mode as briefing_set_mode
from backend.database import SessionLocal
from backend.models import Feedback, Payment, Subscriber
from backend.subscription import channel, config

logger = logging.getLogger("mybloomberg.subscription")


# ── /start ───────────────────────────────────────────────────────────

WELCOME = (
    "🧠 *IDX Pulse Pro*\n"
    "Briefing harian keterbukaan informasi IDX — ringkasan AI untuk Dividen, "
    "HMETD, Laporan Keuangan, Insider Trade, Material Info, Buyback, Public Expose. "
    "Terkirim ke channel premium setiap jam 08:00 WIB.\n\n"
    "*Commands:*\n"
    "/subscribe — daftar (pilih paket)\n"
    "/status — cek masa aktif\n"
    "/renew — perpanjang langganan\n"
    "/feedback — kirim saran/kritik\n"
    "/help — panduan\n\n"
    "_Bukan rekomendasi investasi. Data IDX publik, disusun oleh AI._"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode="Markdown")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


# ── /subscribe ───────────────────────────────────────────────────────

async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    buttons = [
        [InlineKeyboardButton(
            text=f"{p.label} — {p.stars}⭐  ({p.duration_days}d)",
            callback_data=f"buy:{p.key}",
        )]
        for p in config.PLANS
    ]
    await update.message.reply_text(
        "Pilih paket:\n" + "\n".join(f"• *{p.label}* — {p.stars} Stars: {p.blurb}" for p in config.PLANS),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def on_buy_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback when user taps a plan button → send Stars invoice."""
    query = update.callback_query
    await query.answer()
    _, plan_key = query.data.split(":", 1)
    plan = config.PLANS_BY_KEY.get(plan_key)
    if not plan:
        await query.message.reply_text("Paket tidak dikenali.")
        return
    # Payload encodes user + plan + timestamp — verified on pre_checkout.
    payload = f"sub:{query.from_user.id}:{plan.key}:{int(datetime.now(timezone.utc).timestamp())}"
    await ctx.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"IDX Pulse Pro — {plan.label}",
        description=plan.blurb,
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=plan.label, amount=plan.stars)],
    )


# ── Payment flow ─────────────────────────────────────────────────────

async def on_pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve before Telegram actually charges. Validate payload."""
    q = update.pre_checkout_query
    parts = (q.invoice_payload or "").split(":")
    valid = len(parts) == 4 and parts[0] == "sub" and parts[2] in config.PLANS_BY_KEY
    await q.answer(ok=valid, error_message=None if valid else "Paket tidak valid. /subscribe ulang ya.")


async def on_successful_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User paid. Activate subscription + send channel invite link."""
    msg = update.message
    sp = msg.successful_payment
    parts = (sp.invoice_payload or "").split(":")
    if len(parts) != 4 or parts[0] != "sub":
        logger.error("successful_payment with bad payload: %s", sp.invoice_payload)
        return
    _, user_id_s, plan_key, _ = parts
    plan = config.PLANS_BY_KEY.get(plan_key)
    if not plan:
        logger.error("successful_payment for unknown plan: %s", plan_key)
        return

    user = msg.from_user
    db = SessionLocal()
    try:
        # Idempotency: if this charge already recorded, don't double-activate.
        existing = db.query(Payment).filter_by(telegram_charge_id=sp.telegram_payment_charge_id).first()
        if existing:
            logger.info("duplicate successful_payment for charge %s — ignored", sp.telegram_payment_charge_id)
            return

        now = datetime.now(timezone.utc)
        sub = db.query(Subscriber).filter_by(chat_id=user.id).first()
        if sub:
            # Extend from max(now, current expiry) so early renewals stack correctly.
            base = max(sub.expires_at or now, now)
            sub.expires_at = base + timedelta(days=plan.duration_days)
            sub.plan = plan.key
            sub.status = "active"
            sub.last_telegram_charge_id = sp.telegram_payment_charge_id
            sub.reminded_days = ""  # reset reminder flags for new cycle
            sub.username = user.username or ""
            sub.full_name = user.full_name or ""
        else:
            sub = Subscriber(
                chat_id=user.id,
                username=user.username or "",
                full_name=user.full_name or "",
                plan=plan.key,
                status="active",
                started_at=now,
                expires_at=now + timedelta(days=plan.duration_days),
                last_telegram_charge_id=sp.telegram_payment_charge_id,
            )
            db.add(sub)

        db.add(Payment(
            telegram_charge_id=sp.telegram_payment_charge_id,
            chat_id=user.id,
            plan=plan.key,
            amount_stars=sp.total_amount,
            payload=sp.invoice_payload,
            status="paid",
            paid_at=now,
        ))

        # Generate single-use invite link (expires in 1 hour).
        try:
            invite_url = await channel.create_single_use_invite(ctx.bot, label=f"paid-{user.id}")
            sub.invite_link_last = invite_url
        except Exception as e:
            logger.exception("failed to create invite link")
            invite_url = None
        db.commit()

        reply = (
            f"✅ *Payment confirmed!*\n\n"
            f"Paket: *{plan.label}* ({plan.stars} Stars)\n"
            f"Aktif sampai: *{sub.expires_at.astimezone(timezone(timedelta(hours=7))).strftime('%d %b %Y')}*\n\n"
        )
        if invite_url:
            reply += f"🎟 *Join channel:* {invite_url}\n_(single-use, expires 1 jam)_"
        else:
            reply += "⚠️ Ada glitch generate invite link. DM admin untuk bantuan."
        await msg.reply_text(reply, parse_mode="Markdown", disable_web_page_preview=True)
    finally:
        db.close()


# ── /status ──────────────────────────────────────────────────────────

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    db = SessionLocal()
    try:
        sub = db.query(Subscriber).filter_by(chat_id=user_id).first()
        if not sub:
            await update.message.reply_text("Belum subscribe. Ketik /subscribe buat daftar.")
            return
        now = datetime.now(timezone.utc)
        delta = sub.expires_at - now
        days_left = delta.days
        wib = sub.expires_at.astimezone(timezone(timedelta(hours=7)))
        if days_left > 0:
            await update.message.reply_text(
                f"📅 *Status:* {sub.status}\n"
                f"Paket: *{sub.plan}*\n"
                f"Aktif sampai: {wib.strftime('%d %b %Y %H:%M')} WIB\n"
                f"Sisa: *{days_left} hari*",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"⚠️ Masa aktif udah lewat.\n"
                f"Expired: {wib.strftime('%d %b %Y')}\n"
                f"Klik /renew buat perpanjang.",
            )
    finally:
        db.close()


# ── /renew (alias for /subscribe, separate for clarity) ─────────────

async def cmd_renew(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_subscribe(update, ctx)


# ── /feedback <msg> ─────────────────────────────────────────────────

# ── /brief — admin manual trigger ────────────────────────────────────

async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: trigger an immediate IDX briefing run.

    Usage:
        /brief              → header_only mode (free, fast, ~$0)
        /brief full         → full LLM mode (~$0.25)
    """
    admin = config.admin_chat_id()
    user_id = update.effective_user.id
    if admin is None or user_id != admin:
        await update.message.reply_text("⛔ Command admin-only.")
        return

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else "header_only"
    mode = "full" if arg in ("full", "f") else "header_only"

    eta = "~2-3 menit" if mode == "full" else "~10-20 detik"
    cost = "~$0.25" if mode == "full" else "$0"
    await update.message.reply_text(
        f"⏳ Triggering briefing — *{mode}* mode ({cost}, ETA {eta}).\n"
        f"Output broadcast ke channel + DM lu.",
        parse_mode="Markdown",
    )

    # Run in background so Telegram handler doesn't block
    import asyncio as _asyncio
    async def _do_run():
        try:
            result = await run_briefing(force_mode=mode)
            status = result.get("status")
            cost_usd = result.get("cost_usd", 0)
            messages = result.get("messages_sent", 0)
            disclosures = result.get("disclosures_in_window", 0)
            await ctx.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ Briefing done — *{mode}*\n"
                    f"Status: {status}\n"
                    f"Disclosures: {disclosures}\n"
                    f"Messages sent: {messages}\n"
                    f"Cost: ${cost_usd:.4f}"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            await ctx.bot.send_message(
                chat_id=user_id,
                text=f"❌ Briefing gagal: {type(e).__name__}: {e}",
            )
    _asyncio.create_task(_do_run())


# ── /mode — admin: get/set cron mode ─────────────────────────────────

async def cmd_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: view or set the daily cron briefing mode.

    Usage:
        /mode              → show current mode + last run info
        /mode off          → disable cron (no daily briefing)
        /mode header_only  → cheap mode ($0/day, ticker list only)
        /mode full         → full LLM mode (~$0.20-0.25/day)
    """
    admin = config.admin_chat_id()
    user_id = update.effective_user.id
    if admin is None or user_id != admin:
        await update.message.reply_text("⛔ Command admin-only.")
        return

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if not arg:
        # Show current state
        s = briefing_get_state()
        last_run = s.get("last_run_at") or "—"
        last_status = s.get("last_run_status") or "—"
        last_cost = s.get("last_run_cost_usd", 0)
        last_msgs = s.get("last_run_messages_sent", 0)
        last_err = s.get("last_run_error") or ""
        msg = (
            f"⚙️ *Cron Briefing Mode*\n\n"
            f"Mode: *{s['mode']}*\n"
            f"Schedule: 08:00 WIB daily\n\n"
            f"_Last run:_ {last_run}\n"
            f"_Status:_ {last_status}\n"
            f"_Messages:_ {last_msgs}\n"
            f"_Cost:_ ${last_cost:.4f}\n"
        )
        if last_err:
            msg += f"_Error:_ `{last_err[:200]}`\n"
        msg += (
            f"\n*Available modes:*\n"
            f"`/mode off` — disable cron entirely\n"
            f"`/mode header_only` — $0/day, ticker list only\n"
            f"`/mode full` — ~$0.25/day, LLM summaries\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # Set new mode
    try:
        new_state = briefing_set_mode(arg)
        await update.message.reply_text(
            f"✅ Mode set to *{new_state['mode']}*.\n"
            f"Cron 08:00 WIB besok pagi akan fire dengan mode ini.",
            parse_mode="Markdown",
        )
    except ValueError as e:
        await update.message.reply_text(f"⛔ {e}")


async def cmd_intraday(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: enable/disable intraday live alerts (5-min polling 09:00–16:15 WIB).

    Usage:
        /intraday          → show current state
        /intraday on       → enable
        /intraday off      → disable
    """
    admin = config.admin_chat_id()
    user_id = update.effective_user.id
    if admin is None or user_id != admin:
        await update.message.reply_text("⛔ Command admin-only.")
        return

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if not arg:
        s = briefing_get_state()
        on = s.get("intraday_enabled", False)
        last = s.get("last_intraday_at") or "—"
        await update.message.reply_text(
            f"⚡ *Intraday Live Alerts*\n\n"
            f"Status: {'🟢 ON' if on else '🔴 OFF'}\n"
            f"Schedule: 09:00 catch-up + 09:05–16:15 setiap 5 min (Mon-Fri)\n"
            f"Last poll: {last}\n\n"
            f"`/intraday on` — enable\n"
            f"`/intraday off` — disable",
            parse_mode="Markdown",
        )
        return

    if arg in ("on", "enable", "yes", "1"):
        briefing_set_intraday(True)
        await update.message.reply_text("⚡ Intraday alerts: *ON* — first poll fires within 5 min selama market hours.", parse_mode="Markdown")
    elif arg in ("off", "disable", "no", "0"):
        briefing_set_intraday(False)
        await update.message.reply_text("🔴 Intraday alerts: *OFF*", parse_mode="Markdown")
    else:
        await update.message.reply_text("Usage: `/intraday on` atau `/intraday off`", parse_mode="Markdown")


async def cmd_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    # Strip command part
    parts = text.split(maxsplit=1)
    body = parts[1].strip() if len(parts) > 1 else ""
    if not body:
        await update.message.reply_text(
            "Format: `/feedback <pesan>`\n\nContoh: `/feedback format LK kurang clear, tambahin breakdown quarter-to-quarter dong`",
            parse_mode="Markdown",
        )
        return
    user = update.effective_user
    db = SessionLocal()
    try:
        db.add(Feedback(
            chat_id=user.id,
            username=user.username or "",
            message=body[:2000],
            status="new",
        ))
        db.commit()
    finally:
        db.close()
    await update.message.reply_text(
        "✅ Feedback lu udah masuk queue. Thanks, bakal dibaca admin."
    )
