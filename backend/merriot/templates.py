"""Merriot message templates — centralized copy for easy editing.

Voice: Merriot — Princess of Caerleon, younger sister of King Cai. Tomboy
Rune Knight, hobi berburu, ramah ke semua orang tapi sesekali sassy. Tone:
santai-energik (BUKAN "lu/gw"), pakai "kamu" / imperative netral, action
verbs (bidik/kejar/buruan/intip), interjeksi ringan boleh ("nih", "yuk",
"deh"). Hangat tapi gak lebay. Hunter metaphors fit konteks investasi.
"""
from __future__ import annotations

from datetime import date as date_cls
from backend.models import ThesisNote


WELCOME = """Halo! Aku Merriot.

Catatan thesis sahammu — biar gak lolos pas waktunya review. Lemparin aja
informasinya, sisanya aku yang bidik.

Cara pakai:
1. Ketik teks bebas. Misal:
   "BBCA bocoran channel A, target 12k pakai PE 20x. Cek ulang 3 minggu"
2. Atau kirim screenshot chat / info teks — di-extract pakai vision.

Aku ekstrak ticker, target, sama tanggal review otomatis. Kamu tinggal Save.

Commands:
/tickers — semua saham yang udah ada thesis-nya
/all — semua catatan (bisa filter: /all pending)
/due — note yang due minggu ini
/recent — 10 catatan terakhir
/thesis BBCA — semua note ticker BBCA
/help — info lengkap

Yuk, lempar thesis pertama.

📡 Privacy: teks-mu diparse pakai Claude (Anthropic) dan lewat server Telegram. Hindari info yang super sensitif ya."""


HELP = """Merriot — pemburu thesis saham.

Kirim teks bebas atau screenshot — aku ekstrak inti-nya.

Commands:
/tickers — semua saham yang udah punya thesis
/all — semua catatan (filter: /all pending|reviewed|invalid)
/timeline — timeline review chronological (closest first)
/due — note yang due minggu ini
/recent — 10 catatan terakhir
/thesis BBCA — note untuk satu ticker
/del <id> — hapus note
/help — pesan ini

Setelah save, aku kirim reminder otomatis:
• 7 hari sebelum review (heads-up)
• 1 hari sebelum review (preview)
• Hari-H (full + tombol Reviewed/Postpone/Update/Invalid)

Quick commands (tanpa slash juga bisa):
• del 1 / hapus 1 — hapus note #1
• reviewed 2 / done 2 — tandai sudah review
• tunda 3 / postpone 3 — geser review +7 hari
• invalid 4 / batal 4 — tandai thesis gagal

Append info ke note existing:
• add 1 info dari pak Benny: target naik 2k
• +MDIA info baru dari pak Roger
• tambah BBCA Q1 EPS keluar 28
   (kalau pakai ticker, otomatis ke note pending terbaru
    untuk ticker itu)

Tap tombol di reminder buat respond cepat. Praktis, gak ribet."""


def fmt_extraction_preview(extraction, draft_id: str) -> str:
    """Confirmation preview after LLM extract."""
    if isinstance(extraction.ticker, list):
        ticker_str = ", ".join(extraction.ticker)
    else:
        ticker_str = extraction.ticker
    type_label = {
        "earnings_estimate": "Earnings est.",
        "valuation": "Valuation",
        "catalyst": "Catalyst",
        "sentiment": "Sentiment",
        "risk_flag": "Risk flag",
        "exit": "Exit",
        "negative_thesis": "Negative",
        "other": "Other",
    }.get(extraction.thesis_type, extraction.thesis_type)
    direction = {
        "bullish": "🟢 Bullish",
        "bearish": "🔴 Bearish",
        "neutral": "⚪ Neutral",
        "exit": "🚪 Exit",
    }.get(extraction.thesis_direction, extraction.thesis_direction)

    lines = [
        "Tangkapan aku begini — fix?",
        "",
        f"Ticker: {ticker_str}",
        f"Tipe: {type_label} · {direction}",
    ]
    if extraction.key_points:
        lines.append("")
        lines.append("Key points:")
        for kp in extraction.key_points:
            lines.append(f"• {kp}")
    if extraction.tags:
        lines.append("")
        lines.append("Tags: " + " ".join("#" + t for t in extraction.tags))
    lines.append("")
    lines.append(f"Review: {_fmt_date_id(extraction.suggested_review_date)}")
    if extraction.review_reasoning:
        lines.append(f"  ({extraction.review_reasoning})")
    if extraction.confidence < 0.7:
        lines.append("")
        lines.append(f"⚠ Confidence rendah ({extraction.confidence:.0%}). Cek lagi sebelum save.")
    if extraction.warnings:
        lines.append(f"⚠ {', '.join(extraction.warnings)}")
    return "\n".join(lines)


def fmt_saved_confirmation(note: ThesisNote) -> str:
    return f"✅ Disimpan #{note.id} {note.ticker} — review {_fmt_date_id(note.review_at)}"


def fmt_reminder_h7(note: ThesisNote) -> str:
    body_excerpt = (note.body or "")[:200]
    created = note.created_at.strftime("%-d %b") if note.created_at else "?"
    return (
        f"Heads up — review {note.ticker} 7 hari lagi ({_fmt_date_id(note.review_at)}).\n\n"
        f"Thesis (catatan {created}): {body_excerpt}\n\n"
        f"Mau prep dari sekarang?"
    )


def fmt_reminder_h1(note: ThesisNote) -> str:
    lines = [f"Besok review {note.ticker} ({_fmt_date_id(note.review_at)}).", ""]
    if note.key_points:
        for kp in note.key_points:
            lines.append(f"• {kp}")
    else:
        lines.append((note.body or "")[:200])
    lines.append("")
    lines.append("Sempetin intip harga & berita ya.")
    return "\n".join(lines)


def fmt_reminder_h0(note: ThesisNote) -> str:
    created = note.created_at.strftime("%-d %b %Y") if note.created_at else "?"
    lines = [
        f"🔔 Review hari ini — {note.ticker}",
        "",
        f"Catatan asli ({created}):",
        f"\"{(note.body or '')[:500]}\"",
        "",
    ]
    if note.key_points:
        lines.append("Key points:")
        for kp in note.key_points:
            lines.append(f"• {kp}")
        lines.append("")
    if note.tags:
        lines.append("Tags: " + " ".join("#" + t for t in note.tags))
        lines.append("")
    lines.append("Thesis-nya masih nyala?")
    return "\n".join(lines)


def fmt_thesis_list(notes: list[ThesisNote], ticker: str) -> str:
    if not notes:
        return f"Belum ada note untuk {ticker.upper()}. Lempar info-nya kalau ada."
    lines = [f"{ticker.upper()} — {len(notes)} notes", ""]
    for n in notes[:20]:
        status_icon = {
            "pending": "⏳",
            "reviewed": "✅",
            "invalid": "💀",
        }.get(n.status, "•")
        created = n.created_at.strftime("%-d %b %Y") if n.created_at else "?"
        review = _fmt_date_id(n.review_at) if n.review_at else "—"
        arrow = "→" if n.status == "pending" else "·"
        lines.append(f"{status_icon} #{n.id} · {created} {arrow} review {review}")
        for kp in (n.key_points or []):
            lines.append(f"   • {kp}")
        if not n.key_points and n.body:
            lines.append(f"   • {n.body[:100]}")
        if n.tags:
            lines.append(f"   " + " ".join("#" + tg for tg in n.tags))
        lines.append("")
    return "\n".join(lines)


def fmt_due_list(notes: list[ThesisNote]) -> str:
    if not notes:
        return "Tidak ada yang due minggu ini. Aman dulu."
    lines = [f"Due minggu ini ({len(notes)}):", ""]
    from datetime import datetime
    from backend.merriot.config import WIB
    today = datetime.now(WIB).date()
    for n in notes[:20]:
        days = (n.review_at - today).days if n.review_at else 0
        icon = "🔴" if days <= 1 else "🟡" if days <= 3 else "⚪"
        when = "hari ini" if days == 0 else (f"besok" if days == 1 else f"{days} hari")
        lines.append(f"{icon} #{n.id} · {n.ticker} · {when} ({_fmt_date_id(n.review_at)})")
    return "\n".join(lines)


def fmt_tickers_list(rows: list[dict]) -> str:
    """Per-ticker aggregate list."""
    if not rows:
        return "Belum ada thesis. Lempar yang pertama, biar mulai berburu."
    total_notes = sum(r["total"] for r in rows)
    lines = [f"📚 {len(rows)} ticker · {total_notes} notes total", ""]
    for r in rows[:50]:
        last = r["last_at"].strftime("%-d %b") if r["last_at"] else "?"
        badges = []
        if r["pending"]:
            badges.append(f"⏳ {r['pending']}")
        if r["reviewed"]:
            badges.append(f"✅ {r['reviewed']}")
        if r["invalid"]:
            badges.append(f"💀 {r['invalid']}")
        badge_str = " · ".join(badges)
        lines.append(f"📊 {r['ticker']} · {r['total']} note · last {last} · {badge_str}")
    if len(rows) > 50:
        lines.append(f"\n... +{len(rows)-50} ticker lain")
    lines.append("")
    lines.append("Pakai /thesis <TICKER> untuk detailnya.")
    return "\n".join(lines)


def fmt_recent_list(notes: list[ThesisNote]) -> str:
    if not notes:
        return "Belum ada note. Lempar thesis pertama, yuk."
    lines = ["10 catatan terakhir:", ""]
    for n in notes[:10]:
        created = n.created_at.strftime("%-d %b") if n.created_at else "?"
        first_kp = n.key_points[0] if n.key_points else (n.body or "")[:50]
        lines.append(f"#{n.id} · {n.ticker} · {created} · {first_kp[:60]}")
    return "\n".join(lines)


def fmt_all_notes(notes: list[ThesisNote], total_count: int) -> str:
    """Flat list semua notes — created → review timeline, all key points, tags."""
    if not notes:
        return "Belum ada note sama sekali. Yuk, mulai dari yang pertama."
    lines = [f"📋 Semua notes — menampilkan {len(notes)} dari {total_count}", ""]
    by_ticker: dict[str, list[ThesisNote]] = {}
    for n in notes:
        by_ticker.setdefault(n.ticker, []).append(n)
    sorted_tickers = sorted(
        by_ticker.keys(),
        key=lambda t: max(
            (n.created_at for n in by_ticker[t] if n.created_at),
            default=None,
        ) or 0,
        reverse=True,
    )
    for t in sorted_tickers:
        items = by_ticker[t]
        lines.append(f"📊 {t} ({len(items)})")
        for n in items:
            status_icon = {
                "pending": "⏳",
                "reviewed": "✅",
                "invalid": "💀",
            }.get(n.status, "•")
            created = n.created_at.strftime("%-d %b %Y") if n.created_at else "?"
            review = _fmt_date_id(n.review_at) if n.review_at else "—"
            arrow = "→" if n.status == "pending" else "·"
            lines.append(f"  {status_icon} #{n.id} · {created} {arrow} review {review}")
            for kp in (n.key_points or []):
                lines.append(f"     • {kp}")
            if not n.key_points and n.body:
                lines.append(f"     • {n.body[:80]}")
            if n.tags:
                lines.append(f"     " + " ".join("#" + tg for tg in n.tags))
        lines.append("")
    if total_count > len(notes):
        lines.append(f"... +{total_count - len(notes)} note lebih lama. Pakai /thesis <TICKER>.")
    else:
        lines.append("Pakai /thesis <TICKER> untuk detail. /timeline untuk view chronological.")
    return "\n".join(lines)


def fmt_timeline(notes: list[ThesisNote]) -> str:
    """Chronological timeline view sorted by review_at ASC (closest review first).

    Groups by month. Shows visual time gap supaya keliatan pacing.
    """
    if not notes:
        return "Belum ada thesis pending. Lempar dulu yuk biar timeline-nya rame."
    from datetime import datetime
    from backend.merriot.config import WIB
    today = datetime.now(WIB).date()

    pending = [n for n in notes if n.status == "pending" and n.review_at]
    pending.sort(key=lambda n: n.review_at)

    if not pending:
        return "Tidak ada review pending. Semua thesis udah selesai atau invalid."

    months_id = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                 "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    lines = [f"🗓 Timeline review ({len(pending)} pending)", ""]
    current_month = None
    for n in pending:
        ym = (n.review_at.year, n.review_at.month)
        if ym != current_month:
            current_month = ym
            label = f"{months_id[ym[1]]} {ym[0]}"
            lines.append(f"━━ {label} ━━")
        days = (n.review_at - today).days
        if days < 0:
            when = f"OVERDUE {-days}d"
            icon = "🔴"
        elif days == 0:
            when = "HARI INI"
            icon = "🔴"
        elif days == 1:
            when = "BESOK"
            icon = "🟠"
        elif days <= 7:
            when = f"{days} hari lagi"
            icon = "🟡"
        elif days <= 30:
            when = f"{days} hari"
            icon = "🟢"
        else:
            when = f"{days // 30} bulan"
            icon = "⚪"
        created = n.created_at.strftime("%-d %b") if n.created_at else "?"
        review = n.review_at.strftime("%-d %b")
        lines.append(f"")
        lines.append(f"{icon} {review} · {when}")
        lines.append(f"   📊 {n.ticker} #{n.id} · created {created}")
        for kp in (n.key_points or [])[:3]:
            lines.append(f"   • {kp}")
        if n.tags:
            lines.append(f"   " + " ".join("#" + tg for tg in n.tags[:5]))
    lines.append("")
    lines.append("Pakai /thesis <TICKER> untuk detail per ticker.")
    return "\n".join(lines)


def _fmt_date_id(d: date_cls | None) -> str:
    if not d:
        return "—"
    months = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    return f"{d.day} {months[d.month]} {d.year}"


# Error messages
ERR_NOT_ADMIN = "Bot ini private. Maaf ya."
ERR_EMPTY_INPUT = "Kirim teks thesis-nya dulu."
ERR_LLM_FAILED = "Extract gagal. Coba kirim ulang."
ERR_DRAFT_EXPIRED = "Draft sudah expired. Lempar lagi thesis-nya."
ERR_NOTE_NOT_FOUND = "Note-nya gak ketemu."
