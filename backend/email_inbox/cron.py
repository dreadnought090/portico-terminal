"""Cron poller — multi-account inbox scan inside WIB window."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.database import SessionLocal
from backend.email_inbox import config, imap_client, parser
from backend.models import EmailTransaction

logger = logging.getLogger("email_inbox.cron")

# Per-account last-UID state file: {accounts: {user@x: {last_uid: N, updated_at: ...}}}
_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "email_inbox_state.json",
)


def _load_state() -> dict:
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
        return data.get("accounts", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(
                {"accounts": state, "updated_at": datetime.utcnow().isoformat()},
                f, indent=2,
            )
    except Exception:
        logger.exception("save_state failed")


def _confirm_buttons(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"etx_ok:{tx_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"etx_no:{tx_id}"),
    ]])


def _format_preview(tx: EmailTransaction, parsed: dict) -> str:
    action = (parsed.get("action") or "?").upper()
    ticker = parsed.get("ticker") or "?"
    lot = parsed.get("lot") or 0
    shares = parsed.get("shares") or (lot * 100)
    price = parsed.get("price_per_share") or 0
    total = parsed.get("total_value") or shares * price
    broker = parsed.get("broker") or "?"
    trade_date = parsed.get("trade_date") or "?"
    conf = parsed.get("confidence") or 0
    notes = parsed.get("notes") or ""

    emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"

    lines = [
        f"📧 Detected transaction (email)",
        f"",
        f"{emoji} {action} {ticker}",
        f"Lot: {lot} ({shares:,} shares)",
        f"Price: Rp {price:,.0f}",
        f"Total: Rp {total:,.0f}",
        f"Broker: {broker}",
        f"Date: {trade_date}",
        f"Confidence: {conf:.0%}",
    ]
    if notes:
        lines.append(f"Notes: {notes}")
    lines.append("")
    lines.append(f"From: {tx.email_from}")
    lines.append(f"Subject: {(tx.email_subject or '')[:80]}")
    if conf < 0.7:
        lines.append("")
        lines.append("⚠ Low confidence — review carefully sebelum confirm.")
    return "\n".join(lines)


async def _send_confirmation_dm(tx: EmailTransaction, parsed: dict) -> bool:
    """Dispatch DM via Ginger bot (if available) → fallback to subscription bot."""
    if config.dry_run():
        logger.info("[DRY] would DM tx#%d %s %s", tx.id, parsed.get("action"), parsed.get("ticker"))
        return True

    text = _format_preview(tx, parsed)
    markup = _confirm_buttons(tx.id)

    try:
        from backend.ginger import bot as ginger_bot
        from backend.ginger import config as ginger_config
        app = ginger_bot._app
        if app:
            await app.bot.send_message(
                chat_id=ginger_config.admin_chat_id(),
                text=text,
                reply_markup=markup,
            )
            return True
    except Exception:
        logger.exception("Ginger dispatch failed; trying fallback")

    try:
        from backend.subscription import bot as sub_bot
        from backend.subscription import config as sub_config
        app = sub_bot._app
        if app:
            await app.bot.send_message(
                chat_id=sub_config.admin_chat_id(),
                text=text,
                reply_markup=markup,
            )
            return True
    except Exception:
        logger.exception("Fallback bot dispatch failed too")

    return False


async def _scan_account(account: dict, state: dict) -> dict:
    """Scan one account. Mutates state[user] in place. Returns per-account stats."""
    user = account["user"]
    acc_state = state.get(user) or {}
    last_uid = int(acc_state.get("last_uid", 0))
    is_first_run = (last_uid == 0)

    logger.info("[%s] scan starting (last_uid=%d, first_run=%s)", user, last_uid, is_first_run)

    loop = asyncio.get_running_loop()
    try:
        messages = await loop.run_in_executor(
            None, lambda: list(imap_client.fetch_new_messages(account, since_uid=last_uid))
        )
    except Exception:
        logger.exception("[%s] fetch failed", user)
        return {"user": user, "scanned": 0, "dispatched": 0, "error": True}

    # First-run safety: skip LLM, just record max_uid baseline
    if is_first_run and len(messages) > 0:
        boot_max = max(m["uid"] for m in messages)
        state[user] = {"last_uid": boot_max, "updated_at": datetime.utcnow().isoformat()}
        logger.info("[%s] bootstrap: skipped %d emails (last_uid=%d)", user, len(messages), boot_max)
        return {"user": user, "status": "bootstrap", "scanned": len(messages)}

    dispatched = 0
    successfully_processed: set[int] = set()

    for msg in messages:
        uid = msg["uid"]
        db = SessionLocal()
        try:
            existing = db.query(EmailTransaction).filter(
                EmailTransaction.message_id == msg["message_id"]
            ).first()
            if existing:
                successfully_processed.add(uid)
                continue
        finally:
            db.close()

        body = msg["body_text"] or ""
        # If broker sent PDF attachment, decrypt + extract + append to body
        # (many ID brokers cuma kirim "konfirmasi terlampir" di body)
        attachments = msg.get("pdf_attachments") or []
        pdf_text_combined = ""
        pdf_meta_list = []
        if attachments:
            from backend.email_inbox.pdf_extract import extract_pdf_text
            for fname, raw in attachments:
                txt, meta = extract_pdf_text(raw, source_name=fname)
                pdf_meta_list.append({"file": fname, **meta})
                if txt:
                    pdf_text_combined += f"\n\n--- PDF: {fname} ---\n{txt}"
            if pdf_text_combined:
                body = (body + pdf_text_combined)[:30000]  # cap to keep LLM cost sane
        parsed = await parser.extract_transaction(msg["subject"], body)
        # Annotate parsed result with PDF status (helps debugging unparseable cases)
        if pdf_meta_list:
            parsed.setdefault("pdf_status", pdf_meta_list)

        db = SessionLocal()
        try:
            tx = EmailTransaction(
                message_id=msg["message_id"],
                email_subject=msg["subject"][:500],
                email_from=msg["from"][:200],
                email_received_at=msg["received_at"],
                raw_body_excerpt=body[:1000],
                extraction_raw=json.dumps(parsed, default=str)[:5000],
            )
            if parsed.get("is_transaction"):
                tx.extracted_action = parsed.get("action") or ""
                tx.extracted_ticker = parsed.get("ticker") or ""
                tx.extracted_lot = int(parsed.get("lot") or 0)
                tx.extracted_shares = int(parsed.get("shares") or 0)
                tx.extracted_price = float(parsed.get("price_per_share") or 0)
                tx.extracted_total_value = float(parsed.get("total_value") or 0)
                tx.extracted_broker = (parsed.get("broker") or "")[:100]
                from datetime import date as date_cls
                td = parsed.get("trade_date")
                if td:
                    try:
                        tx.extracted_trade_date = date_cls.fromisoformat(td)
                    except Exception:
                        pass
                tx.extraction_confidence = float(parsed.get("confidence") or 0)
                tx.status = "pending"
            else:
                tx.status = "rejected"
                tx.error_message = parsed.get("reason", "not a transaction email")
            db.add(tx)
            db.commit()
            db.refresh(tx)
            tx_id = tx.id
            should_dispatch = (tx.status == "pending")
        except Exception:
            logger.exception("[%s] DB insert failed (uid=%d)", user, uid)
            db.rollback()
            continue
        finally:
            db.close()

        successfully_processed.add(uid)

        if should_dispatch:
            tx_obj = _reload_tx(tx_id)
            if tx_obj is None:
                continue
            try:
                if await _send_confirmation_dm(tx_obj, parsed):
                    dispatched += 1
            except Exception:
                logger.exception("[%s] dispatch tx %d failed", user, tx_id)
            await asyncio.sleep(0.3)

    if successfully_processed:
        new_max = max(successfully_processed | {last_uid})
        state[user] = {"last_uid": new_max, "updated_at": datetime.utcnow().isoformat()}

    logger.info(
        "[%s] done: total=%d processed=%d dispatched=%d",
        user, len(messages), len(successfully_processed), dispatched,
    )
    return {
        "user": user, "scanned": len(messages),
        "processed": len(successfully_processed), "dispatched": dispatched,
    }


async def scan_new_emails() -> dict:
    """Cron entry. Loops all configured accounts inside WIB window."""
    if not config.is_configured():
        return {"status": "unconfigured"}

    if not config.is_in_window():
        start, end = config.poll_window()
        logger.debug("outside window (%d-%d WIB), skip", start, end)
        return {"status": "outside_window", "window": [start, end]}

    state = _load_state()
    results = []
    for account in config.accounts():
        results.append(await _scan_account(account, state))
    _save_state(state)

    return {
        "status": "ok",
        "accounts": len(results),
        "total_dispatched": sum(r.get("dispatched", 0) for r in results),
        "per_account": results,
    }


def _reload_tx(tx_id: int) -> EmailTransaction:
    db = SessionLocal()
    try:
        return db.query(EmailTransaction).filter(EmailTransaction.id == tx_id).first()
    finally:
        db.close()


def register_cron(scheduler) -> None:
    """Wire periodic email polling. Cron trigger inside WIB window only."""
    interval = config.poll_interval_min()
    start, end = config.poll_window()
    # APScheduler cron: hour='17-22', minute='*/30'
    scheduler.add_job(
        scan_new_emails, "cron",
        hour=f"{start}-{end}",
        minute=f"*/{interval}",
        timezone=config.WIB,
        id="email_inbox_poll",
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )
    logger.info("email inbox cron registered: every %d min, WIB %d-%d", interval, start, end)
