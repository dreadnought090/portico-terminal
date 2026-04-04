# Portico Terminal

Personal Indonesian stock portfolio tracker with real-time data from Yahoo Finance and IDX.

## Features

- **Dashboard** — IHSG, portfolio value, P&L, allocation charts
- **Portfolio Management** — Multi-broker, multi-account (Reguler/Margin/Syariah), sortable columns
- **Watchlist** — AG Grid with live prices
- **Stock Analysis** — Price chart, financials, ownership, company profile
- **News** — Auto-aggregated from Google News with urgency scoring
- **IDX Disclosure** — Corporate announcements from idx.co.id
- **Import** — Screenshot OCR (via Groq Vision) or Excel paste
- **Export** — Portfolio to Excel (.xlsx)

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/portico-terminal.git
cd portico-terminal

# Install dependencies
pip install -r requirements.txt

# (Optional) Setup OCR - get free API key from https://console.groq.com
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Run
python app.py
```

Open **http://localhost:8000** in your browser.

## Access from Phone

If your phone is on the same WiFi network:

```
http://<YOUR_COMPUTER_IP>:8000
```

Find your IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux).

## Tech Stack

- **Backend**: FastAPI + SQLite + SQLAlchemy
- **Frontend**: Vanilla JS, Chart.js, AG Grid, TradingView Lightweight Charts
- **Data**: Yahoo Finance (yfinance), Google News RSS, IDX API (curl_cffi)
- **OCR**: Groq Vision API (optional)

## Screenshots

_(Add screenshots here)_

## License

MIT
