"""PDF attachment extraction with password decrypt.

Many ID brokers (Mirae, Mandiri, BNI Sekuritas, IPOT) email transaction
confirmations as password-protected PDFs. Body text is just "konfirmasi
terlampir" so we MUST decrypt + extract PDF text to get the actual data.

Password strategy: try each password in EMAIL_PDF_PASSWORDS env (comma-list).
First successful decrypt wins. Common patterns: birth date DDMMYYYY, NIK,
account number — user puts all candidates in env.
"""
from __future__ import annotations

import io
import logging
import os

logger = logging.getLogger("email_inbox.pdf_extract")

# Lazy imports — pikepdf + pdfplumber heavy, only load when needed.
_pikepdf = None
_pdfplumber = None


def _lazy_import():
    global _pikepdf, _pdfplumber
    if _pikepdf is None:
        try:
            import pikepdf  # type: ignore
            _pikepdf = pikepdf
        except ImportError:
            logger.warning("pikepdf not installed — PDF decrypt disabled")
            return False
    if _pdfplumber is None:
        try:
            import pdfplumber  # type: ignore
            _pdfplumber = pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed — PDF text extract disabled")
            return False
    return True


def passwords() -> list[str]:
    """Comma-separated password candidates to try, in order.

    EMAIL_PDF_PASSWORDS=ddmmyyyy,nik123,acct456
    Common patterns:
      - Birth date DDMMYYYY (Mirae, BNI, most retail)
      - NIK / KTP number (IPOT)
      - Account number (Mandiri Sekuritas)
    """
    raw = os.getenv("EMAIL_PDF_PASSWORDS", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def extract_pdf_text(pdf_bytes: bytes, source_name: str = "attachment.pdf") -> tuple[str, dict]:
    """Decrypt (if needed) + extract text from PDF.

    Returns (text, meta) where meta = {ok, decrypted, password_used, error?}.
    text is empty string on failure. Caller decides how to surface meta.
    """
    if not _lazy_import():
        return "", {"ok": False, "error": "pikepdf/pdfplumber not installed"}

    if not pdf_bytes:
        return "", {"ok": False, "error": "empty bytes"}

    pdf_buf = io.BytesIO(pdf_bytes)
    is_encrypted = False
    decrypted_bytes: bytes | None = None
    password_used: str | None = None

    # Stage 1: detect + decrypt with pikepdf
    try:
        with _pikepdf.open(pdf_buf) as pdf:
            is_encrypted = bool(pdf.is_encrypted)
    except _pikepdf.PasswordError:
        is_encrypted = True
    except Exception as e:
        logger.warning("[%s] pikepdf open failed: %s", source_name, e)
        return "", {"ok": False, "error": f"pdf parse: {e}"}

    if is_encrypted:
        candidates = passwords()
        if not candidates:
            return "", {
                "ok": False, "decrypted": False,
                "error": "PDF encrypted but EMAIL_PDF_PASSWORDS empty",
            }

        for pw in candidates:
            pdf_buf.seek(0)
            try:
                with _pikepdf.open(pdf_buf, password=pw) as pdf:
                    out = io.BytesIO()
                    pdf.save(out)
                    decrypted_bytes = out.getvalue()
                    password_used = pw
                    break
            except _pikepdf.PasswordError:
                continue
            except Exception as e:
                logger.warning("[%s] decrypt with pw[%d chars] failed: %s",
                               source_name, len(pw), e)
                continue

        if decrypted_bytes is None:
            return "", {
                "ok": False, "decrypted": False,
                "error": f"none of {len(candidates)} passwords worked",
            }
    else:
        pdf_buf.seek(0)
        decrypted_bytes = pdf_buf.read()

    # Stage 2: extract text via pdfplumber
    text_parts = []
    try:
        with _pdfplumber.open(io.BytesIO(decrypted_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    text_parts.append(txt)
    except Exception as e:
        logger.warning("[%s] pdfplumber extract failed: %s", source_name, e)
        return "", {
            "ok": False, "decrypted": is_encrypted,
            "error": f"text extract: {e}",
        }

    text = "\n\n".join(text_parts).strip()
    return text, {
        "ok": bool(text),
        "decrypted": is_encrypted,
        "password_used_len": len(password_used) if password_used else 0,
        "pages": len(text_parts),
    }
