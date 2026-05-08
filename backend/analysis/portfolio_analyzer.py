"""Portfolio analysis via Claude Opus — dashboard-triggered, comprehensive scoring + recs.

One-shot analysis that takes full portfolio state + recent history and returns a
structured Indonesian-language advisor report. Designed for the user (Ivan) — a
serious retail investor on IDX — so the output is direct, data-driven, actionable.
Not intended for public redistribution; disclaimer still applied.
"""
import json
import logging
import os
from datetime import datetime, timezone

import anthropic
from sqlalchemy.orm import Session

from backend.models import PortfolioItem, PortfolioSnapshot, ThesisMemo

logger = logging.getLogger("mybloomberg.portfolio_analyzer")

MODEL = "claude-opus-4-7"
INPUT_PRICE_PER_M = 15.0   # USD / 1M tokens
OUTPUT_PRICE_PER_M = 75.0  # USD / 1M tokens
MAX_OUTPUT_TOKENS = 4000


# ── Mega-prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """Anda adalah analis portofolio senior dengan pengetahuan mendalam pasar saham Indonesia (IDX). Gaya komunikasi: langsung, berbasis data, tidak bertele-tele, tidak alarmist. Tujuan Anda: memberikan analisis portofolio pribadi yang objektif dan actionable — bukan rekomendasi pasti, tapi framework berpikir yang jelas sehingga pemilik portofolio bisa mengambil keputusan sendiri.

Prinsip analisis:
1. DATA-DRIVEN — selalu kutip angka aktual dari portofolio (ticker, persentase, nominal Rp). Hindari frasa generik seperti "diversifikasi bagus" tanpa sebutkan angka/ticker konkret.
2. DIRECT — bilang apa yang kurang oke tanpa eufimisme. Contoh: "Posisi BBCA 25% dari total = konsentrasi terlalu tinggi" bukan "mungkin perlu dipertimbangkan...".
3. ACTIONABLE — setiap observasi harus punya implikasi atau saran konkret. "Apa next step"-nya.
4. TIDAK FABRICATE — kalau data insufficient untuk kesimpulan, bilang "data tidak cukup untuk nilai X". Jangan karang.
5. SECTOR-AWARE — ambil konteks sektoral IDX (banking dominant di LQ45, mining cyclical, consumer defensive, dll).
6. RISK FIRST — flag concentration risk, illiquid position, sektor overweight sebelum praise.

Format output: Markdown terstruktur Bahasa Indonesia casual-profesional (Anda, bukan lu/gue). Hindari preamble "berikut analisis saya..." — langsung ke section pertama. Max 2500 kata.

PENTING: Ini BUKAN rekomendasi jual-beli. Ini analisis data + framework berpikir. Disclaimer akan ditambahkan otomatis."""

# Asset allocation reference frame — appended below for rebalance reasoning.
from backend.skills._checklists import ASSET_ALLOCATION_CHECKLIST
SYSTEM_PROMPT += "\n\n" + ASSET_ALLOCATION_CHECKLIST


ANALYSIS_FRAMEWORK_PROMPT = """Analisa portofolio berikut ini menggunakan framework berikut. Output TEPAT dengan header + sub-section seperti di bawah:

## 1. 📊 EXECUTIVE SUMMARY
3-4 kalimat one-look: kondisi portofolio secara umum, skor kesehatan 1-10 dengan justifikasi singkat, satu prioritas tindakan paling penting.

## 2. 🏥 PORTFOLIO HEALTH SCORECARD
Evaluasi 6 dimensi (skor 1-10 per dimensi + 1 kalimat justifikasi):
- **Diversifikasi** (jumlah unique ticker, sector spread)
- **Konsentrasi** (% dari top-5 posisi terhadap total; >50% = konsentrasi tinggi)
- **Allocation balance** (sector weighting vs market; overweight/underweight yang mencolok)
- **P&L health** (unrealized pnl, trajectory 30-90 hari)
- **Liquidity** (proporsi ticker dengan market cap kecil)
- **Quality bias** (apakah posisi dominan di blue-chip atau small-cap speculative)

## 3. 🏆 WINNERS & LOSERS ANALYSIS
Top 5 gainer dan top 5 loser dari data.combined. Untuk masing-masing:
- Nominal P&L (Rp) + persen
- Hipotesis kenapa — gunakan ilmu umum sektor (bukan klaim data yang tidak ada)
- KEEP / TRIM / CUT / HOLD recommendation dengan reasoning 1-kalimat

## 4. 🧭 SECTOR ALLOCATION ANALYSIS
Breakdown exposure per sub_sector. Flag yang overweight/underweight vs pasar. Sebut 1-2 ticker dominant di tiap sector overweight.

## 5. ⚠️ RISK FLAGS (yang paling urgent)
Maksimum 5 item. Format: `⚠️ [TICKER] — masalah dalam 1 kalimat — implikasi`. Fokus ke yang benar-benar actionable (cut-loss candidate, posisi terlalu gemuk, ticker nyangkut lama, dll).

## 6. 🎯 ACTIONABLE RECOMMENDATIONS
3-5 saran spesifik dengan ticker + reasoning. Contoh:
- **TRIM**: BBCA dari 25% ke 15% — rebalance konsentrasi
- **ADD**: explorer di sektor X yang under-represented
- **TAX HARVEST**: TICKER Y rugi >3 bulan, bisa dicut buat offset pajak realized gain (Indonesia pajak capital gain 0.1%)
- **MONITOR**: TICKER Z punya event upcoming (RUPS, dividen, LK)

Masing-masing harus kutip data aktual dari portofolio.

## 7. 🔮 WATCH LIST
Upcoming catalysts (kalau data thesis memo / history mentions). Kalau tidak ada data, tulis "_(tidak ada data event upcoming di portofolio)_" — JANGAN karang.

## 8. ❓ PERTANYAAN UNTUK USER
3 pertanyaan reflektif buat user pikirin:
- contoh: "Investment thesis BBCA Anda apa, dan masih berlaku?"
- contoh: "Kenapa ticker X belum di-cut meski rugi 40%?"

---

Disclaimer otomatis ditambahkan di akhir, Anda tidak perlu menulis disclaimer."""


DISCLAIMER = """

---

_⚠️ **BUKAN REKOMENDASI JUAL/BELI.** Analisis ini dihasilkan AI berdasarkan data portofolio + framework generic. BUKAN pengganti riset Anda sendiri, bukan jaminan return, bukan personal financial advice. Verifikasi setiap klaim dengan laporan keuangan emiten + kondisi pasar aktual. Keputusan investasi tanggung jawab Anda sepenuhnya._"""


# ── Data assembly ─────────────────────────────────────────────────────

def _build_context(db: Session) -> dict:
    """Assemble portfolio + history + thesis memos into a compact dict for the prompt."""
    items = db.query(PortfolioItem).all()
    if not items:
        return {"empty": True}

    # Portfolio items
    portfolio = []
    total_cost = 0.0
    total_mv = 0.0
    for i in items:
        portfolio.append({
            "ticker": i.ticker,
            "company": i.company_name or "",
            "sector": i.sub_sector or "",
            "security_type": i.security_type or "",
            "lot": i.lot,
            "shares": i.shares,
            "avg_price": round(i.avg_price, 2),
            "current_price": round(i.current_price, 2),
            "market_value": round(i.market_value, 0),
            "total_cost": round(i.total_cost, 0),
            "unrealized_pnl": round(i.unrealized_pnl, 0),
            "unrealized_pnl_pct": round(i.unrealized_pnl_pct, 2),
            "broker": i.broker or "",
        })
        total_cost += i.total_cost
        total_mv += i.market_value

    # Combined view (dedupe by ticker across brokers)
    combined_map: dict[str, dict] = {}
    for p in portfolio:
        t = p["ticker"]
        if t not in combined_map:
            combined_map[t] = {
                "ticker": t,
                "company": p["company"],
                "sector": p["sector"],
                "shares": 0,
                "total_cost": 0.0,
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
                "brokers": set(),
            }
        c = combined_map[t]
        c["shares"] += p["shares"]
        c["total_cost"] += p["total_cost"]
        c["market_value"] += p["market_value"]
        c["unrealized_pnl"] += p["unrealized_pnl"]
        if p["broker"]:
            c["brokers"].add(p["broker"])
    combined = []
    for c in combined_map.values():
        c["brokers"] = sorted(c["brokers"])
        c["avg_price"] = round(c["total_cost"] / c["shares"], 2) if c["shares"] else 0
        c["unrealized_pnl_pct"] = round(c["unrealized_pnl"] / c["total_cost"] * 100, 2) if c["total_cost"] else 0
        c["weight_pct"] = round(c["market_value"] / total_mv * 100, 2) if total_mv else 0
        combined.append(c)
    combined.sort(key=lambda x: x["market_value"], reverse=True)

    # Sector breakdown
    sectors: dict[str, dict] = {}
    for c in combined:
        s = c["sector"] or "Other"
        sectors.setdefault(s, {"market_value": 0.0, "tickers": []})
        sectors[s]["market_value"] += c["market_value"]
        sectors[s]["tickers"].append(c["ticker"])
    sector_summary = [
        {
            "sector": s,
            "market_value": round(v["market_value"], 0),
            "weight_pct": round(v["market_value"] / total_mv * 100, 2) if total_mv else 0,
            "tickers": v["tickers"],
        }
        for s, v in sectors.items()
    ]
    sector_summary.sort(key=lambda x: x["market_value"], reverse=True)

    # Recent history (last 30 snapshots)
    history = (
        db.query(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .limit(30)
        .all()
    )
    history_data = [
        {
            "date": h.snapshot_date.isoformat() if h.snapshot_date else None,
            "total_market_value": round(h.total_market_value, 0),
            "total_pnl": round(h.total_pnl, 0),
            "total_pnl_pct": round(h.total_pnl_pct, 2),
        }
        for h in reversed(history)  # chronological
    ]

    # Thesis memos (latest per ticker)
    memos = db.query(ThesisMemo).order_by(ThesisMemo.updated_at.desc()).all()
    seen_tickers: set[str] = set()
    thesis_map: dict[str, dict] = {}
    for m in memos:
        if m.ticker in seen_tickers:
            continue
        seen_tickers.add(m.ticker)
        thesis_map[m.ticker] = {
            "version": m.version,
            "confidence": m.confidence_score,
            "content_preview": (m.content_md or "")[:300],
        }

    summary = {
        "total_items": len(portfolio),
        "total_unique_tickers": len(combined),
        "total_cost": round(total_cost, 0),
        "total_market_value": round(total_mv, 0),
        "total_pnl": round(total_mv - total_cost, 0),
        "total_pnl_pct": round((total_mv - total_cost) / total_cost * 100, 2) if total_cost else 0,
    }

    return {
        "summary": summary,
        "combined_holdings": combined,
        "sectors": sector_summary,
        "history_snapshots": history_data,
        "thesis_memos": thesis_map,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ── Main entry ────────────────────────────────────────────────────────

def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE_PER_M + output_tokens * OUTPUT_PRICE_PER_M) / 1_000_000


def analyze_portfolio(db: Session, extra_focus: str | None = None) -> dict:
    """Run Opus analysis on the current portfolio state. Returns markdown + cost.

    `extra_focus` (optional) appends a follow-up instruction like:
    "fokuskan ke posisi rugi >30% dan berikan exit strategy".
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY missing in env", "analysis_md": "", "cost_usd": 0.0}

    ctx = _build_context(db)
    if ctx.get("empty"):
        return {"error": "Portofolio kosong — tambah holding dulu lewat Portfolio tab.", "analysis_md": "", "cost_usd": 0.0}

    # Compute risk metrics from snapshot history — gives Opus concrete numbers.
    from backend.analysis.risk_metrics import compute_risk_metrics, fmt_metrics_for_llm
    risk_metrics = compute_risk_metrics(ctx.get("history", []))

    user_message = (
        f"Berikut data portofolio saya (as of {ctx['as_of']}):\n\n"
        f"```json\n{json.dumps({k: v for k, v in ctx.items() if k != 'as_of'}, indent=2)}\n```\n"
        f"{fmt_metrics_for_llm(risk_metrics)}\n"
    )
    if extra_focus:
        user_message += f"\nFokus tambahan: {extra_focus.strip()}\n\n"
    user_message += ANALYSIS_FRAMEWORK_PROMPT

    start = datetime.now(timezone.utc)
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        analysis = "".join(
            b.text for b in msg.content if getattr(b, "type", "") == "text"
        ).strip() + DISCLAIMER
        cost = estimate_cost(msg.usage.input_tokens, msg.usage.output_tokens)
        return {
            "analysis_md": analysis,
            "cost_usd": round(cost, 4),
            "duration_ms": elapsed_ms,
            "model": MODEL,
            "tokens_in": msg.usage.input_tokens,
            "tokens_out": msg.usage.output_tokens,
            "portfolio_snapshot": {
                "tickers": ctx["summary"]["total_unique_tickers"],
                "market_value": ctx["summary"]["total_market_value"],
                "pnl_pct": ctx["summary"]["total_pnl_pct"],
            },
        }
    except Exception as e:
        logger.exception("portfolio analyze error")
        return {"error": f"{type(e).__name__}: {e}", "analysis_md": "", "cost_usd": 0.0}
