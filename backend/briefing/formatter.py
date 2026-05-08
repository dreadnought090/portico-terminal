"""Convert classified disclosure buckets into Telegram messages.

Output is a list of strings; each string becomes one Telegram message.
"""
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from backend.briefing.classifier import (
    CATEGORY_LABELS,
    MATERIAL_SUB_LABELS,
    MATERIAL_SUB_ORDER,
    PRIORITY_CATEGORIES,
    RENDER_ORDER,
    material_sub_classify,
)

MAX_NOTIFY_INLINE = 200   # effectively unbounded; sender hard-splits if message > 4000 chars
MAX_TITLE_CHARS = 75
MAX_COMPACT_TICKERS = 200

# Categories rendered as "label (N): TICKER1, TICKER2, ..." instead of one-bullet-per-item.
COMPACT_CATEGORIES = {"public_expose", "rups", "insider_trade"}

# Compact categories where each ticker is a clickable Markdown link to the
# underlying IDX PDF. The URLs are public idx.co.id paths (not localhost) so
# they open fine from mobile Telegram. Char overhead per ticker is ~100
# chars — sender.py hard-split will chunk if a block blows past the 4k cap.
COMPACT_WITH_LINKS = {"public_expose", "insider_trade", "rups"}


# ── Title normalization ─────────────────────────────────────────────

# Common boilerplate prefixes to strip (case-insensitive, longest first).
_BOILERPLATE_PREFIXES = [
    "Keterbukaan Informasi terkait Aksi Korporasi - ",
    "Keterbukaan Informasi Sehubungan Dengan ",
    "Penyampaian Bukti Iklan ",
    "Keterbukaan Informasi ",
    "Penyampaian Laporan ",
    "Ringkasan Risalah ",
    "Pemanggilan ",
    "Pemberitahuan ",
    "Penyampaian ",
    "Pengumuman ",
    "Laporan ",
    "Rencana ",
]

# Short-form replacements applied AFTER prefix strip.
_SUBSTITUTIONS = [
    (re.compile(r"Kuartal I\b", re.IGNORECASE), "Q1"),
    (re.compile(r"Kuartal II\b", re.IGNORECASE), "Q2"),
    (re.compile(r"Kuartal III\b", re.IGNORECASE), "Q3"),
    (re.compile(r"Kuartal IV\b", re.IGNORECASE), "Q4"),
    (re.compile(r"Laporan Keuangan", re.IGNORECASE), "LK"),
    (re.compile(r"\s*-\s*\d{8}$"), ""),                 # trailing date suffix "- 21042026"
    (re.compile(r"\s+"), " "),                          # collapse whitespace
]


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip()
    # Iteratively strip prefixes (a title might have "Penyampaian Bukti Iklan KETERBUKAAN..." = 2 levels)
    changed = True
    passes = 0
    while changed and passes < 3:
        changed = False
        passes += 1
        for prefix in _BOILERPLATE_PREFIXES:
            if t.lower().startswith(prefix.lower()):
                t = t[len(prefix):].strip()
                changed = True
                break
    for pat, repl in _SUBSTITUTIONS:
        t = pat.sub(repl, t)
    # Title-case only if all-caps (common in IDX) — preserve mixed-case
    if t.isupper() and len(t) > 4:
        t = t.title()
    return _escape_md(t.strip())


# Telegram Markdown (legacy, not V2) interprets these as formatting:
#   * bold/italic, _ italic, ` code, [ ] link
# Escape in title bodies so disclosures with raw asterisks/underscores don't
# break the parser. We do NOT escape in our intentional formatting (e.g. *BOLD*
# wrappers we add ourselves).
_MD_ESCAPE = str.maketrans({"*": "·", "_": "‿", "`": "ʼ", "[": "(", "]": ")"})


def _escape_md(text: str) -> str:
    return text.translate(_MD_ESCAPE) if text else text


def _truncate_word(text: str, limit: int = MAX_TITLE_CHARS) -> str:
    """Truncate at word boundary, append ellipsis if cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > limit * 0.6:
        cut = cut[:last_space]
    return cut.rstrip(" ,-;:") + "…"


# ── Message building ────────────────────────────────────────────────

def _greeting(today: date) -> str:
    months = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
              "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{today.day} {months[today.month]} {today.year}"


def _window_str() -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=7)  # WIB
    start = now - timedelta(hours=24)
    return f"{start.strftime('%d %b %H:%M')} → {now.strftime('%d %b %H:%M')} WIB"


def build_header(today: date, total_after_filter: int, buckets: dict, mode: str) -> str:
    lines = [
        f"📊 *IDX Briefing — {_greeting(today)}*",
        f"_Window: {_window_str()} · {total_after_filter} disclosures · mode: {mode}_",
    ]
    if not buckets:
        lines += ["", "Tidak ada disclosure signifikan hari ini."]
        return "\n".join(lines)

    priority_keys = [k for k in RENDER_ORDER if k in buckets and k in PRIORITY_CATEGORIES]
    routine_keys = [k for k in RENDER_ORDER if k in buckets and k not in PRIORITY_CATEGORIES]
    priority_count = sum(len(buckets[k]["items"]) for k in priority_keys)
    routine_count = sum(len(buckets[k]["items"]) for k in routine_keys)

    if priority_keys:
        lines += ["", f"🔥 *Actionable ({priority_count})*:"]
        for key in priority_keys:
            emoji, label = CATEGORY_LABELS.get(key, ("📄", key))
            n = len(buckets[key]["items"])
            lines.append(f"  {emoji} {label}: {n}")
    if routine_keys:
        lines += ["", f"📋 *Lainnya ({routine_count})*:"]
        for key in routine_keys:
            emoji, label = CATEGORY_LABELS.get(key, ("📄", key))
            n = len(buckets[key]["items"])
            lines.append(f"  {emoji} {label}: {n}")
    return "\n".join(lines)


def _format_compact_block(category_key: str, items: list[dict]) -> str:
    emoji, label = CATEGORY_LABELS.get(category_key, ("📄", category_key))
    n = len(items)
    with_links = category_key in COMPACT_WITH_LINKS
    # Group by ticker (so duplicates show ×N) and capture first link per ticker for click-through.
    counts: dict[str, int] = {}
    first_link: dict[str, str] = {}
    order: list[str] = []
    for it in items:
        t = it.get("ticker") or "?"
        if t not in counts:
            order.append(t)
            first_link[t] = it.get("link") or ""
        counts[t] = counts.get(t, 0) + 1

    def _render(t: str) -> str:
        suffix = f"×{counts[t]}" if counts[t] > 1 else ""
        if with_links and first_link.get(t):
            return f"[{t}{suffix}]({first_link[t]})"
        return f"{t}{suffix}"

    visible = [_render(t) for t in order[:MAX_COMPACT_TICKERS]]
    extra = len(order) - MAX_COMPACT_TICKERS
    suffix = f" (+{extra} lainnya)" if extra > 0 else ""
    return f"{emoji} *{label}* ({n}): {', '.join(visible)}{suffix}"


def _ticker_link(ticker: str, link: str) -> str:
    """Wrap ticker as a Markdown link to its IDX PDF. Falls back to `ticker`
    (backtick code) when no link is available so format stays consistent.

    URL-encodes the link so filenames with spaces or parentheses (e.g.
    'Cover Letter IDX XBRL 31 Mar 2026 (Unaudited).pdf') don't confuse the
    Markdown-to-HTML regex which naively stops at the first `)`.
    """
    if link:
        safe = quote(link, safe=":/?#[]@!$&'*+,;=%")
        return f"[{ticker}]({safe})"
    return f"`{ticker}`"


def _format_title_line(ticker: str, title: str, link: str = "") -> str:
    norm = normalize_title(title)
    return f"• {_ticker_link(ticker, link)} {_truncate_word(norm)}"


def _id_format(value: float, decimals: int = 1) -> str:
    """Format a float in Indonesian style: 1.234,5 (period thousand, comma decimal)."""
    raw = f"{value:,.{decimals}f}"  # "1,234.5" en-US style
    # swap separators via temp placeholder
    return raw.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fmt_compact_idr(amount: float) -> str:
    """Compact IDR formatting matching LLM template style (T/M/jt/rb)."""
    if not amount or amount <= 0:
        return ""
    a = abs(amount)
    if a >= 1e12:
        return f"Rp {_id_format(amount/1e12)}T"
    if a >= 1e9:
        return f"Rp {_id_format(amount/1e9)}M"
    if a >= 1e6:
        return f"Rp {_id_format(amount/1e6)}jt"
    return f"Rp {_id_format(amount, 0)}"


def _format_priority_block(category_key: str, items: list[dict]) -> str:
    emoji, label = CATEGORY_LABELS.get(category_key, ("📄", category_key))
    lines = [f"{emoji} *{label.upper()}* ({len(items)})"]
    for it in items:
        ticker = it.get("ticker", "?")
        title = normalize_title(it.get("title") or "")
        link = it.get("link") or ""
        summary = (it.get("_summary") or "").strip()
        # For LK items, append market cap + current price so user has size +
        # quote context alongside the financials. Format: "Cap: 700T (5.900)"
        # — period thousand separator on price.
        suffix = ""
        if category_key == "lap_keuangan":
            cap = it.get("_market_cap") or 0
            price = it.get("_last_price") or 0
            if cap > 0:
                cap_compact = _fmt_compact_idr(cap).replace("Rp ", "")  # drop Rp prefix
                if price > 0:
                    suffix = f"  ·  Cap: {cap_compact} ({_id_format(price, 0)})"
                else:
                    suffix = f"  ·  Cap: {cap_compact}"
        lines.append(f"\n*{_ticker_link(ticker, link)}* — {_truncate_word(title, 100)}{suffix}")
        if summary:
            lines.append(summary)
    return "\n".join(lines)


def _format_material_block(items: list[dict]) -> str:
    """Material Info with sub-grouping.

    Repetitive sub-categories (idx_permintaan — judulnya identik persis) get
    compacted to `label (N): TICKER1, TICKER2, ...`. Sub-groups with varied
    titles keep the bullet-per-item format so context is preserved.
    """
    emoji, label = CATEGORY_LABELS["material_info"]
    lines = [f"{emoji} *{label.upper()}* ({len(items)})"]
    # Sub-categories where titles are identical boilerplate across items —
    # showing each title line is pure waste. Compact to ticker list instead.
    COMPACT_SUB = {"idx_permintaan", "transaksi_afiliasi"}
    sub_buckets: dict[str, list[dict]] = {}
    for it in items:
        sub = material_sub_classify(it.get("title", ""))
        sub_buckets.setdefault(sub, []).append(it)
    for sub_key in MATERIAL_SUB_ORDER:
        sub_items = sub_buckets.get(sub_key, [])
        if not sub_items:
            continue
        sub_emoji, sub_label = MATERIAL_SUB_LABELS.get(sub_key, ("📄", sub_key))
        if sub_key in COMPACT_SUB:
            # Build clickable ticker list — first link per ticker wins.
            seen: dict[str, str] = {}
            order: list[str] = []
            for it in sub_items:
                t = it.get("ticker", "?")
                if t not in seen:
                    order.append(t)
                    seen[t] = it.get("link") or ""
            formatted = [f"[{t}]({seen[t]})" if seen[t] else t for t in order]
            lines.append(f"\n{sub_emoji} _{sub_label}_ ({len(sub_items)}): {', '.join(formatted)}")
        else:
            lines.append(f"\n{sub_emoji} _{sub_label} ({len(sub_items)})_")
            for it in sub_items[:MAX_NOTIFY_INLINE]:
                lines.append(_format_title_line(
                    it.get("ticker", "?"), it.get("title", ""), it.get("link") or "",
                ))
            if len(sub_items) > MAX_NOTIFY_INLINE:
                lines.append(f"  _(+{len(sub_items) - MAX_NOTIFY_INLINE} lainnya)_")
    return "\n".join(lines)


def _format_notify_block(category_key: str, items: list[dict]) -> str:
    if category_key in COMPACT_CATEGORIES:
        return _format_compact_block(category_key, items)
    emoji, label = CATEGORY_LABELS.get(category_key, ("📄", category_key))
    n = len(items)
    lines = [f"{emoji} *{label}* ({n})"]
    for it in items[:MAX_NOTIFY_INLINE]:
        lines.append(_format_title_line(
            it.get("ticker", "?"), it.get("title", ""), it.get("link") or "",
        ))
    if n > MAX_NOTIFY_INLINE:
        lines.append(f"_(+{n - MAX_NOTIFY_INLINE} lainnya)_")
    return "\n".join(lines)


def build_messages(today: date, total: int, buckets: dict, mode: str) -> list[str]:
    msgs = [build_header(today, total, buckets, mode)]
    if not buckets:
        return msgs

    if mode == "header_only":
        for key in RENDER_ORDER:
            if key not in buckets:
                continue
            # In header_only, Material also uses compact-ish block but with sub-grouping
            # to keep signal visible without LLM costs.
            if key == "material_info":
                msgs.append(_format_material_block(buckets[key]["items"]))
            elif key in COMPACT_CATEGORIES:
                msgs.append(_format_compact_block(key, buckets[key]["items"]))
            else:
                msgs.append(_format_notify_block(key, buckets[key]["items"]))
        return msgs

    # Full mode: priority → full block with LLM summary, notify → compact/short
    for key in RENDER_ORDER:
        if key not in buckets:
            continue
        bucket = buckets[key]
        if key == "insider_trade" and bucket.get("_aggregate_summary"):
            emoji, label = CATEGORY_LABELS["insider_trade"]
            msgs.append(
                f"{emoji} *{label.upper()}* ({len(bucket['items'])})\n"
                f"{bucket['_aggregate_summary']}"
            )
        elif key == "material_info" and bucket["priority"] == "priority":
            msgs.append(_format_material_block(bucket["items"]))
        elif bucket["priority"] == "priority":
            msgs.append(_format_priority_block(key, bucket["items"]))
        else:
            msgs.append(_format_notify_block(key, bucket["items"]))
    return msgs
