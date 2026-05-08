"""IMAP client — pull broker emails via stdlib imaplib (no extra dep)."""
from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import re
import ssl
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterator

logger = logging.getLogger("email_inbox.imap")


def _matches_broker_sender(from_addr: str, allowlist: list[str]) -> bool:
    """Match sender email against allowlist. Allowlist entries can be:
    - Full address: noreply@miraeasset.co.id
    - Domain: miraeasset.co.id (matches any sender at that domain)
    """
    addr = (from_addr or "").lower()
    for entry in allowlist:
        entry_l = entry.lower()
        if "@" in entry_l:
            if entry_l == addr:
                return True
        else:
            # Domain match — must be at @ boundary OR subdomain (.domain).
            # Prevents lookalike spoofing: "evil-mirae.co.id" should NOT match "mirae.co.id".
            if addr.endswith("@" + entry_l) or addr.endswith("." + entry_l):
                return True
    return False


def fetch_new_messages(account: dict, since_uid: int = 0) -> Iterator[dict]:
    """Yield broker-matched messages with UID > since_uid for one account.

    account dict keys: user, password, host, port, folder, brokers (list)
    Each yielded dict: {uid, message_id, subject, from, received_at, body_text, body_html}
    """
    host, port = account["host"], account["port"]
    user, pwd = account["user"], account["password"]
    folder = account.get("folder", "INBOX")
    senders = account["brokers"]

    ctx = ssl.create_default_context()
    try:
        mail = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    except Exception:
        logger.exception("IMAP connect failed (%s:%d)", host, port)
        return

    try:
        try:
            mail.login(user, pwd)
        except imaplib.IMAP4.error as e:
            logger.error("IMAP login failed: %s", e)
            return

        mail.select(folder, readonly=True)

        # Search for messages with UID > since_uid
        search_query = f"UID {since_uid + 1}:*" if since_uid else "ALL"
        try:
            typ, data = mail.uid("SEARCH", None, search_query)
        except Exception:
            logger.exception("IMAP search failed")
            return
        if typ != "OK":
            return

        uids = (data[0] or b"").split()
        if not uids:
            return

        # Cap to avoid massive backlog on first run
        uids = uids[-200:]

        for uid_b in uids:
            uid = int(uid_b)
            if uid <= since_uid:
                continue
            try:
                typ, msg_data = mail.uid("FETCH", str(uid).encode(), "(RFC822)")
            except Exception:
                logger.warning("IMAP fetch UID %d failed", uid)
                continue
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
            if not raw:
                continue

            try:
                msg = email.message_from_bytes(raw, policy=email.policy.default)
            except Exception:
                logger.exception("email parse UID %d failed", uid)
                continue

            from_full = msg.get("From", "")
            _, from_addr = parseaddr(from_full)
            if not _matches_broker_sender(from_addr, senders):
                continue  # skip non-broker

            message_id = (msg.get("Message-ID", "") or f"uid-{uid}").strip()
            subject = msg.get("Subject", "") or ""
            date_hdr = msg.get("Date", "")
            try:
                received_at = parsedate_to_datetime(date_hdr) if date_hdr else datetime.utcnow()
            except Exception:
                received_at = datetime.utcnow()

            body_text, body_html = _extract_body(msg)
            pdf_attachments = _extract_pdf_attachments(msg)

            yield {
                "uid": uid,
                "message_id": message_id,
                "subject": subject,
                "from": from_addr,
                "received_at": received_at,
                "body_text": body_text,
                "body_html": body_html,
                "pdf_attachments": pdf_attachments,  # list[(filename, bytes)]
            }
    finally:
        try:
            mail.logout()
        except Exception:
            pass


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _extract_pdf_attachments(msg) -> list[tuple[str, bytes]]:
    """Return list of (filename, raw_bytes) for PDF attachments. Cap 5 per email."""
    out = []
    if not msg.is_multipart():
        return out
    for part in msg.walk():
        if len(out) >= 5:
            break
        ctype = (part.get_content_type() or "").lower()
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename() or ""
        is_pdf = ctype == "application/pdf" or filename.lower().endswith(".pdf")
        if not is_pdf:
            continue
        if "attachment" not in disp and "inline" not in disp and not filename:
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload and len(payload) <= 10_000_000:  # 10MB cap per attachment
                out.append((filename or "attachment.pdf", payload))
        except Exception:
            logger.warning("failed to extract attachment %s", filename)
            continue
    return out


def _extract_body(msg) -> tuple[str, str]:
    """Return (text_body, html_body). Prefer text/plain; fallback to stripped HTML."""
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not body_text:
                try:
                    body_text = part.get_content()
                except Exception:
                    pass
            elif ctype == "text/html" and not body_html:
                try:
                    body_html = part.get_content()
                except Exception:
                    pass
    else:
        try:
            content = msg.get_content()
            ctype = msg.get_content_type()
            if ctype == "text/plain":
                body_text = content
            elif ctype == "text/html":
                body_html = content
        except Exception:
            pass

    if not body_text and body_html:
        # Strip HTML tags as fallback
        body_text = _HTML_TAG_RE.sub(" ", body_html)
        body_text = _WS_RE.sub(" ", body_text)

    return (body_text or "")[:8000], (body_html or "")[:12000]
