"""Merriot Telegram handlers — admin-only.

Capture flow:
  user message → LLM extract → preview + [Save/Edit/Cancel]
  → on Save: insert ThesisNote, schedule reminders via cron
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from backend.database import SessionLocal
from backend.models import PortfolioItem, Watchlist
from backend.merriot import config, extractor, storage, templates

logger = logging.getLogger("merriot.handlers")


# ── In-memory draft cache (TTL 1h) ────────────────────────────────────
# Maps draft_id → (ts, raw_text, ThesisExtraction)
_DRAFTS: dict[str, tuple[float, str, Any]] = {}
_DRAFT_TTL = 3600


def _gc_drafts() -> None:
    now = time.time()
    expired = [k for k, (ts, _, _) in _DRAFTS.items() if now - ts > _DRAFT_TTL]
    for k in expired:
        _DRAFTS.pop(k, None)


def _save_draft(raw: str, ext) -> str:
    _gc_drafts()
    did = uuid.uuid4().hex[:10]
    _DRAFTS[did] = (time.time(), raw, ext)
    return did


def _get_draft(did: str):
    _gc_drafts()
    entry = _DRAFTS.get(did)
    if not entry:
        return None
    _, raw, ext = entry
    return raw, ext


def _pop_draft(did: str) -> None:
    _DRAFTS.pop(did, None)


# ── Admin guard ───────────────────────────────────────────────────────

def _is_admin(update: Update) -> bool:
    """Strict — match user.id ONLY. Never trust chat.id (group could collide)."""
    user = update.effective_user
    admin = config.admin_chat_id()
    if not admin or not user:
        return False
    return user.id == admin


async def _reject_non_admin(update: Update) -> bool:
    """Returns True if request rejected. Silent drop — don't acknowledge bot
    existence to non-admins (low-grade fingerprinting protection)."""
    if _is_admin(update):
        return False
    logger.warning("non-admin access blocked: user=%s chat=%s",
                   update.effective_user.id if update.effective_user else "?",
                   update.effective_chat.id if update.effective_chat else "?")
    return True


async def on_my_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """If bot added to a group/channel, leave immediately. Merriot is DM-only."""
    if not update.my_chat_member:
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup", "channel"):
        return
    try:
        await ctx.bot.send_message(chat_id=chat.id, text="Merriot cuma jalan di DM. Bye.")
    except Exception:
        pass
    try:
        await ctx.bot.leave_chat(chat_id=chat.id)
        logger.info("left non-DM chat %s (%s)", chat.id, chat.type)
    except Exception:
        logger.exception("failed to leave chat")


# ── Commands ──────────────────────────────────────────────────────────

_WELCOME_FLAG_PATH = None  # set lazily, lives in data/


def _welcome_seen() -> bool:
    """Track whether /start welcome has been shown before (one-time greeting)."""
    global _WELCOME_FLAG_PATH
    import os
    if _WELCOME_FLAG_PATH is None:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        _WELCOME_FLAG_PATH = os.path.join(base, ".merriot_welcome_seen")
    return os.path.exists(_WELCOME_FLAG_PATH)


def _mark_welcome_seen() -> None:
    import os
    if _WELCOME_FLAG_PATH:
        try:
            with open(_WELCOME_FLAG_PATH, "w") as f:
                f.write("1")
        except Exception:
            pass


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    if _welcome_seen():
        await update.message.reply_text("Halo lagi. /help kalau lupa.")
    else:
        await update.message.reply_text(templates.WELCOME)
        _mark_welcome_seen()


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    # Append a one-line privacy note — bocoran goes through Anthropic + Telegram.
    note = (
        "\n\n📡 Catatan privacy: teks yang lu kirim diparse oleh Claude (Anthropic, US) "
        "dan jalan lewat server Telegram. Jangan kirim info yg bener-bener tidak boleh "
        "leave device."
    )
    await update.message.reply_text(templates.HELP + note)


async def cmd_thesis(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("Pakai: /thesis <TICKER>  (mis. /thesis BBCA)")
        return
    ticker = args[0].upper().strip()
    db = SessionLocal()
    try:
        notes = storage.list_for_ticker(db, ticker, limit=20)
    finally:
        db.close()
    await update.message.reply_text(templates.fmt_thesis_list(notes, ticker))


async def cmd_due(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    db = SessionLocal()
    try:
        notes = storage.list_due_within(db, days=7)
    finally:
        db.close()
    await update.message.reply_text(templates.fmt_due_list(notes))


async def cmd_recent(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    db = SessionLocal()
    try:
        notes = storage.list_recent(db, limit=10)
    finally:
        db.close()
    await update.message.reply_text(templates.fmt_recent_list(notes))


async def cmd_tickers(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """List all tickers that have at least one thesis note."""
    if await _reject_non_admin(update):
        return
    db = SessionLocal()
    try:
        rows = storage.list_tickers_with_counts(db)
    finally:
        db.close()
    await update.message.reply_text(templates.fmt_tickers_list(rows))


async def cmd_timeline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Chronological timeline view of all pending review dates."""
    if await _reject_non_admin(update):
        return
    db = SessionLocal()
    try:
        # Pull all pending notes (cap 200 — overflow unlikely for personal tracker)
        notes, _ = storage.list_all(db, limit=200, status="pending")
    finally:
        db.close()
    text = templates.fmt_timeline(notes)
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (terpotong, terlalu banyak pending. Pakai /due untuk minggu ini)"
    await update.message.reply_text(text)


async def cmd_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all notes (capped at 50), grouped by ticker, newest first.

    Optional arg: status filter (pending | reviewed | invalid).
    Example: /all pending
    """
    if await _reject_non_admin(update):
        return
    args = ctx.args or []
    status = args[0].lower() if args and args[0].lower() in ("pending", "reviewed", "invalid") else None
    db = SessionLocal()
    try:
        notes, total = storage.list_all(db, limit=50, status=status)
    finally:
        db.close()
    text = templates.fmt_all_notes(notes, total)
    if status:
        text = f"Filter: status={status}\n\n" + text
    # Telegram message cap is 4096; truncate gracefully if needed
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (terpotong, pakai /tickers untuk overview)"
    await update.message.reply_text(text)


async def cmd_del(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    args = ctx.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("Pakai: /del <id>  (mis. /del 42)")
        return
    note_id = int(args[0])
    db = SessionLocal()
    try:
        ok = storage.delete_note(db, note_id)
    finally:
        db.close()
    await update.message.reply_text(f"🗑 Deleted #{note_id}" if ok else templates.ERR_NOTE_NOT_FOUND)


# ── Vision capture (screenshot → Sonnet 4.6 vision) ──────────────────

async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User sends screenshot of chart / Telegram message / slide → vision extract."""
    if await _reject_non_admin(update):
        return
    msg = update.message
    if not msg or not msg.photo:
        return

    is_forward = bool(getattr(msg, "forward_origin", None) or getattr(msg, "forward_date", None))
    if is_forward:
        await msg.reply_text(
            "📩 Foto ini forward dari chat lain. Kalau di-extract, image dikirim ke Claude.\n"
            "Kirim ulang dengan upload langsung kalau tetap mau proses."
        )
        return

    try:
        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass  # typing indicator is decorative; don't fail the whole handler on transient net error

    try:
        photo = msg.photo[-1]  # largest variant
        tg_file = await ctx.bot.get_file(photo.file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        logger.exception("photo download failed")
        await msg.reply_text(f"⚠ Gagal download foto: {e}")
        return

    if len(image_bytes) > 5 * 1024 * 1024:
        await msg.reply_text("Foto >5MB. Compress dulu.")
        return

    caption = (msg.caption or "").strip()

    db = SessionLocal()
    try:
        port_tickers = [r.ticker for r in db.query(PortfolioItem.ticker).distinct().all()]
        wl_tickers = [r.ticker for r in db.query(Watchlist.ticker).distinct().all()]
    except Exception:
        port_tickers, wl_tickers = [], []
    finally:
        db.close()

    result = await extractor.extract_with_vision(
        image_bytes,
        image_media_type="image/jpeg",
        caption=caption,
        portfolio_tickers=port_tickers,
        watchlist_tickers=wl_tickers,
    )

    if isinstance(result, extractor.ExtractionError):
        await msg.reply_text(f"⚠ {result.error}\n{result.suggestion}")
        return

    raw_for_draft = caption or "[image]"
    draft_id = _save_draft(raw_for_draft, result)
    preview = "📷 Vision extract:\n\n" + templates.fmt_extraction_preview(result, draft_id)

    if isinstance(result.ticker, list) and len(result.ticker) > 1:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📑 Split {len(result.ticker)} notes", callback_data=f"split:{draft_id}")],
            [InlineKeyboardButton(f"🔗 Save as basket ({result.ticker[0]})", callback_data=f"save:{draft_id}"),
             InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{draft_id}")],
        ])
        preview += f"\n\n⚠ Multi-ticker — Split = {len(result.ticker)} notes, Basket = simpan satu"
    else:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Save", callback_data=f"save:{draft_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{draft_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{draft_id}"),
        ]])
    await msg.reply_text(preview, reply_markup=keyboard)


# ── Free-text capture ─────────────────────────────────────────────────

_QUICK_CMD_RE = __import__("re").compile(
    r"^\s*(del|hapus|delete|rm|remove|"
    r"rev|reviewed|review|done|"
    r"tunda|postpone|pp|"
    r"invalid|batal|skip)"
    r"(?:\s+note)?\s*#?\s*(\d+)\s*$",  # optional "note" between verb and id
    __import__("re").IGNORECASE,
)

# Reverse-order: "note 11 hapus", "11 dihapus", "#11 delete", "note 11 done"
_QUICK_CMD_REV_RE = __import__("re").compile(
    r"^\s*(?:note\s+)?#?(\d+)\s+"
    r"(del|hapus|dihapus|delete|deleted|rm|remove|removed|"
    r"rev|reviewed|review|done|selesai|"
    r"tunda|postpone|pp|"
    r"invalid|batal|cancelled|skip)\s*$",
    __import__("re").IGNORECASE,
)

# Append-info command: "+1 <text>", "add 1 <text>", "+MDIA <text>", "add MDIA <text>"
# Group 1 = optional verb (+/add/update/upd/tambah), Group 2 = id or ticker, Group 3 = text
_APPEND_CMD_RE = __import__("re").compile(
    r"^\s*(?:\+|add|update|upd|tambah)\s*#?\s*(\d+|[A-Z]{3,6})\s+(.+)$",
    __import__("re").IGNORECASE | __import__("re").DOTALL,
)


async def _try_append_command(msg, text: str) -> bool:
    """Detect 'add 1 <text>', '+MDIA <text>', 'tambah BBCA info ...' etc.

    Routes to existing note (by ID or latest pending for ticker) and appends.
    """
    m = _APPEND_CMD_RE.match(text)
    if not m:
        return False
    target = m.group(1)
    addition = m.group(2).strip()
    if not addition:
        return False

    db = SessionLocal()
    try:
        if target.isdigit():
            note_id = int(target)
            note = storage.append_to_note(db, note_id, addition)
            if not note:
                await msg.reply_text(f"Note #{note_id} tidak ketemu.")
                return True
        else:
            ticker = target.upper()
            existing = storage.latest_pending_for_ticker(db, ticker)
            if not existing:
                await msg.reply_text(
                    f"Belum ada thesis pending untuk {ticker}. "
                    f"Lempar thesis baru aja, jangan pakai 'add' dulu."
                )
                return True
            note = storage.append_to_note(db, existing.id, addition)
        if not note:
            await msg.reply_text(templates.ERR_NOTE_NOT_FOUND)
            return True

        # Confirm with the latest key_points snapshot
        kp_lines = "\n".join(f"  • {kp}" for kp in (note.key_points or []))
        await msg.reply_text(
            f"📝 Update #{note.id} {note.ticker}:\n"
            f"{kp_lines}\n\n"
            f"Review tetap: {templates._fmt_date_id(note.review_at)}"
        )
    finally:
        db.close()
    return True


async def _try_quick_command(msg, text: str) -> bool:
    """Detect natural-language single-word commands like 'del 1', 'hapus #2',
    'reviewed 3', 'tunda 4', 'note 11 hapus', '11 done'. Returns True if handled.
    """
    m = _QUICK_CMD_RE.match(text)
    if m:
        verb = m.group(1).lower()
        note_id = int(m.group(2))
    else:
        m = _QUICK_CMD_REV_RE.match(text)
        if not m:
            return False
        note_id = int(m.group(1))
        verb = m.group(2).lower()
        # Normalize "dihapus"/"deleted"/"removed"/"selesai"/"cancelled" to canonical
        if verb in ("dihapus", "deleted", "removed"):
            verb = "del"
        elif verb in ("selesai",):
            verb = "done"
        elif verb in ("cancelled",):
            verb = "batal"

    db = SessionLocal()
    try:
        if verb in ("del", "hapus", "delete", "rm", "remove"):
            ok = storage.delete_note(db, note_id)
            await msg.reply_text(f"🗑 Note #{note_id} dihapus." if ok else templates.ERR_NOTE_NOT_FOUND)
        elif verb in ("rev", "reviewed", "review", "done"):
            n = storage.mark_reviewed(db, note_id)
            await msg.reply_text(
                f"✅ Note #{note_id} {n.ticker} ditandai reviewed."
                if n else templates.ERR_NOTE_NOT_FOUND
            )
        elif verb in ("tunda", "postpone", "pp"):
            n = storage.postpone(db, note_id, days=7)
            if n:
                await msg.reply_text(
                    f"⏰ Note #{n.id} {n.ticker} ditunda → review {templates._fmt_date_id(n.review_at)}"
                )
            else:
                await msg.reply_text(templates.ERR_NOTE_NOT_FOUND)
        elif verb in ("invalid", "batal", "skip"):
            n = storage.mark_invalid(db, note_id)
            await msg.reply_text(
                f"💀 Note #{note_id} {n.ticker} ditandai invalid."
                if n else templates.ERR_NOTE_NOT_FOUND
            )
    finally:
        db.close()
    return True


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    if not update.message or not update.message.text:
        return

    # Forwarded messages can leak third-party content to Anthropic — confirm first.
    msg = update.message
    is_forward = bool(getattr(msg, "forward_origin", None) or getattr(msg, "forward_date", None))
    if is_forward:
        await msg.reply_text(
            "📩 Pesan ini forward dari chat lain. Kalau di-extract, isinya dikirim ke Claude.\n"
            "Tetap proses? Kirim ulang ya tanpa di-forward (paste teksnya) kalau yakin."
        )
        return

    text = msg.text.strip()
    if not text:
        await msg.reply_text(templates.ERR_EMPTY_INPUT)
        return

    # Price alert pattern (cheap regex, runs BEFORE append/quick/LLM)
    try:
        from backend.alerts.handlers import try_natural_alert
        if await try_natural_alert(msg, text):
            return
    except Exception:
        logger.exception("alert NL handler failed")

    # Append to existing note: "add 1 <text>", "+MDIA info dari pak Benny ..."
    if await _try_append_command(msg, text):
        return

    # Quick natural-language commands (del/hapus/reviewed/tunda/invalid + id)
    # — handle BEFORE LLM extraction to avoid wasting a call on "del 1".
    if await _try_quick_command(msg, text):
        return

    if len(text) > 2000:
        await msg.reply_text("Pesan kepanjangan (max 2000 char). Potong dulu inti thesisnya.")
        return

    try:
        await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass  # typing indicator is decorative; don't fail the whole handler on transient net error

    db = SessionLocal()
    try:
        port_tickers = [r.ticker for r in db.query(PortfolioItem.ticker).distinct().all()]
        wl_tickers = [r.ticker for r in db.query(Watchlist.ticker).distinct().all()]
    except Exception:
        port_tickers, wl_tickers = [], []
    finally:
        db.close()

    result = await extractor.extract(text, port_tickers, wl_tickers)

    if isinstance(result, extractor.ExtractionError):
        msg_text = f"⚠ {result.error}\n{result.suggestion}".strip()
        await msg.reply_text(msg_text)
        return

    # Duplicate detection — warn before save (only when single-ticker)
    if isinstance(result.ticker, str):
        db = SessionLocal()
        try:
            dups = storage.find_duplicates(db, result.ticker, text, days=7)
        finally:
            db.close()
        if dups:
            d = dups[0]
            await msg.reply_text(
                f"⚠ Mirip note #{d.id} ({d.ticker}, "
                f"{d.created_at.strftime('%-d %b') if d.created_at else '?'}). "
                f"Tetap save sebagai note baru? (klik Save di bawah, atau Cancel buat skip)"
            )

    draft_id = _save_draft(text, result)
    preview = templates.fmt_extraction_preview(result, draft_id)

    # Multi-ticker — surface explicit choice instead of silent first-ticker save
    if isinstance(result.ticker, list) and len(result.ticker) > 1:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📑 Split {len(result.ticker)} notes", callback_data=f"split:{draft_id}")],
            [InlineKeyboardButton(f"🔗 Save as basket ({result.ticker[0]})", callback_data=f"save:{draft_id}"),
             InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{draft_id}")],
        ])
        preview += f"\n\n⚠ Multi-ticker — Split = bikin {len(result.ticker)} notes terpisah, Basket = simpan satu (ticker {result.ticker[0]})"
    else:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Save", callback_data=f"save:{draft_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{draft_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{draft_id}"),
        ]])
    await msg.reply_text(preview, reply_markup=keyboard)


# ── Callback button handlers ──────────────────────────────────────────

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None:
        return
    # Always answer the callback so Telegram client stops the spinner —
    # even for unauthorized callers (silently dropped).
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

    if action == "save":
        await _do_save(q, ident)
    elif action == "split":
        await _do_split(q, ident)
    elif action == "cancel":
        await _do_cancel(q, ident)
    elif action == "edit":
        await _do_edit(q, ident)
    elif action == "rev":
        await _do_reviewed(q, int(ident))
    elif action == "pp7":
        await _do_postpone(q, int(ident), days=7)
    elif action == "inv":
        await _do_invalid(q, int(ident))
    elif action == "upd":
        await _do_update_prompt(q, int(ident))


async def _do_save(q, draft_id: str) -> None:
    draft = _get_draft(draft_id)
    if not draft:
        await q.edit_message_text(templates.ERR_DRAFT_EXPIRED)
        return
    raw, ext = draft
    # Multi-ticker → save first, warn user to split rest
    ticker = ext.ticker[0] if isinstance(ext.ticker, list) else ext.ticker
    db = SessionLocal()
    try:
        note = storage.create_note(
            db,
            ticker=ticker,
            body=raw,
            thesis_type=ext.thesis_type,
            thesis_direction=ext.thesis_direction,
            key_points=ext.key_points,
            tags=ext.tags,
            source="telegram",
            confidence=ext.confidence,
            review_at=ext.suggested_review_date,
            review_reasoning=ext.review_reasoning,
        )
    finally:
        db.close()
    _pop_draft(draft_id)
    await q.edit_message_text(templates.fmt_saved_confirmation(note))


async def _do_cancel(q, draft_id: str) -> None:
    _pop_draft(draft_id)
    try:
        await q.edit_message_text("❌ Dibatalkan.")
    except Exception:
        pass


async def _do_edit(q, draft_id: str) -> None:
    if not _get_draft(draft_id):
        await q.edit_message_text(templates.ERR_DRAFT_EXPIRED)
        return
    # Pop draft so old preview's Save button can't race with new edit input.
    _pop_draft(draft_id)
    await q.edit_message_text(
        "Oke, kirim ulang thesisnya yang udah lu koreksi (full text). "
        "Draft lama udah gw skip."
    )


async def _do_split(q, draft_id: str) -> None:
    """Multi-ticker split — create one note per ticker."""
    draft = _get_draft(draft_id)
    if not draft:
        await q.edit_message_text(templates.ERR_DRAFT_EXPIRED)
        return
    raw, ext = draft
    tickers = ext.ticker if isinstance(ext.ticker, list) else [ext.ticker]
    db = SessionLocal()
    saved_ids = []
    try:
        for t in tickers:
            note = storage.create_note(
                db,
                ticker=t,
                body=raw,
                thesis_type=ext.thesis_type,
                thesis_direction=ext.thesis_direction,
                key_points=ext.key_points,
                tags=ext.tags,
                source="telegram",
                confidence=ext.confidence,
                review_at=ext.suggested_review_date,
                review_reasoning=ext.review_reasoning,
            )
            saved_ids.append(f"#{note.id} {note.ticker}")
    finally:
        db.close()
    _pop_draft(draft_id)
    await q.edit_message_text(f"✅ Saved {len(saved_ids)} notes: " + ", ".join(saved_ids))


async def _do_reviewed(q, note_id: int) -> None:
    db = SessionLocal()
    try:
        note = storage.mark_reviewed(db, note_id)
    finally:
        db.close()
    if not note:
        await q.edit_message_text(templates.ERR_NOTE_NOT_FOUND)
        return
    await q.edit_message_text(f"✅ Reviewed #{note.id} {note.ticker}")


async def _do_postpone(q, note_id: int, days: int = 7) -> None:
    db = SessionLocal()
    try:
        note = storage.postpone(db, note_id, days=days)
    finally:
        db.close()
    if not note:
        await q.edit_message_text(templates.ERR_NOTE_NOT_FOUND)
        return
    new_date = templates._fmt_date_id(note.review_at)
    await q.edit_message_text(f"⏰ Postponed #{note.id} → {new_date}")


async def _do_invalid(q, note_id: int) -> None:
    db = SessionLocal()
    try:
        note = storage.mark_invalid(db, note_id)
    finally:
        db.close()
    if not note:
        await q.edit_message_text(templates.ERR_NOTE_NOT_FOUND)
        return
    await q.edit_message_text(f"💀 Marked invalid · #{note.id} {note.ticker}")


async def _do_update_prompt(q, note_id: int) -> None:
    await q.edit_message_text(
        f"Kirim update thesis untuk #{note_id} sebagai pesan baru.\n"
        f"Gw akan extract dan link sebagai follow-up."
    )
    # Note: full update-chain feature deferred to v2. For now user just
    # creates a new note manually.
