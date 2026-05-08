"""Title-keyword based classifier for IDX disclosures.

Splits the 24h disclosure feed into:
  PRIORITY (worth deep-summarizing via LLM): dividen, rights issue, material info, etc
  NOTIFY   (just list ticker + title): RUPS, listing, public expose, sustainability
  SKIP     (dropped entirely): NAV reksadana (already filtered upstream), monthly admin
"""
import re

# Each entry: (category_key, priority_level, regex pattern over title lowercased)
# priority_level: "priority" | "notify" | "skip"
# Order matters — first match wins. Most specific patterns first.
_RULES = [
    ("dividen",        "priority", r"\b(dividen|deviden|pembagian saham bonus)\b"),
    ("rights_issue",   "priority", r"\b(hmetd|right issue|penambahan modal.*hak memesan|penawaran umum terbatas|put\s+i+\b)"),
    ("material_info",  "priority",
        r"\b(informasi.*material|fakta material|keterbukaan informasi material"
        r"|keterbukaan informasi.*transaksi afiliasi|transaksi afiliasi"
        r"|tender offer|penawaran tender sukarela|tender sukarela"
        r"|penjelasan atas volatilitas|penjelasan atas permintaan penjelasan bursa"
        r"|laporan.*penggunaan dana|kontrak.*rp|transaksi material)\b"),
    ("akuisisi",       "priority", r"\b(akuisisi|merger|konsolidasi|penambahan bidang usaha|perubahan kegiatan usaha)\b"),
    ("insider_trade",  "priority",
        r"\b(direksi|komisaris|pemegang saham utama|pengendali).*(beli|jual|membeli|menjual|transaksi)\b"
        r"|\blaporan kepemilikan(\s+saham|\s+atau)?\b"),
    ("buyback",        "priority", r"\b(buyback|pembelian kembali saham)\b"),
    # Skip "bukti iklan LK" / "informasi LK" — these are ad-publication
    # confirmation notifications, not the actual financial statement. The
    # substantive LK is a separate disclosure and we catch that with the
    # rule below.
    ("admin_rutin",    "skip",
        r"\b(bukti iklan.*(?:laporan keuangan|lk\s+tahunan)"
        r"|informasi\s+(?:laporan keuangan|lk)\s+tahunan)\b"),
    ("lap_keuangan",   "priority", r"\b(laporan keuangan)\b"),
    ("public_expose",  "notify",   r"\b(public expose|paparan publik|investor day)\b"),

    ("rups",           "notify",
        r"\b(rups|rapat umum pemegang saham|pemanggilan rapat|panggilan rapat"
        r"|ringkasan risalah.*(rapat|rups)"
        r"|penyampaian bukti iklan.*(rups|rapat))\b"),
    ("pencatatan",     "skip",     r"\b(pencatatan saham|listing|delisting|penghapusan)\b"),
    ("sustainability", "skip",     r"\b(laporan keberlanjutan|esg|sustainability|laporan tahunan)\b"),
    ("suspend",        "notify",   r"\b(suspensi|penghentian sementara|unsuspend|pembukaan kembali perdagangan)\b"),
    ("perubahan_corp", "notify",
        r"\b(perubahan|pengunduran diri|berakhir(nya)?\s+jabatan).*\b(direksi|dewan komisaris|komite)\b"
        r"|\bperubahan anggaran dasar\b"
        r"|\bperubahan internal audit\b"),
    ("obligasi",       "skip",     r"\b(obligasi|sukuk|jatuh tempo)\b"),

    ("admin_rutin",    "skip",     r"\b(laporan bulanan registrasi|surat keterangan lunas|laporan harian|laporan transaksi broker)\b"),
]

_COMPILED = [(key, prio, re.compile(pat, re.IGNORECASE)) for key, prio, pat in _RULES]

CATEGORY_LABELS = {
    "dividen":        ("💰", "Dividen"),
    "rights_issue":   ("📈", "HMETD"),
    "material_info":  ("⚠️", "Material"),
    "akuisisi":       ("🤝", "Akuisisi"),
    "insider_trade":  ("👥", "Insider"),
    "buyback":        ("🔄", "Buyback"),
    "lap_keuangan":   ("📊", "LK"),
    "public_expose":  ("🎤", "Public Expose"),
    "rups":           ("🗳️", "RUPS"),
    "pencatatan":     ("📋", "Listing"),
    "sustainability": ("🌱", "Annual Report"),
    "suspend":        ("⏸️", "Suspend"),
    "perubahan_corp": ("🏛️", "Perubahan Corp"),
    "obligasi":       ("📜", "Obligasi"),
    "admin_rutin":    ("📂", "Admin"),
    "uncategorized":  ("📄", "Lainnya"),
}

# "Priority" categories get PDF+LLM in full mode AND are grouped as "Actionable"
# in the header. "Notify" categories are routine — just ticker/title listing.
PRIORITY_CATEGORIES = {
    "dividen", "rights_issue", "material_info", "akuisisi",
    "insider_trade", "buyback", "lap_keuangan",
}

# Material sub-classification — applied inside material_info bucket only.
# Order matters (first match wins). Used by formatter to sub-group.
_MATERIAL_SUBRULES = [
    ("idx_permintaan",   r"\b(penjelasan atas volatilitas|penjelasan atas permintaan penjelasan bursa|permintaan penjelasan)\b"),
    ("transaksi_afiliasi", r"\b(transaksi afiliasi|keterbukaan informasi.*afiliasi)\b"),
    ("tender_offer",     r"\b(tender offer|penawaran tender sukarela|tender sukarela)\b"),
    ("kontrak",          r"\b(kontrak.*rp|kontrak baru|kontrak senilai)\b"),
    ("penggunaan_dana",  r"\blaporan.*penggunaan dana\b"),
]
_MATERIAL_SUB_COMPILED = [(k, re.compile(p, re.IGNORECASE)) for k, p in _MATERIAL_SUBRULES]

MATERIAL_SUB_LABELS = {
    "idx_permintaan":      ("💢", "IDX minta penjelasan"),
    "transaksi_afiliasi":  ("🤝", "Transaksi Afiliasi"),
    "tender_offer":        ("💼", "Tender Offer"),
    "kontrak":             ("📝", "Kontrak Material"),
    "penggunaan_dana":     ("💵", "Penggunaan Dana"),
    "generic_material":    ("📄", "Material lain"),
}

MATERIAL_SUB_ORDER = ["idx_permintaan", "transaksi_afiliasi", "tender_offer", "kontrak", "penggunaan_dana", "generic_material"]


def material_sub_classify(title: str) -> str:
    t = (title or "").lower()
    for key, pat in _MATERIAL_SUB_COMPILED:
        if pat.search(t):
            return key
    return "generic_material"

# Default ordering when rendering — priorities first, then notify, then misc
RENDER_ORDER = [
    "dividen", "rights_issue", "material_info", "akuisisi",
    "insider_trade", "buyback", "lap_keuangan", "public_expose",
    "rups", "pencatatan", "sustainability", "suspend",
    "perubahan_corp", "obligasi", "uncategorized",
]


def classify(title: str) -> tuple[str, str]:
    """Return (category_key, priority_level)."""
    title_norm = (title or "").lower()
    for key, prio, pat in _COMPILED:
        if pat.search(title_norm):
            return key, prio
    return "uncategorized", "notify"


def bucket_disclosures(disclosures: list[dict]) -> dict[str, dict]:
    """Group disclosures by category. Drops items classified as 'skip'.

    Returns: {category_key: {"priority": str, "items": [{ticker, title, date, link, ...}]}}
    """
    buckets: dict[str, dict] = {}
    for d in disclosures:
        key, prio = classify(d.get("title", ""))
        if prio == "skip":
            continue
        buckets.setdefault(key, {"priority": prio, "items": []})
        buckets[key]["items"].append(d)
    return buckets
