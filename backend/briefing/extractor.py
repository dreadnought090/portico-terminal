"""PDF download + text extraction for IDX disclosure attachments.

PDFs cached under data/briefing_pdfs/{YYYY-MM-DD}/. The orchestrator calls
cleanup_old_pdfs() at the start of each run to remove anything older than
24h, so disk usage stays bounded.
"""
import logging
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger("mybloomberg.briefing")

PDF_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "briefing_pdfs"
MAX_PDF_BYTES = 15_000_000     # 15MB cap — annual reports + prospectuses easily 5-10MB
MAX_TEXT_CHARS = 25_000        # text budget for LLM input — ~$0.005 extra per LK item vs 18k


def cleanup_old_pdfs(keep_days: int = 1) -> int:
    """Remove PDF dirs older than keep_days. Returns count removed."""
    if not PDF_ROOT.exists():
        return 0
    cutoff = date.today() - timedelta(days=keep_days)
    removed = 0
    for sub in PDF_ROOT.iterdir():
        if not sub.is_dir():
            continue
        try:
            d = datetime.strptime(sub.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(sub, ignore_errors=True)
            removed += 1
    return removed


def _today_dir() -> Path:
    p = PDF_ROOT / date.today().isoformat()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_pdf(path: Path) -> bool:
    """Sniff first bytes — IDX sometimes serves HTML error pages with .pdf URL."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
        return head[:5] == b"%PDF-"
    except Exception:
        return False


def download_pdf(url: str, fname_hint: str) -> Path | None:
    """Download a PDF to today's cache dir. Returns path or None on failure.

    Validates the downloaded file is actually a PDF (IDX occasionally returns
    HTML error pages with HTTP 200 + text/html body). Non-PDF responses are
    deleted and None is returned so caller can show a clean failure state.
    """
    if not url:
        return None
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname_hint)[:80]
    if not safe.endswith(".pdf"):
        safe += ".pdf"
    dest = _today_dir() / safe
    if dest.exists() and dest.stat().st_size > 0 and _is_pdf(dest):
        return dest
    try:
        from curl_cffi import requests as cffi_requests
        s = cffi_requests.Session(impersonate="chrome")
        r = s.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            logger.warning("pdf download HTTP %s for %s", r.status_code, url)
            r.close()
            return None
        size = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=64_000):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    logger.warning("pdf %s too large (>%dB), skipping", url, MAX_PDF_BYTES)
                    f.close()
                    dest.unlink(missing_ok=True)
                    return None
                f.write(chunk)
        if not _is_pdf(dest):
            logger.warning("downloaded non-PDF (likely HTML error page): %s", url)
            dest.unlink(missing_ok=True)
            return None
        return dest
    except Exception as e:
        logger.warning("pdf download error for %s: %s", url, e)
        dest.unlink(missing_ok=True)
        return None


def extract_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Returns truncated text or empty string.

    When tables are detected, they're rendered as Markdown pipe-tables inline
    so LLM can parse column structure (raw text linearizes cell content and
    garbles rows — critical for form X.H.1-6 insider reports where all value
    is in the transaction table).
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            chunks = []
            for page in pdf.pages:
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                try:
                    raw_text = page.extract_text() or ""
                except Exception:
                    raw_text = ""
                if tables:
                    for tbl in tables:
                        chunks.append(_render_md_table(tbl))
                if raw_text:
                    chunks.append(raw_text)
                if sum(len(c) for c in chunks) > MAX_TEXT_CHARS:
                    break
            text = "\n\n".join(chunks)
            return text[:MAX_TEXT_CHARS]
    except Exception as e:
        logger.warning("pdf extract error for %s: %s", pdf_path, e)
        return ""


def _render_md_table(table: list[list]) -> str:
    """Format a pdfplumber-extracted table (list of list of str/None) as a
    Markdown pipe table with header row separator. Skips empty tables."""
    if not table or not any(any((c or "").strip() for c in row) for row in table):
        return ""
    rows = []
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    # Insert a header separator after the first row so LLM reliably detects
    # column headers vs data rows.
    if len(rows) > 1:
        col_count = rows[0].count("|") - 1
        sep = "|" + ("---|" * max(col_count, 1))
        rows.insert(1, sep)
    return "TABLE:\n" + "\n".join(rows) + "\nEND TABLE"


def download_file(url: str, fname_hint: str) -> Path | None:
    """Download any attachment (PDF or XLSX) without PDF magic-byte validation.
    Use this for Excel-format LK disclosures. Returns path or None on failure."""
    if not url:
        return None
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname_hint)[:80]
    # Preserve original extension if URL provides one, default to .bin otherwise
    url_ext = url.lower().rsplit(".", 1)[-1] if "." in url.rsplit("/", 1)[-1] else ""
    if url_ext in ("pdf", "xlsx", "xls", "xlsm"):
        if not safe.endswith(f".{url_ext}"):
            safe += f".{url_ext}"
    elif not any(safe.endswith(ext) for ext in (".pdf", ".xlsx", ".xls")):
        safe += ".bin"
    dest = _today_dir() / safe
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        from curl_cffi import requests as cffi_requests
        s = cffi_requests.Session(impersonate="chrome")
        r = s.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            logger.warning("download HTTP %s for %s", r.status_code, url)
            r.close()
            return None
        size = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=64_000):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    logger.warning("file %s too large (>%dB), skipping", url, MAX_PDF_BYTES)
                    f.close()
                    dest.unlink(missing_ok=True)
                    return None
                f.write(chunk)
        return dest
    except Exception as e:
        logger.warning("download error for %s: %s", url, e)
        dest.unlink(missing_ok=True)
        return None


def extract_xlsx_text(xlsx_path: Path) -> str:
    """Convert .xlsx to compact text, prioritizing key financial sheets.

    IDX Laporan Keuangan uses sector-specific XBRL taxonomies. Sheet-code
    prefixes seen:
      1xxxxxx = General Industry
      4xxxxxx = Banking / Sharia Finance
      5xxxxxx = Insurance
      6xxxxxx = Investment Fund / Reksadana
      7xxxxxx = Pension Fund
      8xxxxxx = Real Estate
    Across sectors, the income statement is at <sector>311000 or 312000.
    We prioritize those sheets AND add a keyword-based auto-detect fallback
    for any unknown taxonomy — reads the first cell of each sheet and checks
    for "statement of profit" / "laporan laba rugi" markers.
    """
    # Interleaved priority: each sector's income + balance sheet consecutively.
    # Use only ONE income-statement variant per sector (by-nature preferred over
    # by-function; duplicates waste the text budget because IDX filers submit
    # both representations with identical numbers).
    PRIORITY_SHEETS = [
        "1000000",                        # periods + entity info
        # General Industry
        "1311000", "1210000", "1410000",
        # Banking / Sharia
        "4312000", "4220000", "4410000",
        # Insurance
        "5311000", "5220000",
        # Investment Fund
        "6311000", "6210000",
        # Real Estate
        "8311000", "8210000",
        # Cash Flow (last — less critical than ROE/equity)
        "1321000",
    ]
    # Auto-detect signals (first-cell contents) for income statement sheets
    INCOME_MARKERS = ("statement of profit or loss", "laporan laba rugi")
    BALANCE_MARKERS = ("statement of financial position", "laporan posisi keuangan")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx_path, read_only=True, data_only=True)
        available = set(wb.sheetnames)
        ordered_sheets = [s for s in PRIORITY_SHEETS if s in available]
        # Auto-detect key sheets in the REMAINING unlisted sheets.
        unlisted = [s for s in wb.sheetnames if s not in ordered_sheets]
        auto_detected: list[str] = []
        for sn in unlisted:
            try:
                ws = wb[sn]
                # Peek first few cells for marker keywords
                first_rows = []
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i >= 3:
                        break
                    for c in row:
                        if c:
                            first_rows.append(str(c).lower())
                preview = " ".join(first_rows)
                if any(m in preview for m in INCOME_MARKERS) or any(m in preview for m in BALANCE_MARKERS):
                    auto_detected.append(sn)
            except Exception:
                pass
        ordered_sheets.extend(auto_detected)
        ordered_sheets.extend(s for s in unlisted if s not in auto_detected)

        # Summary-row-only extraction keeps only rows that are subtotals or
        # totals (start with "Jumlah", "Total", "Pendapatan", "Beban",
        # "Laba", "Rugi", period headers), plus metadata rows. Skips detail
        # line items so every priority sheet's headline numbers fit within
        # MAX_TEXT_CHARS — critical for multi-subsidiary banks where balance
        # sheet can be 500+ rows that exhaust the budget before reaching
        # Total Liabilitas + Total Ekuitas rows.
        SUMMARY_PREFIXES = (
            "jumlah ", "total ",
            # Revenue / sales — IDX P&L templates start revenue row with "Penjualan"
            # ("Penjualan dan pendapatan usaha" = Sales and revenue).
            "penjualan", "sales", "revenue", "pendapatan dan", "net sales",
            "pendapatan", "penghasilan",
            "beban ", "cost ",
            "laba ", "rugi ", "profit", "loss", "net income",
            "aset", "asset", "liabilitas", "liabilit",
            "ekuitas", "equity",
            "modal ", "share capital",
            "entitas", "attributable",
            "operating", "operasional",
            "tanggal", "periode", "current", "prior",
            # Metadata (scale + currency) — critical for LLM to interpret numbers
            # correctly. IDX filings often use "Pembulatan: Jutaan" meaning numbers
            # must be multiplied by 1M to get actual rupiah.
            "mata uang", "pembulatan", "presentation currency", "level of rounding",
            "rupiah", "usd", "currency", "scale", "rounding", "satuan",
            # Per-share metrics + outstanding share counts
            "per saham", "per share", "earnings per", "saham beredar",
            "outstanding share", "weighted average",
        )

        def _is_summary_line(line_lower: str) -> bool:
            # Keep if first non-empty token matches summary prefix, OR line has
            # just 1 numeric cell (compact period header lines).
            stripped = line_lower.lstrip()
            return any(stripped.startswith(p) for p in SUMMARY_PREFIXES)

        lines: list[str] = []
        total_chars = 0
        for sheet_name in ordered_sheets:
            if total_chars > MAX_TEXT_CHARS:
                break
            ws = wb[sheet_name]
            header = f"\n=== Sheet: {sheet_name} ==="
            lines.append(header)
            total_chars += len(header)
            for row in ws.iter_rows(values_only=True):
                non_empty = [str(c) for c in row if c not in (None, "", 0)]
                if not non_empty:
                    continue
                joined_lower = " ".join(non_empty).lower()
                if not _is_summary_line(joined_lower):
                    continue
                line = "\t".join(non_empty)[:300]
                lines.append(line)
                total_chars += len(line)
                if total_chars > MAX_TEXT_CHARS:
                    lines.append("... (truncated)")
                    break
        wb.close()
        return "\n".join(lines)[:MAX_TEXT_CHARS]
    except Exception as e:
        logger.warning("xlsx extract error for %s: %s", xlsx_path, e)
        return ""


def fetch_body_text(url: str, fname_hint: str) -> str:
    """Download any attachment URL and extract its text (PDF or XLSX).
    Returns empty string on any failure."""
    if not url:
        return ""
    is_xlsx = url.lower().endswith((".xlsx", ".xlsm", ".xls"))
    if is_xlsx:
        path = download_file(url, fname_hint)
        if not path:
            return ""
        return extract_xlsx_text(path)
    # PDF path (default)
    path = download_pdf(url, fname_hint)
    if not path:
        return ""
    return extract_text(path)
