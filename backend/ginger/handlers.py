"""Ginger Telegram handlers — admin-only chat assistant."""
from __future__ import annotations

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from backend.ginger import agent, config

logger = logging.getLogger("ginger.handlers")

# Per-chat history cache (keyed by chat_id). TTL 30 min — gc on each message.
_HISTORY: dict[int, tuple[float, list]] = {}
_HISTORY_TTL = 1800
_MAX_HISTORY_TURNS = 10  # cap to control token bloat


def _get_history(chat_id: int) -> list:
    now = time.time()
    entry = _HISTORY.get(chat_id)
    if not entry:
        return []
    ts, hist = entry
    if now - ts > _HISTORY_TTL:
        _HISTORY.pop(chat_id, None)
        return []
    return hist


def _save_history(chat_id: int, hist: list) -> None:
    # Cap by character count of serialized content (token proxy).
    # Trim from FRONT, but never split tool_use/tool_result pairs.
    from backend.ginger.agent import _is_clean_history
    MAX_CHARS = 40_000  # ~10k tokens proxy

    def _size(h):
        return sum(len(str(m.get("content", ""))) for m in h)

    while len(hist) > 4 and _size(hist) > MAX_CHARS:
        # Drop oldest message
        hist = hist[1:]
        # Then advance until we land on a clean state (preserves pairs)
        while hist and not _is_clean_history(hist):
            hist = hist[1:]
    _HISTORY[chat_id] = (time.time(), hist)


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    admin = config.admin_chat_id()
    return bool(admin and user and user.id == admin)


WELCOME = """Halo, aku Ginger — penyihir Caerleon, sahabat Merriot.

Tugasku: bantu kamu eksplor data Portico via percakapan + catat transaksi.

Contoh tanya (read):
• "Total lot saham banking di porto?"
• "Berapa P&L hari ini?"
• "Saham di sekuritas Mirae?"
• "Thesis BBCA ada berapa?"
• "Alert yang armed sekarang?"

Contoh catat transaksi (write — selalu konfirmasi via tombol):
• "Tadi jual 5 lot BBCA harga 6000 di Mirae"
• "Beli 10 lot TLKM 2850 broker BNI"

📧 Kalau email broker masuk, aku auto-detect & DM untuk konfirmasi
   (perlu setup EMAIL_USER + EMAIL_APP_PASSWORD di .env dulu).

Tip: ketik /reset kalau percakapan udah panjang/melenceng.

Gimana, mau mulai dari mana?"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    # Reset history on /start
    chat_id = update.effective_chat.id
    _HISTORY.pop(chat_id, None)
    await update.message.reply_text(WELCOME)


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation context."""
    if not _is_admin(update):
        return
    chat_id = update.effective_chat.id
    _HISTORY.pop(chat_id, None)
    await update.message.reply_text("🪄 Memori percakapan di-reset. Mulai fresh.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        return
    await update.message.reply_text(WELCOME)


async def on_email_tx_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Confirm/Reject buttons from email-detected transactions."""
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
    try:
        tx_id = int(ident)
    except ValueError:
        return

    from backend.email_inbox import apply_transaction, reject_transaction

    if action == "etx_ok":
        result = apply_transaction(tx_id, chat_id=update.effective_chat.id)
        if result["ok"]:
            await q.edit_message_text(
                (q.message.text or "") + f"\n\n✅ Confirmed & applied → {result['message']}"
            )
        else:
            await q.edit_message_text(
                (q.message.text or "") + f"\n\n⚠ Apply failed: {result['message']}"
            )
    elif action == "etx_no":
        result = reject_transaction(tx_id)
        if result["ok"]:
            await q.edit_message_text(
                (q.message.text or "") + "\n\n❌ Rejected — portfolio tidak diubah."
            )
        else:
            await q.edit_message_text(
                (q.message.text or "") + f"\n\n⚠ Reject failed: {result['message']}"
            )


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Free-text → agent.chat_turn → reply."""
    if not _is_admin(update):
        return
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text:
        return

    chat_id = update.effective_chat.id

    # Typing indicator (non-critical, swallow errors)
    try:
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

    history = _get_history(chat_id)
    try:
        response_text, new_history, side_effects = await agent.chat_turn(text, history)
    except Exception:
        logger.exception("Ginger agent crashed")
        await update.message.reply_text("⚠ Aku crash sebentar. Coba lagi atau /reset.")
        return

    _save_history(chat_id, new_history)

    if len(response_text) > 4000:
        response_text = response_text[:3950] + "\n\n... (terpotong, tanya lebih spesifik)"

    await update.message.reply_text(response_text)

    # Dispatch side-effects (e.g., button message for transaction confirmation)
    for eff in side_effects:
        if eff["type"] == "transaction_pending":
            await _send_transaction_buttons(update.message, eff["tx_id"], eff["preview"])


async def _send_transaction_buttons(msg, tx_id: int, preview: dict) -> None:
    """Follow-up message with [Confirm/Reject] buttons for proposed tx."""
    action = (preview.get("action") or "?").upper()
    ticker = preview.get("ticker") or "?"
    lot = preview.get("lot") or 0
    shares = preview.get("shares") or (lot * 100)
    price = preview.get("price") or 0
    total = preview.get("total_value") or shares * price
    broker = preview.get("broker") or "—"
    trade_date = preview.get("trade_date") or "?"
    emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
    text = (
        f"📋 Konfirmasi Transaksi\n\n"
        f"{emoji} {action} {ticker}\n"
        f"Lot: {lot} ({shares:,} shares)\n"
        f"Price: Rp {price:,.0f}\n"
        f"Total: Rp {total:,.0f}\n"
        f"Broker: {broker}\n"
        f"Date: {trade_date}\n\n"
        f"Konfirmasi via tombol di bawah."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"etx_ok:{tx_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"etx_no:{tx_id}"),
    ]])
    await msg.reply_text(text, reply_markup=keyboard)
