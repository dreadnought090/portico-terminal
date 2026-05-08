"""Claude-based email transaction extractor.

Indonesian broker confirmation emails vary widely (HTML tables, plain text).
LLM extraction handles all formats. Returns structured data + confidence.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date as date_cls

logger = logging.getLogger("email_inbox.parser")


SYSTEM_PROMPT = """You extract stock transaction details from Indonesian broker confirmation emails.

Brokers in Indonesia (IDX): Mirae Asset, Mandiri Sekuritas, BNI Sekuritas, BCA Sekuritas, IPOT, Phillip, Stockbit, Ajaib, Valbury, Kiwoom, OCBC NISP, BRI Danareksa, dll.

Common email patterns:
- Subject: "Konfirmasi Transaksi Beli/Jual", "Transaction Confirmation", "Bukti Eksekusi"
- Body contains: ticker (4-letter IDX code), action (BELI/JUAL or BUY/SELL), lot OR shares, price per share, total value, date

OUTPUT JSON only — no prose, no markdown fences:

{
  "is_transaction": true|false,
  "action": "buy"|"sell",
  "ticker": "BBCA",
  "lot": 5,                 // 1 lot = 100 shares (IDX standard)
  "shares": 500,            // = lot * 100
  "price_per_share": 5950,  // IDR per share
  "total_value": 2975000,   // IDR (gross or net, whichever email shows)
  "broker": "Mirae Asset",
  "trade_date": "2026-05-02",   // YYYY-MM-DD; if not visible, omit field
  "confidence": 0.0-1.0,
  "notes": "any caveat (e.g., 'partial fill', 'fee not included')"
}

If email is NOT a transaction confirmation (e.g., monthly statement, marketing, password reset):
{"is_transaction": false, "reason": "<why>"}

Rules:
- ticker MUST be 4-letter uppercase IDX code (BBCA, TLKM, etc.). If ambiguous, set is_transaction=false.
- If lot OR shares missing, compute from the other (1 lot = 100 shares).
- Date format YYYY-MM-DD strict. Omit if not in email.
- DO NOT invent fields. If a field is unclear, set null OR lower confidence."""


_client = None


def _get_client():
    """Lazy singleton — saves TLS handshake per call."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            return None
        _client = AsyncAnthropic(api_key=api_key)
    return _client


async def extract_transaction(subject: str, body: str) -> dict:
    """Returns dict with parsed structure or {"is_transaction": false, "reason": ...}."""
    client = _get_client()
    if client is None:
        return {"is_transaction": False, "reason": "ANTHROPIC_API_KEY missing or SDK unavailable"}

    user_msg = f"""Subject: {subject[:300]}

Body:
{body[:6000]}"""

    try:
        resp = await client.messages.create(
            model=os.getenv("EMAIL_PARSER_MODEL", "claude-haiku-4-5"),
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        return _parse_json(raw)
    except Exception as e:
        logger.exception("Claude email parse failed")
        return {"is_transaction": False, "reason": f"LLM error: {e}"}


def _parse_json(raw: str) -> dict:
    """Tolerant JSON parse — strip code fences if present."""
    candidate = raw.strip()
    if candidate.startswith("```"):
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", candidate)
        if m:
            candidate = m.group(1).strip()
    # First {...} block
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start:end + 1]
    try:
        obj = json.loads(candidate)
        # Validate required fields if is_transaction=true
        if obj.get("is_transaction"):
            ticker = (obj.get("ticker") or "").upper()
            if not re.match(r"^[A-Z]{3,6}$", ticker):
                return {"is_transaction": False, "reason": f"invalid ticker: {ticker!r}"}
            obj["ticker"] = ticker
            action = (obj.get("action") or "").lower()
            if action not in ("buy", "sell"):
                return {"is_transaction": False, "reason": f"invalid action: {action!r}"}
            obj["action"] = action
            # Compute lot/shares if one missing
            lot = obj.get("lot")
            shares = obj.get("shares")
            if lot and not shares:
                obj["shares"] = int(lot) * 100
            elif shares and not lot:
                obj["lot"] = int(shares) // 100
            # Parse trade_date if present
            td = obj.get("trade_date")
            if td and isinstance(td, str):
                try:
                    date_cls.fromisoformat(td)
                except ValueError:
                    obj["trade_date"] = None
        return obj
    except json.JSONDecodeError as e:
        return {"is_transaction": False, "reason": f"JSON parse failed: {e}"}
