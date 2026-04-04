"""OCR service for extracting stock data from broker screenshots using Groq Vision."""
import re
import os
import json
import base64
from PIL import Image
import io


GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

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

Balas HANYA dengan JSON array, tanpa markdown, tanpa penjelasan. Contoh:
[{"ticker":"HRUM","lot":1065,"avg_price":800,"shares":106500,"raw_line":"HRUM 1065 800"}]

Jika tidak ada saham terdeteksi, balas: []"""


def extract_stocks_from_image(image_bytes: bytes) -> dict:
    """Extract stock information from a screenshot using Groq Vision."""
    if not GROQ_API_KEY:
        return {
            "error": "GROQ_API_KEY belum diset. Daftar gratis di console.groq.com lalu isi di file .env",
            "stocks": [],
            "raw_text": "",
        }

    response_text = ""
    try:
        from groq import Groq

        image = Image.open(io.BytesIO(image_bytes))
        if image.mode == "RGBA":
            image = image.convert("RGB")

        max_dim = max(image.size)
        if max_dim > 1500:
            ratio = 1500 / max_dim
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0.1,
        )
        response_text = completion.choices[0].message.content.strip()

        # Strip markdown code blocks
        text = response_text
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

        stocks = [s for s in stocks if s["ticker"]]

        return {
            "stocks": stocks,
            "raw_text": f"[Groq Vision] {response_text[:500]}",
            "error": None if stocks else "Tidak menemukan ticker saham dalam gambar",
            "engine": "groq-vision",
        }

    except json.JSONDecodeError as e:
        return {
            "stocks": [],
            "raw_text": f"[Groq response] {response_text[:500]}",
            "error": f"Gagal parse JSON: {str(e)}",
            "engine": "groq-vision",
        }
    except Exception as e:
        return {
            "stocks": [],
            "raw_text": response_text[:500] if response_text else "",
            "error": str(e),
            "engine": "groq-vision",
        }
