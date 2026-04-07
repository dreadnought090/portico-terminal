"""Portico - Indonesian Stock Terminal Application."""
import os
import sys
import asyncio
import logging

logger = logging.getLogger("mybloomberg")

# Load .env file if exists
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.database import get_db, init_db
from backend.models import PortfolioItem, StockCache, NewsItem, Watchlist, SecurityType, SubSector, PortfolioSnapshot
from backend.stock_service import (
    fetch_stock_data, fetch_stock_history, fetch_news_for_ticker,
    fetch_idx_disclosure, fetch_market_summary, IDX_SECTORS,
    fetch_corporate_profile, fetch_ownership_data, fetch_financials,
    fetch_financial_statements
)
from backend.ocr_service import extract_stocks_from_image

scheduler = AsyncIOScheduler()


def _update_item_price(item: PortfolioItem, data: dict, db: Session = None):
    """Shared helper: update a portfolio item's price from fetched data."""
    item.current_price = data["last_price"]
    item.market_value = item.shares * data["last_price"]
    item.unrealized_pnl = item.market_value - item.total_cost
    item.unrealized_pnl_pct = (
        (item.unrealized_pnl / item.total_cost * 100) if item.total_cost else 0
    )
    item.last_updated = datetime.now(timezone.utc)

    if db:
        cache = db.query(StockCache).filter_by(ticker=item.ticker).first()
        if cache:
            cache.last_price = data["last_price"]
            cache.change = data.get("change", 0)
            cache.change_pct = data.get("change_pct", 0)
            cache.volume = data.get("volume", 0)
            cache.last_updated = datetime.now(timezone.utc)


async def update_all_portfolio_prices():
    """Background job: update prices for all portfolio items."""
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        items = db.query(PortfolioItem).all()
        for item in items:
            try:
                data = fetch_stock_data(item.ticker)
                if "error" not in data:
                    _update_item_price(item, data, db)
            except Exception:
                logger.exception("Failed to update price for %s", item.ticker)
                continue
        db.commit()
    finally:
        db.close()


def take_portfolio_snapshot(db: Session = None):
    """Save a snapshot of today's portfolio totals."""
    from backend.database import SessionLocal
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        items = db.query(PortfolioItem).all()
        if not items:
            return
        today = datetime.now(timezone.utc).date()
        total_cost = sum(i.total_cost for i in items)
        total_mv = sum(i.market_value for i in items)
        total_pnl = total_mv - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

        snap = db.query(PortfolioSnapshot).filter_by(snapshot_date=today).first()
        if snap:
            snap.total_cost = total_cost
            snap.total_market_value = total_mv
            snap.total_pnl = total_pnl
            snap.total_pnl_pct = total_pnl_pct
            snap.total_items = len(items)
        else:
            db.add(PortfolioSnapshot(
                snapshot_date=today,
                total_cost=total_cost,
                total_market_value=total_mv,
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl_pct,
                total_items=len(items),
            ))
        db.commit()
    except Exception:
        logger.exception("Failed to take portfolio snapshot")
    finally:
        if own_db:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(update_all_portfolio_prices, "interval", minutes=15, id="price_update")
    scheduler.add_job(take_portfolio_snapshot, "cron", hour=16, minute=5, id="daily_snapshot")
    scheduler.start()
    # Take snapshot on startup if portfolio has data
    take_portfolio_snapshot()
    yield
    scheduler.shutdown()


app = FastAPI(title="Portico", version="1.0.0", lifespan=lifespan)

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/frontend", StaticFiles(directory=os.path.join(BASE_DIR, "frontend")), name="frontend")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Pydantic Schemas ──────────────────────────────────────────────────

class AddStockRequest(BaseModel):
    ticker: str
    lot: int = 0
    shares: int = 0
    avg_price: float = 0
    security_type: str = "Saham"
    broker: str = ""
    account_type: str = "Reguler"
    company_name: str = ""
    total_cost: float = 0
    notes: str = ""


class UpdateStockRequest(BaseModel):
    lot: Optional[int] = None
    shares: Optional[int] = None
    avg_price: Optional[float] = None
    security_type: Optional[str] = None
    broker: Optional[str] = None
    account_type: Optional[str] = None
    notes: Optional[str] = None


# ── Pages ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# ── Market Data API ───────────────────────────────────────────────────

@app.get("/api/market")
async def get_market_summary():
    """Get IHSG and market overview."""
    return await fetch_market_summary()


@app.get("/api/stock/{ticker}")
async def get_stock(ticker: str):
    """Get real-time stock data for a ticker."""
    data = fetch_stock_data(ticker)
    if "error" in data and "last_price" not in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@app.get("/api/stock/{ticker}/history")
async def get_stock_history(ticker: str, period: str = "1mo"):
    """Get historical price data."""
    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
    if period not in valid_periods:
        period = "1mo"
    data = fetch_stock_history(ticker, period)
    return {"ticker": ticker.upper(), "period": period, "data": data}


@app.get("/api/stock/{ticker}/news")
async def get_stock_news(ticker: str):
    """Get news for a specific stock."""
    news = await fetch_news_for_ticker(ticker)
    return {"ticker": ticker.upper(), "news": news}


@app.get("/api/stock/{ticker}/profile")
async def get_corporate_profile(ticker: str):
    """Get corporate profile and company officers."""
    return fetch_corporate_profile(ticker)


@app.get("/api/stock/{ticker}/ownership")
async def get_ownership(ticker: str):
    """Get ownership and shareholder data."""
    return fetch_ownership_data(ticker)


@app.get("/api/stock/{ticker}/financials")
async def get_financials(ticker: str):
    """Get key financial metrics and quarterly data."""
    return fetch_financials(ticker)


@app.get("/api/stock/{ticker}/statements")
async def get_financial_statements(ticker: str, quarters: int = Query(default=8, le=32)):
    """Get quarterly financial statements (Income Statement, Balance Sheet, Cash Flow)."""
    return fetch_financial_statements(ticker, num_quarters=quarters)


@app.get("/api/disclosure")
async def get_disclosure(ticker: str = "", page: int = 0):
    """Get IDX corporate disclosures."""
    disclosures = await fetch_idx_disclosure(ticker, page=page, page_size=50)
    return {"disclosures": disclosures, "page": page, "hasMore": len(disclosures) >= 50}


# ── Portfolio API ─────────────────────────────────────────────────────

@app.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    """Get all portfolio items with classification."""
    items = db.query(PortfolioItem).all()
    portfolio = []
    total_cost = 0
    total_market_value = 0
    total_pnl = 0

    for item in items:
        entry = {
            "id": item.id,
            "ticker": item.ticker,
            "company_name": item.company_name,
            "security_type": item.security_type,
            "sub_sector": item.sub_sector,
            "lot": item.lot,
            "shares": item.shares,
            "avg_price": item.avg_price,
            "total_cost": item.total_cost,
            "current_price": item.current_price,
            "market_value": item.market_value,
            "unrealized_pnl": item.unrealized_pnl,
            "unrealized_pnl_pct": item.unrealized_pnl_pct,
            "last_updated": item.last_updated.isoformat() if item.last_updated else None,
            "broker": item.broker or "",
            "account_type": item.account_type or "Reguler",
            "notes": item.notes,
        }
        portfolio.append(entry)
        total_cost += item.total_cost
        total_market_value += item.market_value
        total_pnl += item.unrealized_pnl

    # Classification by security type
    by_type = {}
    for item in portfolio:
        sec_type = item["security_type"]
        if sec_type not in by_type:
            by_type[sec_type] = {"items": [], "total_cost": 0, "market_value": 0, "pnl": 0}
        by_type[sec_type]["items"].append(item)
        by_type[sec_type]["total_cost"] += item["total_cost"]
        by_type[sec_type]["market_value"] += item["market_value"]
        by_type[sec_type]["pnl"] += item["unrealized_pnl"]

    # Classification by sector
    by_sector = {}
    for item in portfolio:
        sector = item["sub_sector"]
        if sector not in by_sector:
            by_sector[sector] = {"items": [], "total_cost": 0, "market_value": 0, "pnl": 0}
        by_sector[sector]["items"].append(item)
        by_sector[sector]["total_cost"] += item["total_cost"]
        by_sector[sector]["market_value"] += item["market_value"]
        by_sector[sector]["pnl"] += item["unrealized_pnl"]

    # Classification by broker
    by_broker = {}
    for item in portfolio:
        broker = item["broker"] or "Tanpa Sekuritas"
        if broker not in by_broker:
            by_broker[broker] = {"items": [], "total_cost": 0, "market_value": 0, "pnl": 0}
        by_broker[broker]["items"].append(item)
        by_broker[broker]["total_cost"] += item["total_cost"]
        by_broker[broker]["market_value"] += item["market_value"]
        by_broker[broker]["pnl"] += item["unrealized_pnl"]

    # Combined view: merge same tickers across brokers
    combined = {}
    for item in portfolio:
        t = item["ticker"]
        if t not in combined:
            combined[t] = {
                "ticker": t,
                "company_name": item["company_name"],
                "security_type": item["security_type"],
                "sub_sector": item["sub_sector"],
                "lot": 0, "shares": 0, "total_cost": 0,
                "current_price": item["current_price"],
                "market_value": 0, "unrealized_pnl": 0,
                "brokers": [],
                "ids": [],
            }
        c = combined[t]
        c["lot"] += item["lot"]
        c["shares"] += item["shares"]
        c["total_cost"] += item["total_cost"]
        c["market_value"] += item["market_value"]
        c["unrealized_pnl"] += item["unrealized_pnl"]
        if item["broker"]:
            c["brokers"].append(item["broker"])
        c["ids"].append(item["id"])
    for t, c in combined.items():
        c["avg_price"] = (c["total_cost"] / c["shares"]) if c["shares"] else 0
        c["unrealized_pnl_pct"] = (c["unrealized_pnl"] / c["total_cost"] * 100) if c["total_cost"] else 0
        c["brokers"] = list(set(c["brokers"]))
    combined_list = list(combined.values())

    return {
        "items": portfolio,
        "combined": combined_list,
        "summary": {
            "total_items": len(portfolio),
            "total_unique": len(combined_list),
            "total_cost": total_cost,
            "total_market_value": total_market_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": (total_pnl / total_cost * 100) if total_cost else 0,
        },
        "by_type": by_type,
        "by_sector": by_sector,
        "by_broker": by_broker,
    }


@app.post("/api/portfolio")
async def add_to_portfolio(req: AddStockRequest, db: Session = Depends(get_db)):
    """Add a stock to portfolio."""
    ticker = req.ticker.upper().replace(".JK", "")

    # Check if already exists with same broker + account type
    existing = db.query(PortfolioItem).filter_by(
        ticker=ticker, broker=req.broker, account_type=req.account_type
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{ticker} sudah ada di portfolio ({req.broker} - {req.account_type})")

    # For tradeable assets (saham, etf, warrant, right), fetch live price
    asset_type = req.security_type.lower()
    if asset_type in ("saham", "etf", "warrant", "right"):
        if req.lot <= 0 and req.shares <= 0:
            raise HTTPException(status_code=400, detail="Lot atau shares harus diisi (minimal salah satu > 0)")
        data = fetch_stock_data(ticker)
        current_price = data.get("last_price", 0)
        company_name = req.company_name or data.get("company_name", ticker)
        sector = data.get("sector", "Other")
        shares = req.shares if req.shares > 0 else req.lot * 100
        lot = req.lot if req.lot > 0 else (req.shares // 100 if req.shares > 0 else 0)
        total_cost = shares * req.avg_price
        market_value = shares * current_price
    else:
        # Obligasi, Reksadana, Lainnya — no live price
        current_price = req.avg_price
        company_name = req.company_name or ticker
        sector = req.security_type
        shares = req.shares if req.shares > 0 else max(req.lot, 1)
        lot = req.lot if req.lot > 0 else 1
        total_cost = req.total_cost if req.total_cost > 0 else shares * req.avg_price
        market_value = total_cost  # no live pricing

    pnl = market_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost else 0

    item = PortfolioItem(
        ticker=ticker,
        company_name=company_name,
        security_type=req.security_type,
        sub_sector=sector,
        lot=lot,
        shares=shares,
        avg_price=req.avg_price,
        total_cost=total_cost,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl=pnl,
        unrealized_pnl_pct=pnl_pct,
        broker=req.broker,
        account_type=req.account_type,
        notes=req.notes,
    )
    db.add(item)

    # Also add to watchlist
    wl = db.query(Watchlist).filter_by(ticker=ticker).first()
    if not wl:
        db.add(Watchlist(ticker=ticker))

    # Cache stock data (only for tradeable assets with live data)
    if asset_type in ("saham", "etf", "warrant", "right"):
        cache = db.query(StockCache).filter_by(ticker=ticker).first()
        if not cache:
            cache = StockCache(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                sub_sector=sector,
                last_price=current_price,
                prev_close=data.get("prev_close", 0),
                open_price=data.get("open_price", 0),
                high=data.get("high", 0),
                low=data.get("low", 0),
                volume=data.get("volume", 0),
                market_cap=data.get("market_cap", 0),
                pe_ratio=data.get("pe_ratio", 0),
                pb_ratio=data.get("pb_ratio", 0),
                dividend_yield=data.get("dividend_yield", 0),
                change=data.get("change", 0),
                change_pct=data.get("change_pct", 0),
            )
            db.add(cache)

    db.commit()

    return {"message": f"{ticker} berhasil ditambahkan ke portfolio", "ticker": ticker}


@app.put("/api/portfolio/{item_id}")
def update_portfolio_item(item_id: int, req: UpdateStockRequest, db: Session = Depends(get_db)):
    """Update a portfolio item."""
    item = db.query(PortfolioItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")

    if req.lot is not None:
        item.lot = req.lot
        item.shares = req.lot * 100
    if req.shares is not None:
        item.shares = req.shares
        item.lot = req.shares // 100
    if req.avg_price is not None:
        item.avg_price = req.avg_price
    if req.security_type is not None:
        item.security_type = req.security_type
    if req.broker is not None:
        item.broker = req.broker
    if req.account_type is not None:
        item.account_type = req.account_type
    if req.notes is not None:
        item.notes = req.notes

    item.total_cost = item.shares * item.avg_price
    item.market_value = item.shares * item.current_price
    item.unrealized_pnl = item.market_value - item.total_cost
    item.unrealized_pnl_pct = (
        (item.unrealized_pnl / item.total_cost * 100) if item.total_cost else 0
    )
    item.last_updated = datetime.now(timezone.utc)

    db.commit()
    return {"message": "Portfolio updated", "ticker": item.ticker}


@app.delete("/api/portfolio/{item_id}")
def delete_portfolio_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a portfolio item."""
    item = db.query(PortfolioItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    db.delete(item)
    db.commit()
    return {"message": f"{item.ticker} dihapus dari portfolio"}


class BulkDeletePortfolioRequest(BaseModel):
    ids: list[int]

class BulkUpdateBrokerRequest(BaseModel):
    ids: list[int]
    broker: str


@app.post("/api/portfolio/bulk-update-broker")
def bulk_update_broker(req: BulkUpdateBrokerRequest, db: Session = Depends(get_db)):
    """Update broker for multiple portfolio items at once."""
    updated = []
    for item_id in req.ids:
        item = db.query(PortfolioItem).filter_by(id=item_id).first()
        if item:
            item.broker = req.broker
            updated.append(item.ticker)
    db.commit()
    return {"message": f"{len(updated)} saham diupdate ke broker {req.broker}", "updated": updated}


@app.post("/api/portfolio/bulk-delete")
def bulk_delete_portfolio(req: BulkDeletePortfolioRequest, db: Session = Depends(get_db)):
    """Delete multiple portfolio items at once."""
    deleted = []
    for item_id in req.ids:
        item = db.query(PortfolioItem).filter_by(id=item_id).first()
        if item:
            deleted.append(item.ticker)
            db.delete(item)
    db.commit()
    return {"message": f"{len(deleted)} item dihapus dari portfolio", "deleted": deleted}


@app.post("/api/portfolio/refresh")
async def refresh_portfolio(db: Session = Depends(get_db)):
    """Force refresh all portfolio prices."""
    items = db.query(PortfolioItem).all()
    updated = 0
    for item in items:
        try:
            data = fetch_stock_data(item.ticker)
            if "error" not in data:
                _update_item_price(item, data)
                updated += 1
        except Exception:
            logger.exception("Failed to refresh %s", item.ticker)
            continue
    db.commit()
    take_portfolio_snapshot(db)
    return {"message": f"{updated}/{len(items)} saham berhasil di-update"}


@app.get("/api/portfolio/history")
def get_portfolio_history(period: str = "all", db: Session = Depends(get_db)):
    """Get historical portfolio snapshots for charting."""
    from datetime import timedelta
    query = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date.asc())

    if period != "all":
        days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
        days = days_map.get(period, 9999)
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
        query = query.filter(PortfolioSnapshot.snapshot_date >= cutoff)

    snaps = query.all()
    return {
        "snapshots": [
            {
                "date": s.snapshot_date.isoformat(),
                "value": s.total_market_value,
                "cost": s.total_cost,
                "pnl": s.total_pnl,
                "pnl_pct": s.total_pnl_pct,
                "items": s.total_items,
            }
            for s in snaps
        ]
    }


# ── Screenshot OCR API ────────────────────────────────────────────────

@app.post("/api/ocr/screenshot")
async def process_screenshot(file: UploadFile = File(...)):
    """Process a screenshot to extract stock data."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar")

    contents = await file.read()
    result = extract_stocks_from_image(contents)
    return result


class OcrImportRequest(BaseModel):
    stocks: list[Any]
    broker: str = ""
    account_type: str = "Reguler"


@app.post("/api/ocr/import")
async def import_from_ocr(req: OcrImportRequest, db: Session = Depends(get_db)):
    """Import stocks from OCR results into portfolio and watchlist."""
    imported = []
    skipped = []
    for stock in req.stocks:
        ticker = stock.get("ticker", "").upper()
        if not ticker:
            continue

        # Skip delisted stocks (only when paste data explicitly has last_price=0 AND value=0)
        paste_last = stock.get("last_price")
        paste_value = stock.get("value")
        if paste_last is not None and paste_value is not None and paste_last == 0 and paste_value == 0:
            continue

        # Always add to watchlist regardless of portfolio status
        wl = db.query(Watchlist).filter_by(ticker=ticker).first()
        if not wl:
            db.add(Watchlist(ticker=ticker))

        existing = db.query(PortfolioItem).filter_by(
            ticker=ticker, broker=req.broker, account_type=req.account_type
        ).first()
        if existing:
            # Skip if same ticker+broker+account already exists
            skipped.append(ticker)
            continue

        data = fetch_stock_data(ticker)
        current_price = data.get("last_price", 0)
        company_name = data.get("company_name", ticker)
        sector = data.get("sector", "Other")

        lot = stock.get("lot", 0)
        shares = stock.get("shares", lot * 100)
        avg_price = stock.get("avg_price", current_price)
        total_cost = shares * avg_price
        market_value = shares * current_price

        item = PortfolioItem(
            ticker=ticker,
            company_name=company_name,
            security_type="Saham",
            sub_sector=sector,
            lot=lot,
            shares=shares,
            avg_price=avg_price,
            total_cost=total_cost,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=market_value - total_cost,
            unrealized_pnl_pct=((market_value - total_cost) / total_cost * 100) if total_cost else 0,
            broker=req.broker,
            account_type=req.account_type,
        )
        db.add(item)

        imported.append(ticker)

    db.commit()
    return {"imported": imported, "skipped": skipped, "count": len(imported), "skipped_count": len(skipped)}


# ── Watchlist API ─────────────────────────────────────────────────────

@app.get("/api/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    """Get watchlist with live prices."""
    # Auto-sync: ensure all portfolio tickers are in watchlist
    portfolio_tickers = {p.ticker for p in db.query(PortfolioItem).all()}
    watchlist_tickers = {w.ticker for w in db.query(Watchlist).all()}
    for ticker in portfolio_tickers - watchlist_tickers:
        db.add(Watchlist(ticker=ticker))
    if portfolio_tickers - watchlist_tickers:
        db.commit()

    items = db.query(Watchlist).all()
    # Batch-fetch all caches in one query (avoid N+1)
    all_caches = {c.ticker: c for c in db.query(StockCache).all()}
    result = []
    for item in items:
        cache = all_caches.get(item.ticker)
        if cache:
            result.append({
                "ticker": cache.ticker,
                "company_name": cache.company_name,
                "last_price": cache.last_price,
                "change": cache.change,
                "change_pct": cache.change_pct,
                "volume": cache.volume,
                "market_cap": cache.market_cap,
            })
        else:
            data = fetch_stock_data(item.ticker)
            result.append({
                "ticker": item.ticker,
                "company_name": data.get("company_name", item.ticker),
                "last_price": data.get("last_price", 0),
                "change": data.get("change", 0),
                "change_pct": data.get("change_pct", 0),
                "volume": data.get("volume", 0),
                "market_cap": data.get("market_cap", 0),
            })
    return {"watchlist": result}


class BulkDeleteWatchlistRequest(BaseModel):
    tickers: list[str]


@app.post("/api/watchlist/bulk-delete")
def bulk_delete_watchlist(req: BulkDeleteWatchlistRequest, db: Session = Depends(get_db)):
    """Delete multiple watchlist items at once."""
    deleted = []
    for ticker in req.tickers:
        ticker = ticker.upper().replace(".JK", "")
        item = db.query(Watchlist).filter_by(ticker=ticker).first()
        if item:
            deleted.append(ticker)
            db.delete(item)
    db.commit()
    return {"message": f"{len(deleted)} item dihapus dari watchlist", "deleted": deleted}


@app.post("/api/watchlist/{ticker}")
def add_to_watchlist(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper().replace(".JK", "")
    existing = db.query(Watchlist).filter_by(ticker=ticker).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{ticker} sudah ada di watchlist")
    db.add(Watchlist(ticker=ticker))
    db.commit()
    return {"message": f"{ticker} ditambahkan ke watchlist"}


@app.delete("/api/watchlist/{ticker}")
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper().replace(".JK", "")
    item = db.query(Watchlist).filter_by(ticker=ticker).first()
    if not item:
        raise HTTPException(status_code=404, detail="Ticker tidak ada di watchlist")
    db.delete(item)
    db.commit()
    return {"message": f"{ticker} dihapus dari watchlist"}


# ── Save / Load Portfolio ─────────────────────────────────────────────

@app.get("/api/portfolio/export")
def export_portfolio(db: Session = Depends(get_db)):
    """Export full portfolio + watchlist as JSON backup."""
    import json as _json
    items = db.query(PortfolioItem).all()
    watchlist = db.query(Watchlist).all()
    snapshots = db.query(PortfolioSnapshot).all()

    data = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": [
            {
                "ticker": i.ticker, "company_name": i.company_name,
                "security_type": i.security_type, "sub_sector": i.sub_sector,
                "lot": i.lot, "shares": i.shares, "avg_price": i.avg_price,
                "total_cost": i.total_cost, "current_price": i.current_price,
                "market_value": i.market_value, "unrealized_pnl": i.unrealized_pnl,
                "unrealized_pnl_pct": i.unrealized_pnl_pct,
                "broker": i.broker or "", "account_type": i.account_type or "Reguler",
                "notes": i.notes or "",
            }
            for i in items
        ],
        "watchlist": [w.ticker for w in watchlist],
        "snapshots": [
            {
                "date": s.snapshot_date.isoformat(),
                "total_cost": s.total_cost, "total_market_value": s.total_market_value,
                "total_pnl": s.total_pnl, "total_pnl_pct": s.total_pnl_pct,
                "total_items": s.total_items,
            }
            for s in snapshots
        ],
    }
    content = _json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=portico_backup.json"},
    )


class ImportPortfolioRequest(BaseModel):
    data: dict


@app.post("/api/portfolio/import")
def import_portfolio(req: ImportPortfolioRequest, db: Session = Depends(get_db)):
    """Import portfolio from JSON backup. Skips duplicates."""
    data = req.data
    if data.get("version") != 1:
        raise HTTPException(status_code=400, detail="Format backup tidak valid")

    imported = 0
    skipped = 0
    for item in data.get("portfolio", []):
        ticker = item.get("ticker", "").upper()
        if not ticker:
            continue
        broker = item.get("broker", "")
        account_type = item.get("account_type", "Reguler")
        existing = db.query(PortfolioItem).filter_by(
            ticker=ticker, broker=broker, account_type=account_type
        ).first()
        if existing:
            skipped += 1
            continue
        db.add(PortfolioItem(
            ticker=ticker,
            company_name=item.get("company_name", ticker),
            security_type=item.get("security_type", "Saham"),
            sub_sector=item.get("sub_sector", "Other"),
            lot=item.get("lot", 0),
            shares=item.get("shares", 0),
            avg_price=item.get("avg_price", 0),
            total_cost=item.get("total_cost", 0),
            current_price=item.get("current_price", 0),
            market_value=item.get("market_value", 0),
            unrealized_pnl=item.get("unrealized_pnl", 0),
            unrealized_pnl_pct=item.get("unrealized_pnl_pct", 0),
            broker=broker,
            account_type=account_type,
            notes=item.get("notes", ""),
        ))
        imported += 1

    # Import watchlist
    wl_imported = 0
    for ticker in data.get("watchlist", []):
        ticker = ticker.upper()
        if not db.query(Watchlist).filter_by(ticker=ticker).first():
            db.add(Watchlist(ticker=ticker))
            wl_imported += 1

    # Import snapshots
    snap_imported = 0
    for s in data.get("snapshots", []):
        from datetime import date as _date
        snap_date = _date.fromisoformat(s["date"])
        if not db.query(PortfolioSnapshot).filter_by(snapshot_date=snap_date).first():
            db.add(PortfolioSnapshot(
                snapshot_date=snap_date,
                total_cost=s.get("total_cost", 0),
                total_market_value=s.get("total_market_value", 0),
                total_pnl=s.get("total_pnl", 0),
                total_pnl_pct=s.get("total_pnl_pct", 0),
                total_items=s.get("total_items", 0),
            ))
            snap_imported += 1

    db.commit()
    return {
        "message": f"{imported} saham diimport, {skipped} duplikat diskip, {wl_imported} watchlist, {snap_imported} snapshot",
        "imported": imported, "skipped": skipped,
        "watchlist_imported": wl_imported, "snapshots_imported": snap_imported,
    }


@app.post("/api/portfolio/clear-all")
def clear_all_data(db: Session = Depends(get_db)):
    """Delete ALL data: portfolio, watchlist, cache, and history snapshots."""
    p = db.query(PortfolioItem).delete()
    w = db.query(Watchlist).delete()
    s = db.query(PortfolioSnapshot).delete()
    c = db.query(StockCache).delete()
    db.commit()
    return {"message": f"Semua data dihapus: {p} portfolio, {w} watchlist, {s} snapshot, {c} cache"}


# ── Search API ────────────────────────────────────────────────────────

@app.get("/api/search")
async def search_stock(q: str = Query(..., min_length=1)):
    """Search for a stock ticker."""
    q = q.upper().strip()
    data = fetch_stock_data(q)
    if "error" in data and "last_price" not in data:
        return {"results": [], "query": q}
    return {"results": [data], "query": q}


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  Portico Terminal - Indonesian Stock Terminal")
    print("  Buka browser: http://localhost:8000")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
