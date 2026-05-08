"""Merriot LLM extractor — raw NL → structured ThesisExtraction.

Uses Claude Haiku 4.5. ~$0.002/call. Pydantic validates output; 2-attempt
retry then regex fallback so user input is never lost.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, date as date_cls
from typing import Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.merriot.config import WIB, llm_model

logger = logging.getLogger("merriot.extractor")


# ── Output schema ─────────────────────────────────────────────────────

class ThesisExtraction(BaseModel):
    ticker: Union[str, list[str]]
    thesis_type: str = Field(default="other")
    thesis_direction: str = Field(default="neutral")
    key_points: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    suggested_review_date: date_cls
    review_reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("key_points")
    @classmethod
    def _kp_len(cls, v):
        return [s[:100] for s in v]

    @field_validator("tags")
    @classmethod
    def _tags_lower(cls, v):
        return [t.lower().strip() for t in v if t.strip()]


class ExtractionError(BaseModel):
    error: str
    suggestion: str = ""


# ── Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You extract structured stock-thesis data from Indonesian retail-investor notes (mixed ID/EN, casual register, "bocoran" = tip).

TASK
Given a raw note + today_iso + portfolio/watchlist tickers, return ONE JSON object matching <output_schema>. No prose, no markdown fences, no trailing comments.

INDONESIAN CONTEXT
- "bocoran" = leak/tip; "cek lagi" = re-check; "wait & see" / "w&s" = monitor
- Time: "X minggu/bulan/hari" = X weeks/months/days; "akhir bulan" = month-end; "RUPS" = AGM
- Tickers are 4-letter IDX codes (BBCA, TLKM). Disambiguate partial matches against user's portfolio+watchlist.

<output_schema>
{
  "ticker": "string | string[]",
  "thesis_type": "earnings_estimate|valuation|catalyst|sentiment|risk_flag|exit|negative_thesis|other",
  "thesis_direction": "bullish|bearish|neutral|exit",
  "key_points": ["<=100 char, preserve user wording", "1-5 items"],
  "tags": ["lowercase", "1-5 items"],
  "suggested_review_date": "YYYY-MM-DD",
  "review_reasoning": "1 sentence explaining date math",
  "confidence": 0.0-1.0,
  "warnings": ["multi_ticker|ambiguous_ticker|vague_dates|no_numbers|stale_source|..."]
}
</output_schema>

FAILURE MODE — STRICT
ONLY return error if LITERALLY no 4-letter uppercase token exists in the input.

CRITICAL RULES (no exceptions):
1. ANY [A-Z]{4} token in the input IS a valid IDX ticker. Extract it. Period.
2. Portfolio/watchlist is for DISAMBIGUATION only ("BB" → BBCA), NOT a whitelist.
3. "Brand-sounding" / "common-word-looking" tickers are STILL valid IDX tickers.
   IDX has 900+ listed companies including:
   - COCO (Wahana Pronatural), GOTO (GoTo Gojek-Tokopedia), BUKA (Bukalapak),
     BUMI (Bumi Resources), DATA (Sinergi Inti Andalan), MDIA (Intermedia
     Capital), CASH (Cashlez Worldwide), TEBE (Trimegah Bangun Persada),
     SINI (Singaraja Putra), PYFA (Pyridam Farma), CLPI (Colorpak Indonesia),
     NIKL (Pelat Timah Nusantara), PBSA (Paramita Bangun Sarana), etc.
   - Many tickers LOOK like brand names, slang, or common words. They are
     STILL real IDX tickers. DO NOT reject because "doesn't sound like a ticker".
4. DO NOT reject because "ticker not in user's portfolio". That's wrong reasoning.
5. DO NOT reject because "looks like a brand name". Brands ARE companies; many
   are listed.

Only return error if LITERALLY zero [A-Z]{4} tokens in input:
{"error":"no_ticker_detected","suggestion":"<saran dalam Bahasa Indonesia santai>"}

The suggestion field MUST be Bahasa Indonesia santai (pakai "kamu", BUKAN "Anda").

REVIEW DATE RULES (apply in order, stop at first match)
1. Explicit duration ("3 minggu", "1 bulan") → today + that duration
2. Named event ("after earnings", "RUPS bulan depan") → event date + 0-3d buffer; if quarter unknown, today+21d
3. Vague ("wait & see", "monitor") → today + 14d
4. Exit/done thesis → today + 90d (post-mortem review)
5. Default → today + 30d
Always populate the field. Explain in review_reasoning.

CONFIDENCE RUBRIC
- 0.9+ : explicit ticker + numbers + clear direction + clear timeframe
- 0.7-0.9: ticker clear, some inference on type/date
- 0.5-0.7: ticker clear but thesis vague OR multi-ticker
- <0.5: heavy inference; add warnings

RULES
- NEVER invent numbers. If user wrote no number, don't add one.
- key_points preserve user's mixed ID/EN phrasing.
- Multi-ticker: ticker as array, warnings include "multi_ticker".
- Negative thesis / exit notes are VALID — capture them, don't refuse.
- Vague thesis with ticker present is VALID — extract with low confidence
  (0.4-0.6), don't refuse. User wants to remember it for review.
- "Salim masuk", "Toto Sugiri masuk", "akuisisi X by Y", "rumor merger" are
  all valid CATALYSTS even without numbers. Type=catalyst, direction=bullish
  unless context says bearish.
- Source attribution (informant/group name): include in key_points AND tags
  (e.g., "info dari pak Budi" → tags include "source-budi").

EXAMPLES

Input: today=2026-04-29; note="BBCA bocoran channel A, rev Q1 +15% YoY. Target Rp 12k pakai PE 20x EPS 600. Cek lagi after earnings ~3 minggu"
Output: {"ticker":"BBCA","thesis_type":"earnings_estimate","thesis_direction":"bullish","key_points":["Rev Q1 +15% YoY (sumber: channel A)","Target Rp 12.000 @ PE 20x EPS 600"],"tags":["bocoran","earnings","valuation"],"suggested_review_date":"2026-05-20","review_reasoning":"User said '~3 minggu', today+21d","confidence":0.9,"warnings":[]}

Input: today=2026-04-29; note="September MDIA Salim dan toto sugiri masuk"
Output: {"ticker":"MDIA","thesis_type":"catalyst","thesis_direction":"bullish","key_points":["Salim masuk MDIA","Toto Sugiri masuk MDIA"],"tags":["catalyst","insider","ownership"],"suggested_review_date":"2026-09-30","review_reasoning":"User said 'September' → review akhir September","confidence":0.65,"warnings":["no_target_price"]}

Input: today=2026-05-06; note="SMAR wacana mau diliquidkan lalu rerating, info dari ko ed"
Output: {"ticker":"SMAR","thesis_type":"catalyst","thesis_direction":"bullish","key_points":["Wacana likuidasi SMAR → potensi rerating","Sumber: ko Ed"],"tags":["catalyst","liquidation","rerating","source-ed"],"suggested_review_date":"2026-06-05","review_reasoning":"Wacana belum confirm → wait & see ~30 hari","confidence":0.6,"warnings":["rumor","unconfirmed"]}

Input: today=2026-05-07; note="COCO mau diinject momogi, estimasi laba 3T setahun, marketcap coco 1T 1 year reminder ya"
Output: {"ticker":"COCO","thesis_type":"catalyst","thesis_direction":"bullish","key_points":["COCO mau diinject Momogi","Estimasi laba 3T/tahun","Market cap COCO ~1T (mispriced)"],"tags":["catalyst","injection","mispriced","momogi"],"suggested_review_date":"2027-05-07","review_reasoning":"User said '1 year reminder' → today+365d","confidence":0.7,"warnings":["unconfirmed"]}

Input: today=2026-04-29; note="Si X bilang tunggu sampai bottom Mei"
Output: {"error":"no_ticker_detected","suggestion":"Tambahkan kode saham 4-huruf (mis. BBCA) di awal catatan"}"""


USER_TEMPLATE = """today_iso={today}
portfolio={portfolio}
watchlist={watchlist}
note=\"\"\"{note}\"\"\""""


# ── Public API ────────────────────────────────────────────────────────

async def extract(
    note: str,
    portfolio_tickers: list[str] | None = None,
    watchlist_tickers: list[str] | None = None,
    today: date_cls | None = None,
) -> Union[ThesisExtraction, ExtractionError]:
    """Extract structured thesis. Ticker detection is regex-deterministic; LLM
    only structures thesis fields. LLM cannot reject if regex finds a ticker.
    """
    today = today or datetime.now(WIB).date()
    note_clean = (note or "").strip()

    # Stage 1: deterministic ticker extraction. LLM never overrides this.
    regex_tickers = _regex_extract_tickers(note_clean)

    # Build LLM context — inject regex result as authoritative
    user_msg = USER_TEMPLATE.format(
        today=today.isoformat(),
        portfolio=json.dumps(portfolio_tickers or []),
        watchlist=json.dumps(watchlist_tickers or []),
        note=note_clean[:2000],
    )
    if regex_tickers:
        user_msg += (
            f"\n\nDETECTED_TICKERS={json.dumps(regex_tickers)}"
            "\nThese are pre-validated 4-letter IDX tickers from the note. "
            "ALWAYS use one of these as the ticker field. "
            "DO NOT return no_ticker_detected — regex already confirmed they exist."
        )

    raw = await _call_claude(user_msg, max_attempts=2)
    if raw is None:
        return _regex_fallback(note_clean, today)

    parsed = _try_parse(raw)

    # Safety override: LLM cannot say no_ticker_detected if regex found one
    if isinstance(parsed, ExtractionError) and parsed.error == "no_ticker_detected" and regex_tickers:
        logger.warning(
            "LLM tried to reject but regex found %s — overriding with regex fallback + LLM context",
            regex_tickers,
        )
        return _regex_fallback(note_clean, today)

    if parsed is not None:
        return parsed
    return _regex_fallback(note_clean, today)


async def extract_with_vision(
    image_bytes: bytes,
    image_media_type: str = "image/jpeg",
    caption: str = "",
    portfolio_tickers: list[str] | None = None,
    watchlist_tickers: list[str] | None = None,
    today: date_cls | None = None,
) -> Union[ThesisExtraction, ExtractionError]:
    """Vision extraction — for screenshots of charts, Telegram messages, slides.

    Uses Sonnet 4.6 (better OCR + chart reasoning than Haiku). Cost ~$0.01/image
    vs Haiku $0.002. Caption is included as additional context if provided.
    """
    import base64

    today = today or datetime.now(WIB).date()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY missing — vision disabled")
        return ExtractionError(error="api_key_missing", suggestion="Set ANTHROPIC_API_KEY di .env")

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return ExtractionError(error="sdk_missing", suggestion="pip install anthropic")

    client = AsyncAnthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    text_payload = USER_TEMPLATE.format(
        today=today.isoformat(),
        portfolio=json.dumps(portfolio_tickers or []),
        watchlist=json.dumps(watchlist_tickers or []),
        note=(caption or "").strip()[:1000] or "[image-only — extract from image]",
    ) + """

VISION CONTEXT
Image is a SCREENSHOT of TEXT — almost always a chat conversation
(WhatsApp / Telegram / Discord) or a text-info snippet where someone shares
fundamentals/news/tips about a stock. NEVER a price chart.

Common patterns:
- Chat with a named source: "info dari pak Budi: BBCA EPS Q1 28..."
- Forwarded text-only message about earnings, valuation, catalyst
- Summary of fundamentals (Rev, NPAT, EPS, target price)

Rules:
1. Identify the SUBSTANTIVE content. Skip greetings, stickers, "wkwk", emoji-only,
   metadata (timestamps, online status).
2. **Capture source attribution** when visible — sender name, group name,
   "info dari [X]", "channel [Y]". Add to key_points (e.g., "EPS Q1 = 28 (sumber:
   pak Budi)") AND to tags as "source-budi" / "grup-X".
3. Multi-message conversations: join the relevant messages into key_points
   chronologically. Don't include unrelated chitchat.
4. Forwarded message inside chat → extract; warn 'forwarded'.
5. Multiple stocks discussed → multi-ticker (warnings: multi_ticker).
6. **Caption** (text user typed when sending the photo) takes precedence —
   if user wrote "BBCA cek 1 bulan", honor that; image is supporting context.

CRITICAL: Only extract what's literally visible in the image text. Don't infer
numbers not shown. Don't guess sender names if not legible."""

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = await client.messages.create(
                model="claude-sonnet-4-6",  # vision-capable, better OCR than Haiku
                max_tokens=800,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": image_media_type, "data": b64,
                        }},
                        {"type": "text", "text": text_payload},
                    ],
                }],
            )
            raw = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
            parsed = _try_parse(raw)
            if parsed is not None:
                return parsed
            last_err = ValueError(f"vision parse failed: {raw[:200]}")
        except Exception as e:
            last_err = e
            logger.warning("vision attempt %d failed: %s", attempt + 1, e)

    logger.error("vision extraction failed: %s", last_err)
    return ExtractionError(
        error="vision_failed",
        suggestion="Coba kirim ulang sebagai text, atau retry. Detail: " + str(last_err)[:100],
    )


# ── Internals ─────────────────────────────────────────────────────────

async def _call_claude(user_msg: str, max_attempts: int = 2) -> Optional[str]:
    """Returns raw response text, or None on hard failure."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY missing — extractor disabled")
        return None

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.exception("anthropic SDK missing")
        return None

    client = AsyncAnthropic(api_key=api_key)

    last_err: Exception | None = None
    msg_for_attempt = user_msg
    for attempt in range(max_attempts):
        try:
            resp = await client.messages.create(
                model=llm_model(),
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": msg_for_attempt}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
            return text
        except Exception as e:
            last_err = e
            logger.warning("LLM call attempt %d failed: %s", attempt + 1, e)
            # Stricter retry instruction
            msg_for_attempt = (
                user_msg
                + "\n\nReturn ONLY the JSON object on a single line. No markdown, no prose."
            )
    logger.error("LLM extraction failed after %d attempts: %s", max_attempts, last_err)
    return None


def _extract_first_json_object(s: str) -> Optional[str]:
    """Walk braces to find the first balanced JSON object.

    Greedy regex `\\{[\\s\\S]*\\}` would grab from first `{` to LAST `}`, which
    breaks if Claude emits trailing prose. Brace-depth scan is robust.
    """
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _try_parse(raw: str) -> Optional[Union[ThesisExtraction, ExtractionError]]:
    """Best-effort JSON parse + Pydantic validation."""
    candidate = raw.strip()
    # Strip code fences if Claude added them despite instructions
    if candidate.startswith("```"):
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", candidate)
        if m:
            candidate = m.group(1).strip()
    blob = _extract_first_json_object(candidate)
    if not blob:
        return None
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if "error" in obj:
        try:
            return ExtractionError(**obj)
        except ValidationError:
            return None
    try:
        return ThesisExtraction(**obj)
    except ValidationError as e:
        logger.warning("Pydantic rejected LLM output: %s", e)
        return None


_TICKER_RE = re.compile(r"\b([A-Z]{4})\b")


def _regex_extract_tickers(text: str) -> list[str]:
    """Deterministic ticker detection. Strategy:
    1. Find all [A-Z]{4} ALL CAPS tokens.
    2. If IDX registry available: prioritize registry-validated candidates first;
       words like JUAL/INFO/BACK get pushed back (registry-valid first), but
       still kept as fallback if registry has none.
    3. If registry empty/unavailable: take all matches as-is.
    """
    if not text:
        return []
    raw_matches = []
    for m in _TICKER_RE.findall(text):
        if m not in raw_matches:
            raw_matches.append(m)
    if not raw_matches:
        return []
    raw_matches = raw_matches[:8]  # cap before registry lookup

    # Prefer registry-validated. Fail-soft: if registry import/query errors,
    # fall back to raw matches.
    try:
        from backend.idx_registry import is_valid_ticker
        valid = [t for t in raw_matches if is_valid_ticker(t)]
        unknown = [t for t in raw_matches if t not in valid]
        # Validated first, unknown after (still kept — might be new IPO not yet refreshed)
        ordered = valid + unknown
    except Exception:
        ordered = raw_matches

    return ordered[:5]


def _regex_fallback(note: str, today: date_cls) -> Union[ThesisExtraction, ExtractionError]:
    """Cheap last-resort extraction. Always succeeds if any 4-letter ticker exists."""
    text = (note or "").strip()
    if not text:
        return ExtractionError(error="empty_input", suggestion="Kirim teks thesis dulu")
    tickers = _regex_extract_tickers(text)
    if not tickers:
        return ExtractionError(
            error="no_ticker_detected",
            suggestion="Tambahkan kode saham 4-huruf (mis. BBCA) di catatan",
        )
    return ThesisExtraction(
        ticker=tickers[0] if len(tickers) == 1 else tickers,
        thesis_type="other",
        thesis_direction="neutral",
        key_points=[text[:100]],
        tags=["unprocessed"],
        suggested_review_date=today + timedelta(days=30),
        review_reasoning="LLM unavailable — default 30 hari",
        confidence=0.3,
        warnings=(["multi_ticker"] if len(tickers) > 1 else []) + ["llm_failed", "regex_fallback", "manual_review_needed"],
    )
