"""OCR service for extracting stock data from broker screenshots using Claude Vision."""
import re
import os
import json
import base64
from PIL import Image
import io
import anthropic


ANTHROPIC_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OCR_MODEL = os.environ.get("OCR_MODEL", "claude-sonnet-4-6")

VISION_PROMPT = """Analisis screenshot portfolio broker saham Indonesia ini.
Ekstrak SEMUA saham/efek yang terlihat dalam format JSON array.

Untuk setiap saham yang terlihat, ekstrak:
- "ticker": kode saham (contoh: BBCA, HRUM, TLKM). Harus kode saham IDX yang valid, BUKAN nama orang atau label UI.
- "lot": jumlah lot (1 lot = 100 lembar). Jika terlihat jumlah lembar/shares, bagi 100 untuk dapat lot.
- "avg_price": harga rata-rata beli (average price). Perhatikan format angka Indonesia (titik sebagai pemisah ribuan).
- "shares": jumlah lembar saham. Jika tidak terlihat, isi lot x 100.
- "raw_line": teks mentah baris tersebut dari screenshot.

Perhatikan:
- Angka Indonesia: 1.065 bisa berarti 1065 (bukan 1,065). 140.500 berarti 140500.
- Abaikan header, nama akun, label UI — hanya ekstrak data saham.
- Jika tidak yakin sebuah kode adalah ticker saham valid, jangan masukkan.
- PENTING: Beberapa broker menampilkan notasi setelah ticker seperti ".L", ".S", "*", "-W", dll.
  Ini BUKAN bagian dari ticker! Contoh: "BULL.L" → ticker adalah "BULL", "GOTO*" → ticker adalah "GOTO".
  Selalu buang notasi/suffix tersebut dan tulis hanya kode ticker murni (huruf kapital saja).

Balas HANYA dengan JSON array, tanpa markdown, tanpa penjelasan. Contoh:
[{"ticker":"HRUM","lot":1065,"avg_price":800,"shares":106500,"raw_line":"HRUM 1065 800"}]

Jika tidak ada saham terdeteksi, balas: []"""


def clean_ocr_ticker(raw: str) -> str:
    """Clean OCR-extracted ticker by removing broker notation suffixes."""
    ticker = raw.strip()
    ticker = re.sub(r'[.\-\*][A-Za-z0-9]*$', '', ticker)
    ticker = re.sub(r'[^A-Z]', '', ticker.upper())
    if len(ticker) > 4:
        ticker = ticker[:4]
    return ticker


def _prepare_image(image_bytes: bytes) -> str:
    """Resize and encode image to base64 for API."""
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode == "RGBA":
        image = image.convert("RGB")

    max_dim = max(image.size)
    if max_dim > 1024:
        ratio = 1024 / max_dim
        new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
        image = image.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _parse_response(response_text: str) -> list:
    """Parse and clean OCR response into stock list."""
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    text = text.strip()

    stocks = json.loads(text)
    if not isinstance(stocks, list):
        stocks = []

    for s in stocks:
        s.setdefault("ticker", "")
        s.setdefault("lot", 0)
        s.setdefault("avg_price", 0)
        s.setdefault("shares", s.get("lot", 0) * 100)
        s.setdefault("raw_line", "")
        s["ticker"] = clean_ocr_ticker(s["ticker"])

    return [s for s in stocks if s["ticker"]]


def _build_prompt(context: str = "", known_tickers: str = "") -> str:
    """Build the full prompt with optional context."""
    prompt = VISION_PROMPT
    extra = []
    if known_tickers:
        extra.append(f"Ticker yang sudah ada di portfolio user: {known_tickers}. Gunakan sebagai referensi untuk mencocokkan ticker yang ambigu.")
    if context:
        extra.append(f"Catatan dari user: {context}")
    if extra:
        prompt += "\n\nKonteks tambahan:\n" + "\n".join(extra)
    return prompt


def extract_stocks_from_image(image_bytes: bytes, context: str = "", known_tickers: str = "") -> dict:
    """Extract stock information from a screenshot using Claude Vision API."""
    if not ANTHROPIC_API_KEY:
        return {
            "error": "API key belum diset. Isi OPENROUTER_API_KEY di file .env dengan Anthropic API key",
            "stocks": [],
            "raw_text": "",
        }

    response_text = ""
    try:
        img_b64 = _prepare_image(image_bytes)
        prompt = _build_prompt(context, known_tickers)
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=OCR_MODEL,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": img_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        response_text = message.content[0].text.strip()
        stocks = _parse_response(response_text)

        return {
            "stocks": stocks,
            "raw_text": f"[Claude/{OCR_MODEL}] {response_text[:500]}",
            "error": None if stocks else "Tidak menemukan ticker saham dalam gambar",
            "engine": f"claude/{OCR_MODEL}",
        }

    except json.JSONDecodeError as e:
        return {
            "stocks": [],
            "raw_text": f"[Claude response] {response_text[:500]}",
            "error": f"Gagal parse JSON: {str(e)}",
            "engine": f"claude/{OCR_MODEL}",
        }
    except Exception as e:
        return {
            "stocks": [],
            "raw_text": response_text[:500] if response_text else "",
            "error": str(e),
            "engine": f"claude/{OCR_MODEL}",
        }
