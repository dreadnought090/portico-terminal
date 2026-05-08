"""Telegram Bot API direct sender — bypasses Hermes entirely."""
import html as _html
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

logger = logging.getLogger("mybloomberg.briefing")

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4000  # Telegram caps at 4096; leave headroom for markdown overhead

SENT_LOG_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "briefing_sent"


def _log_sent(messages: list[str]) -> None:
    """Persist sent batch to data/briefing_sent/{YYYY-MM-DDTHHMMSS}.md for audit."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        SENT_LOG_ROOT.mkdir(parents=True, exist_ok=True)
        path = SENT_LOG_ROOT / f"{ts}.md"
        with open(path, "w") as f:
            f.write(f"# Briefing sent at {ts}Z ({len(messages)} messages)\n\n")
            for i, m in enumerate(messages, 1):
                f.write(f"## Message {i} ({len(m)} chars)\n\n{m}\n\n---\n\n")
    except Exception as e:
        logger.warning("could not write sent log: %s", e)


# ── Markdown → HTML converter ───────────────────────────────────────
#
# Telegram legacy Markdown is fragile: any unbalanced `*`, `_`, `[`, or `(`
# from LLM output (e.g. "Rp[●]" redaction) breaks the whole-message parse.
# HTML is much more tolerant — we just escape <>& in text and emit tags for
# the formatting we actually need.

_LINK_RE = re.compile(r"\[([^\]]+?)\]\((https?://[^)]+)\)")   # [text](url)
_BOLD_DOUBLE_RE = re.compile(r"\*\*([^*\n]+?)\*\*")            # **text**
_BOLD_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")          # *text*
_ITALIC_RE = re.compile(r"(?<!\w)_([^_\n]+?)_(?!\w)")          # _text_
_CODE_RE = re.compile(r"`([^`\n]+?)`")                         # `text`

# Sentinel tokens used to shield tag output from HTML escaping. Chars in the
# Unicode private-use area won't occur in real disclosure text.
_S = ""  # opening bracket sentinel
_E = ""  # closing bracket sentinel


def _markdown_to_html(text: str) -> str:
    if not text:
        return text
    # 1. Temporarily replace our formatting markers with sentinels + raw content,
    #    so we can escape the REST of the text without also escaping our tags.
    def link_sub(m):
        inner = m.group(1).strip()
        url = m.group(2).strip()
        return f"{_S}a href=\"{url}\"{_E}{inner}{_S}/a{_E}"

    text = _LINK_RE.sub(link_sub, text)
    text = _BOLD_DOUBLE_RE.sub(lambda m: f"{_S}b{_E}{m.group(1)}{_S}/b{_E}", text)
    text = _BOLD_RE.sub(lambda m: f"{_S}b{_E}{m.group(1)}{_S}/b{_E}", text)
    text = _ITALIC_RE.sub(lambda m: f"{_S}i{_E}{m.group(1)}{_S}/i{_E}", text)
    text = _CODE_RE.sub(lambda m: f"{_S}code{_E}{m.group(1)}{_S}/code{_E}", text)

    # 2. Now escape <, >, & in the REMAINING text
    text = _html.escape(text, quote=False)

    # 3. Restore sentinels as real HTML tags
    text = text.replace(_S, "<").replace(_E, ">")
    return text


def _credentials() -> tuple[str, list[str]]:
    """Return (bot_token, [chat_id, ...]).

    Multiple destinations are supported via BRIEFING_CHAT_IDS (comma-separated)
    or combining BRIEFING_CHAT_ID (personal) with BRIEFING_CHANNEL_ID (channel
    broadcast). Channel IDs have the `-100XXXXXXXXXX` form.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in env")

    ids: list[str] = []
    multi = os.environ.get("BRIEFING_CHAT_IDS", "").strip()
    if multi:
        ids.extend(x.strip() for x in multi.split(",") if x.strip())
    single = os.environ.get("BRIEFING_CHAT_ID", "").strip() or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if single and single not in ids:
        ids.append(single)
    channel = os.environ.get("BRIEFING_CHANNEL_ID", "").strip()
    if channel and channel not in ids:
        ids.append(channel)

    if not ids:
        raise RuntimeError("No destination chat id configured (BRIEFING_CHAT_ID / BRIEFING_CHANNEL_ID / BRIEFING_CHAT_IDS)")
    return token, ids


DISCLAIMER_FOOTER = (
    "━━━━━━━━━━━━━━━\n"
    "_⚠️ BUKAN REKOMENDASI INVESTASI. Data IDX publik, disusun oleh AI. "
    "Keputusan investasi tanggung jawab Anda sepenuhnya._"
)


def _split_long(text: str) -> list[str]:
    """Split a single long message into pieces under MAX_MESSAGE_CHARS.

    Tries paragraph boundaries first, then line boundaries for paragraphs that
    are themselves too long, and finally hard char-splits as last resort so
    nothing ever gets dropped.
    """
    if len(text) <= MAX_MESSAGE_CHARS:
        return [text]

    def _split_long_line(line: str) -> list[str]:
        """Split a single overly-long line at comma boundaries (safe for compact
        ticker lists like '[AAA](u), [BBB](u), ...'). Falls back to hard char
        split if no comma fits. Never splits inside a `[...]` or `(...)` group."""
        out: list[str] = []
        remaining = line
        while len(remaining) > MAX_MESSAGE_CHARS:
            # Scan backward from the cap for a ", " that's outside any [] or ().
            cut = -1
            depth_bracket = 0
            depth_paren = 0
            for i, ch in enumerate(remaining[:MAX_MESSAGE_CHARS]):
                if ch == "[":
                    depth_bracket += 1
                elif ch == "]":
                    depth_bracket = max(0, depth_bracket - 1)
                elif ch == "(":
                    depth_paren += 1
                elif ch == ")":
                    depth_paren = max(0, depth_paren - 1)
                elif ch == "," and depth_bracket == 0 and depth_paren == 0:
                    cut = i  # remember latest safe comma
            if cut > MAX_MESSAGE_CHARS * 0.3:
                out.append(remaining[:cut + 1].rstrip())
                remaining = remaining[cut + 1:].lstrip()
            else:
                # No safe comma found — fall back to hard char cut.
                out.append(remaining[:MAX_MESSAGE_CHARS])
                remaining = remaining[MAX_MESSAGE_CHARS:]
        if remaining:
            out.append(remaining)
        return out

    def _split_paragraph(para: str) -> list[str]:
        if len(para) <= MAX_MESSAGE_CHARS:
            return [para]
        # paragraph too long — split by line, then by comma for long lines
        out, cur = [], ""
        for line in para.split("\n"):
            if len(cur) + len(line) + 1 > MAX_MESSAGE_CHARS:
                if cur:
                    out.append(cur.rstrip())
                if len(line) > MAX_MESSAGE_CHARS:
                    out.extend(_split_long_line(line))
                    cur = ""
                else:
                    cur = line + "\n"
            else:
                cur += line + "\n"
        if cur.strip():
            out.append(cur.rstrip())
        return out

    chunks = []
    cur = ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > MAX_MESSAGE_CHARS:
            if cur:
                chunks.append(cur.rstrip())
            cur = ""
            for piece in _split_paragraph(para):
                if len(cur) + len(piece) + 2 > MAX_MESSAGE_CHARS:
                    if cur:
                        chunks.append(cur.rstrip())
                    cur = piece + "\n\n"
                else:
                    cur += piece + "\n\n"
        else:
            cur += para + "\n\n"
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


def _send_one(url: str, chat_id: str, piece: str) -> tuple[bool, int | None]:
    """Send a single piece to one chat. Returns (success, message_id_or_None)."""
    html_body = _markdown_to_html(piece)
    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": html_body,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if r.status_code == 200:
            try:
                msg_id = r.json().get("result", {}).get("message_id")
            except Exception:
                msg_id = None
            return True, msg_id
        # HTML parse is very tolerant. Plain-text fallback if rejected.
        fallback = re.sub(r"\[([^\]]+?)\]\([^)]+\)", r"\1", piece)
        fallback = re.sub(r"\*+([^*\n]+?)\*+", r"\1", fallback)
        fallback = re.sub(r"`([^`]+)`", r"\1", fallback)
        r2 = requests.post(
            url,
            json={"chat_id": chat_id, "text": fallback, "disable_web_page_preview": True},
            timeout=15,
        )
        if r2.status_code == 200:
            logger.warning("telegram html failed for %s, plain-text ok: %s", chat_id, r.text[:150])
            try:
                msg_id = r2.json().get("result", {}).get("message_id")
            except Exception:
                msg_id = None
            return True, msg_id
        logger.warning("telegram send failed to %s: %s %s", chat_id, r.status_code, r.text[:200])
        return False, None
    except Exception as e:
        logger.warning("telegram send error to %s: %s", chat_id, e)
        return False, None


def _pin_message(token: str, chat_id: str, message_id: int) -> bool:
    """Pin a message in the given chat. Best-effort — silent fail."""
    try:
        r = requests.post(
            f"{TELEGRAM_API}/bot{token}/pinChatMessage",
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": True},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        logger.warning("pin failed for %s msg %s: %s %s", chat_id, message_id, r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("pin error: %s", e)
    return False


def _channel_chat_id() -> str | None:
    """Channel id used for pinning — only the BRIEFING_CHANNEL_ID env var."""
    cid = os.environ.get("BRIEFING_CHANNEL_ID", "").strip()
    return cid or None


def send_messages(messages: Iterable[str], pin_first_in_channel: bool = False,
                  with_disclaimer: bool = True) -> int:
    """Send a sequence of messages to all configured Telegram destinations.

    Returns total deliveries counted as (messages × destinations).

    `pin_first_in_channel`: if True, after sending, pin the first successfully-
    sent message that landed in BRIEFING_CHANNEL_ID. Used by the daily 08:00
    recap so subscribers see the latest digest pinned at top of channel.
    """
    token, chat_ids = _credentials()
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    msg_list = list(messages)
    if msg_list and with_disclaimer:
        msg_list.append(DISCLAIMER_FOOTER)
    _log_sent(msg_list)  # audit trail before we hit the wire

    channel_id = _channel_chat_id() if pin_first_in_channel else None
    first_channel_msg_id: int | None = None

    sent = 0
    for raw in msg_list:
        for piece in _split_long(raw):
            for chat_id in chat_ids:
                ok, msg_id = _send_one(url, chat_id, piece)
                if ok:
                    sent += 1
                    if (
                        channel_id is not None
                        and first_channel_msg_id is None
                        and str(chat_id) == channel_id
                        and msg_id is not None
                    ):
                        first_channel_msg_id = msg_id
                time.sleep(0.15)
            time.sleep(0.25)

    if first_channel_msg_id is not None:
        _pin_message(token, channel_id, first_channel_msg_id)
    return sent
