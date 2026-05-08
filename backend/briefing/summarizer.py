"""Per-disclosure LLM summarization via Anthropic SDK direct.

Used only in 'full' mode for priority categories. Header-only mode skips this.
"""
import logging
import os
import re

logger = logging.getLogger("mybloomberg.briefing")

# Haiku often emits `**bold**` (MarkdownV2 style). Telegram legacy Markdown uses
# `*single*` for bold, so unbalanced `**` renders as literal asterisks. Collapse.
_BOLD_DOUBLE_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _normalize_markdown(text: str) -> str:
    if not text:
        return text
    text = _BOLD_DOUBLE_RE.sub(r"*\1*", text)
    text = _fix_unit_overflow(text)
    text = _fix_eps_garbage(text)   # kill suspect EPS values BEFORE sci-notation conversion
    text = _fix_sci_notation(text)
    return text


# Match EPS field with suspiciously-tiny value (definitely a scale error from
# LLM division / filer mis-storage). Replace with '—' to avoid showing garbage.
_EPS_TINY_RE = re.compile(
    r"(Q[1-3]\s+EPS|FY\s+EPS|EPS):\s*(Rp|USD)\s+(-?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?)",
    re.IGNORECASE,
)


def _fix_eps_garbage(text: str) -> str:
    """Replace EPS values that are clearly wrong (sub-Rp 0.01) with '—'.

    Real IDX share EPS ranges from ~Rp 0.5 (penny stocks) to thousands. Values
    like 1.5e-6 or 0.000025 are scale artifacts from LLM mis-computation when
    the filer left EPS row blank. Better to show '—' than fake precision.
    """
    def repl(m: re.Match) -> str:
        label = m.group(1)
        currency = m.group(2)
        raw_val = m.group(3)
        try:
            # Parse — handles both '1,5' Indonesian, '1.5e-06' scientific, and '0,000025' Indonesian decimal
            normalized = raw_val.lower().replace(",", ".")
            val = float(normalized)
            if abs(val) > 0 and abs(val) < 0.01:
                return f"{label}: —"
        except ValueError:
            pass
        return m.group(0)
    return _EPS_TINY_RE.sub(repl, text)


# ── Auto-format fixes for LLM output ─────────────────────────────────

# Match "Rp X,YM" or "USD X,YM" where number is in Indonesian format
# (period thousand separator, comma decimal). Used to detect when a number
# is too big for "M" (miliar) and should be promoted to "T" (triliun).
_AMOUNT_RE = re.compile(r"\b(Rp|USD)\s+([\d.,]+)([MT])\b")


def _id_num_to_float(s: str) -> float | None:
    """Parse Indonesian-formatted number like '3.534,2' → 3534.2"""
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _fix_unit_overflow(text: str) -> str:
    """If LLM emitted 'Rp 3.534,2M' (3534 miliar), auto-promote to 'Rp 3,5T'.

    Threshold: when M value >= 1000 → convert to T. Also when T value >= 1000 →
    convert to thousand T (rare). Currency-agnostic (Rp / USD).
    """
    def repl(m: re.Match) -> str:
        currency = m.group(1)
        num_str = m.group(2)
        unit = m.group(3)
        val = _id_num_to_float(num_str)
        if val is None:
            return m.group(0)
        if unit == "M" and val >= 1000:
            new_val = val / 1000
            new_str = f"{new_val:.1f}".replace(".", ",")
            return f"{currency} {new_str}T"
        if unit == "T" and val >= 1000:
            # extreme — keep but flag (some emerging-market caps could hit)
            new_val = val / 1000
            new_str = f"{new_val:.1f}".replace(".", ",")
            return f"{currency} {new_str}quad"
        return m.group(0)
    return _AMOUNT_RE.sub(repl, text)


_SCI_RE = re.compile(r"\b(Rp|USD)\s+(-?\d+(?:[.,]\d+)?)e([-+]?\d+)\b", re.IGNORECASE)


def _fix_sci_notation(text: str) -> str:
    """Convert scientific notation values to readable Indonesian decimal.

    E.g. 'Rp 1,5e-06' → 'Rp 0,0000015'. Only triggers on very small EPS values
    that XBRL filers sometimes mis-store (raw ratio without applying scale).
    """
    def repl(m: re.Match) -> str:
        currency = m.group(1)
        mantissa = m.group(2).replace(",", ".")
        exponent = int(m.group(3))
        try:
            val = float(mantissa) * (10 ** exponent)
            if abs(val) < 1:
                # Very small — show with enough decimals
                formatted = f"{val:.10f}".rstrip("0").rstrip(".") or "0"
            elif abs(val) < 1000:
                formatted = f"{val:.4f}".rstrip("0").rstrip(".")
            else:
                formatted = f"{val:.0f}"
            # Indonesian decimal format
            formatted = formatted.replace(".", ",")
            return f"{currency} {formatted}"
        except (ValueError, OverflowError):
            return m.group(0)
    return _SCI_RE.sub(repl, text)

# Default model = Haiku for cheap/simple categories. LK gets upgraded
# to Sonnet for better numerical reasoning (scale handling, EPS sanity).
MODEL_ID = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 350

# Per-model pricing (USD per 1M tokens). Update if Anthropic changes prices.
MODEL_PRICING = {
    "claude-haiku-4-5":  {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
}

# Categories that warrant the better (and pricier) Sonnet model. LK has many
# numerical edge cases (scale conversion, EPS calculation, bank XBRL) where
# Haiku trips up. Other categories are extraction-style + tolerate Haiku.
PREMIUM_MODEL_CATEGORIES = {"lap_keuangan"}
PREMIUM_MODEL_ID = "claude-sonnet-4-6"

# Backward-compat aliases for existing code paths.
INPUT_PRICE_PER_M = MODEL_PRICING[MODEL_ID]["input"]
OUTPUT_PRICE_PER_M = MODEL_PRICING[MODEL_ID]["output"]


def _model_for_category(category_key: str) -> str:
    return PREMIUM_MODEL_ID if category_key in PREMIUM_MODEL_CATEGORIES else MODEL_ID


def _cost_for_model(model: str, input_tokens: int, output_tokens: int) -> float:
    p = MODEL_PRICING.get(model, MODEL_PRICING[MODEL_ID])
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

# Per-category extraction prompts. Output is ONE LINE of compact inline prose
# (not multi-line bullets) — target ~100-180 chars. No "**Label:**" prefixes.
# Use commas/slashes to separate facts. Preserve numbers exactly from document.
_COMPACT_STYLE_RULES = (
    "OUTPUT RULES — PENTING:\n"
    "- Maksimum 2 baris, target 1 baris inline prose (bukan bullet list).\n"
    "- Jangan pakai label bold '**Nama:** value'. Pakai format compact 'X Rp Y, Z A%'.\n"
    "- Separator pakai koma/slash, bukan newline per fakta.\n"
    "- Angka Rp: compact ('Rp 17,2M', 'Rp 500jt', 'Rp 35'), tanpa pemisah ribuan.\n"
    "- Pakai simbol arah 📈/🔻 kalau ada YoY comparison yang relevan.\n"
    "- Jangan preamble ('berikut ringkasan', 'detail dokumen'). Langsung data.\n"
    "- Kalau angka tidak ada di dokumen, tulis 'TBD' atau skip (jangan karang)."
)

_CATEGORY_PROMPTS = {
    "dividen": (
        "Ekstrak disclosure dividen: DPS (Rp/lembar), cum/ex/payment date, total payout, payout ratio. "
        "Format example: 'DPS Rp 35, cum 30 Apr, ex 2 Mei, pay 14 Mei, payout ratio 62%'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "rights_issue": (
        "Ekstrak prospektus rights issue / HMETD: rasio, harga, saham baru, dilusi %, standby buyer, use of proceeds. "
        "Format example: 'HMETD 1:3, 10,68B saham baru, dilusi 75%, harga TBD, use: organic lending'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "material_info": (
        "Ringkas informasi material: aksi + angka kunci + dampak. "
        "Format example: 'Divestasi aset Rp 500M ke AFILIASI, dampak net cash +Rp 450M'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "akuisisi": (
        "Ekstrak akuisisi/bidang usaha: target, nilai, sumber dana, rationale. "
        "Format example: 'Akuisisi 51% PT X @ Rp 2T via kas internal, diversifikasi ke F&B'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "insider_trade": (
        "Ekstrak transaksi insider: jabatan + beli/jual + jumlah saham + nilai. "
        "Format example: 'PSU beli 5jt lbr @ Rp 150 (Rp 750jt)'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "buyback": (
        "Ekstrak buyback: nilai program, % modal, periode, harga cap, sumber dana, dampak EPS. "
        "Format example: 'Buyback Rp 200M (5% modal, 340jt lbr), cap Rp 850, 1 Jun 26–29 Mei 27, dana internal. EPS 51,29→54,45'.\n\n" + _COMPACT_STYLE_RULES
    ),
    "lap_keuangan": (
        "Ekstrak data keuangan. Output SATU BARIS tepat format berikut, pipe-separator. "
        "Isi nilai dari dokumen, atau '—' kalau data tidak tersedia. JANGAN narasi, hanya 1 baris:\n\n"
        "`Periode: <Q1 2026/Q2 2026/Q3 2026/FY 2025/etc> | Rev: <Rp|USD> X (YoY ±Y%) | NPAT: <Rp|USD> X (YoY ±Y%) | "
        "<Q1/Q2/Q3/FY> EPS: <Rp|USD> X | Liabilitas: <Rp|USD> X (YoY ±Y%) | Ekuitas: <Rp|USD> X (YoY ±Y%)`\n\n"
        "Currency prefix konsisten di SEMUA field (Rev/NPAT/EPS/Liabilitas/Ekuitas) — pakai currency aslinya dokumen.\n\n"
        "⚠️⚠️ UNIT CONVERSION — STEP BY STEP (jangan salah skala, SAMA SEKALI):\n\n"
        "LANGKAH 0 — Cek CURRENCY dari sheet 1000000 (baris 'Mata uang pelaporan'):\n"
        "  'Rupiah / IDR' → pakai prefix 'Rp'\n"
        "  'Dollar Amerika / USD' → pakai prefix 'USD' (BUKAN Rp!)\n"
        "  Kalau USD, output: 'USD 762M' (M=miliar/million), 'USD 1,2T' (T=triliun/trillion), dst.\n"
        "  Tidak ada conversion IDR↔USD, pakai currency aslinya dari dokumen.\n\n"
        "LANGKAH 1 — Cek scaling dari sheet 1000000 (baris 'Pembulatan' / 'Level of rounding'):\n"
        "  'Satuan Penuh / Full Amount' → angka di dokumen = full amount, TIDAK usah dikali\n"
        "  'Jutaan / In Million' → KALIKAN angka dengan 1.000.000 (10^6) dulu\n"
        "  'Ribuan / In Thousand' → kalikan dengan 1.000\n"
        "  Kalau tidak ada → asumsi Satuan Penuh.\n\n"
        "CONTOH GIAA (airline, USD currency, Jutaan scale):\n"
        "  raw 762 + scale 'Jutaan' + currency USD → 762 × 10^6 USD = 762.000.000 (9 digit) → USD 762M ✓\n"
        "  BUKAN 'Rp 762,4jt' (ini salah 2 kali: currency + scale)\n\n"
        "CATATAN — sheet P&L bisa beda per filer:\n"
        "  Bisa di 1311000, 1312000, 1321000, atau 1322000 (semua = Statement of Profit or Loss).\n"
        "  Kalau satu sheet kosong, CEK sheet next — GIAA misalnya P&L ada di 1321000 bukan 1311000.\n\n"
        "LANGKAH 2 — Hitung jumlah digit hasil (setelah scaling), pakai tabel ini STRICT:\n"
        "  4-6 digit → `Rp X` atau `Rp X.XXXrb` (ribu)\n"
        "  7-9 digit → `Rp X,Xjt` (juta)\n"
        "  10-12 digit → `Rp X,XM` (MILIAR — M)\n"
        "  13-15 digit → `Rp X,XT` (TRILIUN — T)\n\n"
        "LANGKAH 3 — Cross-check dengan contoh dibawah:\n"
        "  raw 23.323 + scale 'Jutaan' → 23.323 × 10^6 = 23.323.000.000 (11 digit) → Rp 23,3M ✓\n"
        "  raw 940.393.384.685 + scale 'Satuan Penuh' → 940.393.384.685 (12 digit) → Rp 940,4M ✓\n"
        "  raw 1.047.032.188.556 + scale 'Satuan Penuh' → 13 digit → Rp 1,05T ✓\n"
        "  raw 106.638.803.871 + scale 'Satuan Penuh' → 12 digit → Rp 106,6M ✓ (BUKAN Rp 106,6T)\n\n"
        "ATURAN EMAS: 12 digit dan di bawahnya = MILIAR (M). Hanya 13+ digit yang boleh pakai T (TRILIUN).\n"
        "JANGAN pakai T kecuali jumlah digit angka aktual ≥ 13.\n\n"
        "EPS CONVENTIONS — SANGAT PENTING:\n"
        "- EPS label sesuai period: `Q1 EPS`, `Q2 EPS`, `Q3 EPS`, atau `FY EPS`. BUKAN cuma 'EPS:'.\n"
        "- ⛔ JANGAN HITUNG EPS SENDIRI. Hanya pakai nilai yang TERTULIS di baris 'Laba per saham dasar'\n"
        "  atau 'Earnings per share' di dokumen. Kalau baris itu kosong/blank → output `<period> EPS: —`.\n"
        "- ⛔ JANGAN bagi NPAT/shares manually — banyak filer lupa apply scale ke EPS storage,\n"
        "  hasilnya scientific notation kecil (1e-06) atau 0. Lebih baik `—` daripada angka salah.\n"
        "- Kalau EPS ada di dokumen tapi nilainya scientific (1,5e-06 atau 2e-06): SKIP, tulis `—`.\n"
        "  Filer mis-stored — angka itu pasti salah skala, jangan diteruskan ke output.\n"
        "- Format EPS valid: `Rp 25`, `Rp -7,66`, `Rp 0,15` — selalu decimal Indonesian, NEVER scientific.\n\n"
        "FIELD DEFINITIONS:\n"
        "- Liabilitas = 'Jumlah Liabilitas' / 'Total Liabilities' dari Statement of Financial Position.\n"
        "- Ekuitas = 'Jumlah Ekuitas' / 'Total Equity' dari Statement of Financial Position.\n"
        "- Untuk bank/syariah: Liabilitas TIDAK termasuk 'Dana syirkah temporer' (kategori sendiri).\n"
        "- YoY % = (current − prior) / prior × 100. Kalau tidak ada prior period di dokumen → `—`.\n"
        "- Kalau dokumen hanya balance sheet tanpa income statement: Rev/NPAT/EPS = `—`, isi Liab + Ekuitas.\n"
        "- Kalau dokumen cuma pemberitahuan: output `(belum ada data - rencana penyampaian)`.\n\n"
        "FORMATTING:\n"
        "- JANGAN pakai `**bold**`. Pakai 🔻 kalau NPAT/EPS memburuk YoY, 📈 kalau membaik.\n"
        "- Maksimum 1 baris. Kalau harus 2 baris, baris ke-2 hanya untuk catatan penting."
    ),
    "public_expose": (
        "Ringkas highlight public expose: tema + guidance + capex/M&A plan. "
        "Format example: 'Tema: bank digital expansion; target revenue +15% 2026; capex Rp 2T'.\n\n" + _COMPACT_STYLE_RULES
    ),
}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE_PER_M + output_tokens * OUTPUT_PRICE_PER_M) / 1_000_000


def summarize_insider_aggregate(items: list[dict]) -> tuple[str, float]:
    """Single LLM call to digest ALL insider trade disclosures of the day.
    Each item should have keys: ticker, title, _body_text (PDF-extracted text or "").
    Returns (formatted_summary_md, cost_usd).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "(API key missing)", 0.0
    if not items:
        return "(tidak ada data)", 0.0

    # Build a compact corpus: per-item header + truncated body so the prompt fits.
    # Insider tables typically start ~800-1200 chars into the PDF (after cover
    # letter preamble), so keep a generous floor so we don't cut off the data.
    per_item_max = max(2500, 20_000 // max(1, len(items)))
    sections = []
    for it in items:
        ticker = it.get("ticker", "?")
        title = it.get("title", "")
        body = (it.get("_body_text") or "")[:per_item_max]
        if body:
            sections.append(f"### {ticker} | {title}\n{body}")
        else:
            sections.append(f"### {ticker} | {title}\n(PDF tidak ter-extract)")
    corpus = "\n\n".join(sections)

    instructions = (
        "Anda menerima daftar laporan kepemilikan saham insider (direksi, komisaris, "
        "pemegang saham utama/PSU, pengendali) dari berbagai emiten IDX hari ini.\n\n"
        "Dokumen adalah Form X.H.1-6 OJK — biasa ada tabel dengan kolom: Nama pelaku, "
        "Jabatan, Jenis Transaksi (Pembelian/Penjualan), Jumlah Saham, Harga, Nilai.\n\n"
        "Tugas: ekstrak per emiten: arah (BELI/JUAL), nilai Rp total, jabatan.\n\n"
        "Format output PERSIS seperti template ini, tanpa preamble:\n\n"
        "*BELI* (N):\n"
        "• `TICKER` Rp X (Jabatan)\n\n"
        "*JUAL* (N):\n"
        "• `TICKER` Rp X (Jabatan)\n\n"
        "Aturan:\n"
        "- Urutkan dari nominal terbesar di tiap seksi.\n"
        "- Format Rp compact: `Rp 5,2M` (M=miliar), `Rp 800jt`, `Rp 50jt`. Tanpa pemisah ribuan.\n"
        "- Jabatan singkat: PSU / Pengendali / Direksi / Komisaris.\n"
        "- Pakai `*bold*` (single asterisk), JANGAN `**bold**`.\n"
        "- Jika TIDAK ada transaksi beli di data → tulis `*BELI* (0): tidak ada` dan lanjut *JUAL*.\n"
        "- Jika nilai spesifik tidak terekstrak di dokumen, tulis `Rp ?` (jangan karang angka).\n"
        "- Skip emiten yang body_text-nya kosong/tidak terbaca.\n"
        "- JANGAN narasi tambahan. Cuma bullet berformat."
    )

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL_ID,
            max_tokens=1200,  # bigger budget for aggregate
            system=(
                "Anda asisten data extractor untuk transaksi insider IDX. Output ringkas, "
                "faktual, hanya angka dari dokumen — tidak ada interpretasi."
            ),
            messages=[{
                "role": "user",
                "content": f"{instructions}\n\n=== INPUT ({len(items)} laporan) ===\n\n{corpus}",
            }],
        )
        text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        summary = _normalize_markdown("\n".join(text_parts).strip())
        cost = estimate_cost(msg.usage.input_tokens, msg.usage.output_tokens)
        return summary, cost
    except Exception as e:
        logger.warning("insider aggregate error: %s", e)
        return f"(LLM error: {type(e).__name__})", 0.0


def summarize(category_key: str, ticker: str, title: str, body_text: str) -> tuple[str, float]:
    """Send body to Haiku, return (summary_md, cost_usd). Empty string on failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "(API key missing)", 0.0

    instructions = _CATEGORY_PROMPTS.get(
        category_key,
        "Ringkas disclosure ini dalam 2-4 baris bullet, faktual saja.",
    )

    if not body_text or len(body_text) < 100:
        return "(PDF tidak bisa di-extract)", 0.0

    model_id = _model_for_category(category_key)
    # LK gets bigger output budget — pipe-template is longer than other cats.
    max_tokens = 600 if category_key == "lap_keuangan" else MAX_OUTPUT_TOKENS
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=(
                "Anda asisten analis IDX. Ringkas disclosure dengan akurat, hanya pakai angka "
                "yang muncul di dokumen. Format singkat, padat, Bahasa Indonesia formal. "
                "Tanpa preamble seperti 'berikut ringkasan' — langsung bullet."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Ticker: {ticker}\nJudul: {title}\n\n"
                    f"Isi dokumen:\n{body_text}\n\n"
                    f"Tugas: {instructions}"
                ),
            }],
        )
        text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        summary = _normalize_markdown("\n".join(text_parts).strip())
        cost = _cost_for_model(model_id, msg.usage.input_tokens, msg.usage.output_tokens)
        return summary, cost
    except Exception as e:
        logger.warning("summarize error for %s/%s: %s", ticker, category_key, e)
        return f"(LLM error: {type(e).__name__})", 0.0
