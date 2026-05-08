"""Alert message templates — Merriot voice (hunter, no lu/gw, casual ID)."""
from __future__ import annotations

from datetime import datetime, timezone
from backend.models import PriceAlert


def _fmt_price(p: float) -> str:
    """Indonesian-style number formatting: 12.000, 5.975, 1.250.000"""
    if p is None:
        return "—"
    if p == int(p):
        return f"{int(p):,}".replace(",", ".")
    return f"{p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_dir(d: str) -> str:
    return {"above": "↑ di atas", "below": "↓ di bawah"}.get(d, d)


def fmt_alert_armed(a: PriceAlert, current_price: float | None = None,
                    sanity_warn: bool = False) -> str:
    label = f" ({a.label})" if a.label else ""
    arrow = "🏹"
    lines = [
        f"{arrow} Alert armed: {a.ticker} {_fmt_dir(a.direction)} Rp {_fmt_price(a.threshold_price)}{label}",
    ]
    if current_price is not None:
        diff_pct = ((current_price - a.threshold_price) / a.threshold_price) * 100 if a.threshold_price else 0
        direction_emoji = "📈" if diff_pct < 0 and a.direction == "above" else "📉" if diff_pct > 0 and a.direction == "below" else "✓"
        lines.append(f"Sekarang: Rp {_fmt_price(current_price)} ({direction_emoji} {abs(diff_pct):.1f}% dari threshold)")
    if sanity_warn:
        lines.append("⚠ Threshold jauh dari harga sekarang — coba double-check, mungkin typo?")
    lines.append(f"ID: #{a.id} · Aktif sampai trigger")
    return "\n".join(lines)


def fmt_triggered(a: PriceAlert, snap: dict) -> str:
    label = f" ({a.label})" if a.label else ""
    current = snap.get("close") or 0
    drift = a.drift_pct if a.drift_pct is not None else 0
    armed_days = (datetime.now(timezone.utc).replace(tzinfo=None) -
                  (a.created_at.replace(tzinfo=None) if a.created_at else datetime.now())).days
    armed_text = f"{armed_days} hari lalu" if armed_days > 0 else "tadi"
    if a.direction == "above":
        emoji = "🎯"
        verb = "Bidikan kena!"
    else:
        emoji = "💀"
        verb = "Threshold tembus turun!"
    lines = [
        f"{emoji} {verb} {a.ticker} {_fmt_dir(a.direction)} Rp {_fmt_price(a.threshold_price)}{label}",
        f"Sekarang: Rp {_fmt_price(current)} ({'+' if drift > 0 else ''}{drift:.2f}% lewat threshold)",
        f"Armed: {armed_text}",
    ]
    if snap.get("updated_at"):
        lines.append(f"Data: {snap['updated_at']} (IDX)")
    return "\n".join(lines)


def fmt_alerts_list(armed: list[PriceAlert], history: list[PriceAlert],
                    market_open: bool, prices: dict[str, float] | None = None) -> str:
    prices = prices or {}
    lines = []
    if armed:
        lines.append(f"🏹 Armed ({len(armed)})")
        for a in armed:
            cur = prices.get(a.ticker)
            label = f" ({a.label})" if a.label else ""
            cur_str = f"skrg Rp {_fmt_price(cur)}" if cur is not None else "—"
            armed_days = (datetime.now(timezone.utc).replace(tzinfo=None) -
                          (a.created_at.replace(tzinfo=None) if a.created_at else datetime.now())).days
            armed_str = f"{armed_days}d" if armed_days else "<1d"
            lines.append(
                f"#{a.id}  {a.ticker} {_fmt_dir(a.direction)} {_fmt_price(a.threshold_price)}{label}"
                f"  · {cur_str} · {armed_str}"
            )
    else:
        lines.append("🏹 Armed: (tidak ada)")

    if history:
        lines.append("")
        lines.append(f"🎯 Triggered/Cancelled (24h terakhir, {len(history)})")
        for a in history[:10]:
            label = f" ({a.label})" if a.label else ""
            if a.status == "triggered":
                hit = _fmt_price(a.triggered_price) if a.triggered_price else "?"
                lines.append(f"#{a.id}  {a.ticker} {_fmt_dir(a.direction)} {_fmt_price(a.threshold_price)}{label} → kena Rp {hit}")
            else:
                lines.append(f"#{a.id}  {a.ticker} {_fmt_dir(a.direction)} {_fmt_price(a.threshold_price)}{label} → {a.status}")

    if not market_open:
        lines.append("")
        lines.append("🌙 Pasar tutup — alert paused, lanjut Senin 09:00 WIB.")

    return "\n".join(lines) if lines else "Belum ada alert. Coba: alert BBCA above 12000 target"


# Error / status messages
ERR_INVALID_DIR = "Arah harus 'above'/'below' (atau 'atas'/'bawah')."
ERR_INVALID_PRICE = "Threshold harus angka positif."
ERR_INVALID_TICKER = "Ticker harus 3-6 huruf kapital (contoh: BBCA)."
ERR_NOT_FOUND = "Alert tidak ketemu."
ERR_ALREADY_TRIGGERED = "Alert sudah triggered atau cancelled, tidak bisa diubah."
HELP_USAGE = (
    "Cara pakai:\n"
    "  alert BBCA above 12000 target\n"
    "  alert MDIA below 800 stop loss\n"
    "  alerts            — list active\n"
    "  delalert 1        — cancel alert #1"
)
