"""Alert Telegram handlers — registered into Merriot bot via register_handlers().

NL patterns checked BEFORE Merriot's append/quick/LLM chain (cheap regex, no DB).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from backend.database import SessionLocal
from backend.alerts import config, storage, templates

logger = logging.getLogger("alerts.handlers")


# ── Admin guard (small dup from merriot — keep modules independent) ──

def _is_admin(update: Update) -> bool:
    user = update.effective_user
    admin = config.admin_chat_id()
    if not admin or not user:
        return False
    return user.id == admin


async def _reject_non_admin(update: Update) -> bool:
    if _is_admin(update):
        return False
    return True


# ── Price parsing ─────────────────────────────────────────────────────

_PRICE_RE = re.compile(r"^([\d.,]+)([kKmM]?)$")


def _parse_price(s: str) -> Optional[float]:
    """Accepts: 12000 / 12k / 1.2m / 12,500 / 12.500 → 12500.

    Heuristic: dot followed by EXACTLY 3 digits (and no other dot) = thousand
    separator. Dot followed by 1-2 digits = decimal. Comma always = thousand.
    """
    s = s.strip()
    m = _PRICE_RE.match(s)
    if not m:
        return None
    num_str, suffix = m.group(1), m.group(2)
    num_str = num_str.replace(",", "")  # comma always = thousand separator
    if "." in num_str:
        parts = num_str.split(".")
        # Multiple dots OR final group exactly 3 digits → all dots are thousand separators
        # (Indonesian format: "1.234.567" or "12.500"). Single trailing 1-2 digits = decimal.
        if len(parts) >= 3:
            if all(len(p) == 3 for p in parts[1:]):
                num_str = "".join(parts)  # 1.234.567 → 1234567
            else:
                return None  # ambiguous like "1.23.4"
        elif len(parts) == 2 and len(parts[1]) == 3:
            num_str = parts[0] + parts[1]  # 12.500 → 12500
        # else keep as decimal (12.5 → 12.5)
    try:
        val = float(num_str)
    except ValueError:
        return None
    if suffix in ("k", "K"):
        val *= 1_000
    elif suffix in ("m", "M"):
        val *= 1_000_000
    if val <= 0:
        return None
    return val


# ── Natural-language pattern (called from merriot.handlers.on_message) ──

# Lenient natural-language pattern.
# Matches all of:
#   "alert BBCA above 12000"
#   "alert BBCA above 12000 target jangka pendek"
#   "Alert BUMI klo harga diatas 250"
#   "alert TLKM kalau turun 2800"
#   "alert BMRI jika harga di atas 6000 watch breakout"
#   "Alert BBRI > 5500"
#
# Groups: 1=ticker, 2=direction-word, 3=price, 4=optional label.
# Filler words (klo|kalau|kalo|jika|if|harga|price|sampai|sampe|saat|when|to|sudah)
# allowed between ticker and direction. "di atas"/"di bawah" with optional space
# normalized via _normalize_dir.
_ALERT_RE = re.compile(
    r"^\s*alert\s+"
    # optional filler word(s) BEFORE ticker (e.g. "alert klo BUMI ...")
    r"(?:(?:klo|kalau|kalo|jika|if|kl|kalau\s+harga)\s+)?"
    r"([A-Z]{3,6})\b"
    # optional filler word(s) BETWEEN ticker and direction
    r"(?:\s+(?:klo|kalau|kalo|jika|if|harga|price|sampai|sampe|saat|when|to|udah|sudah|sd|kl)\b)*"
    r"\s*(above|below|atas|bawah|naik|turun|di\s*atas|di\s*bawah|tembus|break(?:out)?|>=?|<=?)\s*"
    r"([\d.,kKmM]+)"
    r"(?:\s+(.{1,80}))?\s*$",
    re.IGNORECASE,
)
# delalert 1, cancel alert 1, batal alert 1
_DELALERT_RE = re.compile(
    r"^\s*(?:delalert|cancel\s+alert|batal\s+alert|hapus\s+alert)\s+#?(\d+)\s*$",
    re.IGNORECASE,
)


def _normalize_dir(s: str) -> Optional[str]:
    s = re.sub(r"\s+", "", s.lower())  # collapse "di atas" → "diatas"
    if s in ("above", "atas", "diatas", "naik", "tembus", "break", "breakout", ">", ">="):
        return "above"
    if s in ("below", "bawah", "dibawah", "turun", "<", "<="):
        return "below"
    return None


async def try_natural_alert(msg, text: str) -> bool:
    """Returns True if matched and handled. Called from Merriot on_message.

    Admin-guarded — non-admin returns False so message falls through to
    Merriot's other handlers (which themselves silently ignore non-admin).
    """
    # Cheap regex first — only check admin if pattern matches (avoid leaking
    # bot existence by always rejecting non-admins).
    m_del = _DELALERT_RE.match(text)
    m_alert = _ALERT_RE.match(text)
    if not m_del and not m_alert:
        return False

    # Admin guard — `msg` doesn't carry user; pull from update via from_user.
    user = msg.from_user if hasattr(msg, "from_user") else None
    admin = config.admin_chat_id()
    if not admin or not user or user.id != admin:
        return False

    if m_del:
        await _do_cancel(msg, int(m_del.group(1)))
        return True

    ticker = m_alert.group(1).upper()
    direction = _normalize_dir(m_alert.group(2))
    if not direction:
        await msg.reply_text(templates.ERR_INVALID_DIR)
        return True

    threshold = _parse_price(m_alert.group(3))
    if threshold is None:
        await msg.reply_text(templates.ERR_INVALID_PRICE)
        return True

    label = (m_alert.group(4) or "").strip()
    await _do_create(msg, ticker, direction, threshold, label)
    return True


# ── Slash commands ────────────────────────────────────────────────────

async def cmd_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    args = ctx.args or []
    if len(args) < 3:
        await update.message.reply_text(templates.HELP_USAGE)
        return
    ticker = args[0].upper()
    direction = _normalize_dir(args[1])
    if not direction:
        await update.message.reply_text(templates.ERR_INVALID_DIR)
        return
    threshold = _parse_price(args[2])
    if threshold is None:
        await update.message.reply_text(templates.ERR_INVALID_PRICE)
        return
    if not re.match(r"^[A-Z]{3,6}$", ticker):
        await update.message.reply_text(templates.ERR_INVALID_TICKER)
        return
    label = " ".join(args[3:])[:80]
    await _do_create(update.message, ticker, direction, threshold, label)


async def cmd_alerts(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    db = SessionLocal()
    try:
        armed = storage.list_armed(db)
        history = storage.list_history(db, limit=10)
    finally:
        db.close()

    # Fetch current prices for armed alerts in parallel (gather + semaphore).
    prices: dict[str, float] = {}
    try:
        import asyncio
        from backend.idx_native import fetch_trading_info_daily
        unique = list({a.ticker for a in armed})[:15]
        sem = asyncio.Semaphore(5)
        async def _one(t):
            async with sem:
                try:
                    s = await fetch_trading_info_daily(t)
                    return t, (s.get("close") if s else None)
                except Exception:
                    return t, None
        results = await asyncio.gather(*[_one(t) for t in unique])
        prices = {t: c for t, c in results if c}
    except Exception:
        logger.exception("price fetch in cmd_alerts failed")

    market_open = _market_open_now()
    text = templates.fmt_alerts_list(armed, history, market_open, prices)
    await update.message.reply_text(text)


async def cmd_delalert(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    args = ctx.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("Pakai: /delalert <id>  (mis. /delalert 1)")
        return
    await _do_cancel(update.message, int(args[0]))


# ── Create / cancel / re-arm helpers ─────────────────────────────────

async def _do_create(msg, ticker: str, direction: str, threshold: float, label: str) -> None:
    db = SessionLocal()
    try:
        # Duplicate check
        dups = storage.find_duplicates(db, ticker, direction, threshold, window_h=24, tolerance=0.005)
        if dups:
            d = dups[0]
            await msg.reply_text(
                f"⚠ Mirip alert #{d.id} (sudah armed). Cancel dulu kalau mau ganti."
            )
            return
        a = storage.create_alert(
            db, ticker=ticker, direction=direction, threshold=threshold,
            label=label, chat_id=config.admin_chat_id(),
        )
    finally:
        db.close()

    # Fetch current price for the confirmation message + sanity check
    current_price: Optional[float] = None
    try:
        from backend.idx_native import fetch_trading_info_daily
        snap = await fetch_trading_info_daily(ticker)
        if snap:
            current_price = snap.get("close")
    except Exception:
        pass

    sanity_warn = False
    if current_price and threshold:
        ratio = abs(threshold - current_price) / current_price
        sanity_warn = ratio > 0.5  # >50% from current = probable typo

    text = templates.fmt_alert_armed(a, current_price, sanity_warn)
    await msg.reply_text(text)


async def _do_cancel(msg, alert_id: int) -> None:
    db = SessionLocal()
    try:
        a = storage.cancel(db, alert_id)
    finally:
        db.close()
    if not a:
        await msg.reply_text(templates.ERR_NOT_FOUND)
        return
    if a.status != "cancelled":
        await msg.reply_text(templates.ERR_ALREADY_TRIGGERED)
        return
    await msg.reply_text(f"❌ Alert #{a.id} {a.ticker} dibatalkan.")


# ── Callback handlers (a* prefix to avoid collision with Merriot) ────

async def on_alert_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None:
        return
    try:
        await q.answer()
    except Exception:
        pass
    if not _is_admin(update):
        return
    data = q.data or ""
    if ":" not in data:
        return
    action, ident = data.split(":", 1)

    if action == "adone":
        await _cb_done(q, int(ident))
    elif action == "acancel":
        await _cb_cancel(q, int(ident))


async def _cb_done(q, alert_id: int) -> None:
    """User acks fired alert AND stops it. Persistent mode: alert is still
    'armed' after fire, so Done must explicitly cancel to stop further fires."""
    db = SessionLocal()
    try:
        a = storage.mark_done(db, alert_id)
    finally:
        db.close()
    text = q.message.text or ""
    if a and a.status == "cancelled":
        suffix = f"\n\n✅ Done — alert #{alert_id} dihentikan."
    else:
        suffix = "\n\n✅ Acked."
    try:
        await q.edit_message_text(text + suffix)
    except Exception:
        pass


async def _cb_cancel(q, alert_id: int) -> None:
    db = SessionLocal()
    try:
        a = storage.cancel(db, alert_id)
    finally:
        db.close()
    if a:
        await q.edit_message_text(f"❌ Alert #{a.id} {a.ticker} dibatalkan.")


# ── Market hours helper ───────────────────────────────────────────────

def _market_open_now() -> bool:
    from datetime import datetime
    now = datetime.now(config.WIB)
    if now.weekday() > 4:  # Sat/Sun
        return False
    h, m = now.hour, now.minute
    if h < 9 or h > 16:
        return False
    if h == 16 and m > 30:
        return False
    return True


# ── Registration entry point (called from merriot/bot.py) ────────────

def register_handlers(app: Application) -> None:
    """Register alert commands + callback into Merriot's bot.

    Pattern-filtered callback handler so it doesn't intercept Merriot's
    callbacks (different prefixes).
    """
    app.add_handler(CommandHandler("alert", cmd_alert))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("delalert", cmd_delalert))
    app.add_handler(CallbackQueryHandler(on_alert_callback, pattern=r"^a(done|cancel):"))
