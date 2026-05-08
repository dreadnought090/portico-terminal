"""Ginger tool definitions for Claude function calling.

Each tool: schema (JSON for Claude) + Python executor (queries Portico DB
directly, no HTTP roundtrip).

v1 = READ-ONLY. No writes, no DB modification. Safe by design.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    PortfolioItem, ThesisNote, PriceAlert, Watchlist, StockCache,
)

logger = logging.getLogger("ginger.tools")


# ── Tool schemas (Claude function calling format) ───────────────────

TOOL_SCHEMAS = [
    {
        "name": "get_portfolio_summary",
        "description": "Ringkasan total portofolio: jumlah posisi, total cost, total market value, P&L, top 5 posisi.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_holdings",
        "description": "List semua holdings di portofolio. Bisa filter by ticker, broker, sektor, atau security_type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker_contains": {"type": "string", "description": "Filter ticker yang mengandung text ini (e.g. 'BB' → BBCA, BBRI, BBNI)"},
                "broker": {"type": "string", "description": "Filter by broker (case-insensitive substring match, e.g. 'mirae')"},
                "sector": {"type": "string", "description": "Filter by sub_sector (e.g. 'Banking')"},
                "security_type": {"type": "string", "description": "Filter by type: Saham|Obligasi|Reksadana|ETF|Warrant|Right|Lainnya"},
                "min_pnl_pct": {"type": "number", "description": "Hanya posisi dengan P&L% >= ini"},
                "max_pnl_pct": {"type": "number", "description": "Hanya posisi dengan P&L% <= ini"},
            },
        },
    },
    {
        "name": "get_stock_detail",
        "description": "Detail single ticker: holding, harga current, P&L, jumlah thesis note, alert armed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker, e.g. 'BBCA'"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "list_thesis",
        "description": "List thesis notes (Merriot). Filter by ticker, status, atau direction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "reviewed", "invalid"]},
                "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral", "exit"]},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "list_alerts",
        "description": "List price alerts. Filter by ticker atau status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "status": {"type": "string", "enum": ["armed", "triggered", "cancelled"]},
            },
        },
    },
    {
        "name": "list_due_thesis",
        "description": "Thesis yang due (review_at) dalam N hari kedepan. Default 7 hari.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "list_watchlist",
        "description": "Saham di watchlist (incaran, belum dibeli).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_brokers",
        "description": "List broker yang dipakai user + jumlah ticker per broker.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_transaction",
        "description": (
            "Catat transaksi saham (beli/jual). WAJIB user-confirmation via tombol — "
            "TIDAK auto-apply. Pakai tool ini ketika user bilang sudah beli/jual "
            "saham (mis. 'tadi jual 5 lot BBCA harga 6000 di Mirae'). Tool insert "
            "pending tx + balas dengan tombol Confirm/Reject. Jangan invent angka — "
            "kalau user gak sebut harga atau broker, tanyakan dulu sebelum panggil tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["buy", "sell"]},
                "ticker": {"type": "string", "description": "4-letter IDX ticker, e.g. BBCA"},
                "lot": {"type": "integer", "description": "Jumlah lot (1 lot = 100 shares)"},
                "price": {"type": "number", "description": "Harga per saham (IDR)"},
                "broker": {"type": "string", "description": "Nama broker (e.g. 'Mirae Asset', 'BNI Sekuritas')"},
                "trade_date": {"type": "string", "description": "YYYY-MM-DD; kalau gak disebut user, omit (default = hari ini)"},
            },
            "required": ["action", "ticker", "lot", "price"],
        },
    },
]


# ── Executors ─────────────────────────────────────────────────────────

def _serialize_holding(p: PortfolioItem) -> dict:
    return {
        "ticker": p.ticker,
        "company_name": p.company_name or "",
        "type": p.security_type,
        "sector": p.sub_sector or "",
        "lot": p.lot,
        "shares": p.shares,
        "avg_price": round(p.avg_price or 0, 2),
        "current_price": round(p.current_price or 0, 2),
        "market_value": round(p.market_value or 0, 0),
        "total_cost": round(p.total_cost or 0, 0),
        "pnl": round(p.unrealized_pnl or 0, 0),
        "pnl_pct": round(p.unrealized_pnl_pct or 0, 2),
        "broker": p.broker or "",
    }


def get_portfolio_summary() -> dict:
    db = SessionLocal()
    try:
        items = db.query(PortfolioItem).all()
        if not items:
            return {"empty": True, "message": "Portofolio kosong."}
        total_cost = sum(i.total_cost or 0 for i in items)
        total_mv = sum(i.market_value or 0 for i in items)
        total_pnl = total_mv - total_cost
        pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
        # Top 5 by market value
        sorted_items = sorted(items, key=lambda x: x.market_value or 0, reverse=True)
        top_5 = [_serialize_holding(p) for p in sorted_items[:5]]
        return {
            "total_positions": len(items),
            "total_cost_idr": round(total_cost, 0),
            "total_market_value_idr": round(total_mv, 0),
            "total_pnl_idr": round(total_pnl, 0),
            "total_pnl_pct": round(pnl_pct, 2),
            "top_5_positions": top_5,
        }
    finally:
        db.close()


def list_holdings(
    ticker_contains: str = "",
    broker: str = "",
    sector: str = "",
    security_type: str = "",
    min_pnl_pct: float | None = None,
    max_pnl_pct: float | None = None,
) -> dict:
    db = SessionLocal()
    try:
        q = db.query(PortfolioItem)
        if ticker_contains:
            q = q.filter(PortfolioItem.ticker.contains(ticker_contains.upper()))
        if broker:
            q = q.filter(PortfolioItem.broker.ilike(f"%{broker}%"))
        if sector:
            q = q.filter(PortfolioItem.sub_sector.ilike(f"%{sector}%"))
        if security_type:
            q = q.filter(PortfolioItem.security_type.ilike(security_type))
        items = q.order_by(PortfolioItem.market_value.desc()).all()

        if min_pnl_pct is not None:
            items = [i for i in items if (i.unrealized_pnl_pct or 0) >= min_pnl_pct]
        if max_pnl_pct is not None:
            items = [i for i in items if (i.unrealized_pnl_pct or 0) <= max_pnl_pct]

        return {
            "count": len(items),
            "holdings": [_serialize_holding(p) for p in items],
        }
    finally:
        db.close()


def get_stock_detail(ticker: str) -> dict:
    code = ticker.upper().replace(".JK", "").strip()
    db = SessionLocal()
    try:
        items = db.query(PortfolioItem).filter(PortfolioItem.ticker == code).all()
        thesis_count = db.query(func.count(ThesisNote.id)).filter(ThesisNote.ticker == code).scalar() or 0
        thesis_pending = db.query(func.count(ThesisNote.id)).filter(
            ThesisNote.ticker == code, ThesisNote.status == "pending"
        ).scalar() or 0
        alert_armed = db.query(func.count(PriceAlert.id)).filter(
            PriceAlert.ticker == code, PriceAlert.status == "armed"
        ).scalar() or 0
        cache = db.query(StockCache).filter(StockCache.ticker == code).first()

        # Aggregate holdings (could be multi-broker)
        total_lot = sum(i.lot or 0 for i in items)
        total_shares = sum(i.shares or 0 for i in items)
        total_cost = sum(i.total_cost or 0 for i in items)
        total_mv = sum(i.market_value or 0 for i in items)
        avg_price = (total_cost / total_shares) if total_shares else 0
        brokers = sorted({i.broker for i in items if i.broker})

        return {
            "ticker": code,
            "in_portfolio": len(items) > 0,
            "total_lot": total_lot,
            "total_shares": total_shares,
            "avg_price": round(avg_price, 2),
            "current_price": round(cache.last_price if cache else 0, 2),
            "total_cost": round(total_cost, 0),
            "market_value": round(total_mv, 0),
            "pnl": round(total_mv - total_cost, 0),
            "pnl_pct": round(((total_mv - total_cost) / total_cost * 100) if total_cost else 0, 2),
            "brokers": brokers,
            "company_name": (items[0].company_name if items else "") or (cache.company_name if cache else ""),
            "sector": (items[0].sub_sector if items else "") or (cache.sub_sector if cache else ""),
            "thesis_total": thesis_count,
            "thesis_pending": thesis_pending,
            "alerts_armed": alert_armed,
        }
    finally:
        db.close()


def list_thesis(ticker: str = "", status: str = "", direction: str = "", limit: int = 20) -> dict:
    db = SessionLocal()
    try:
        q = db.query(ThesisNote)
        if ticker:
            q = q.filter(ThesisNote.ticker == ticker.upper())
        if status:
            q = q.filter(ThesisNote.status == status)
        if direction:
            q = q.filter(ThesisNote.thesis_direction == direction)
        notes = q.order_by(ThesisNote.created_at.desc()).limit(min(limit, 50)).all()
        return {
            "count": len(notes),
            "notes": [{
                "id": n.id, "ticker": n.ticker,
                "type": n.thesis_type, "direction": n.thesis_direction,
                "status": n.status,
                "key_points": n.key_points or [],
                "tags": n.tags or [],
                "review_at": n.review_at.isoformat() if n.review_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            } for n in notes],
        }
    finally:
        db.close()


def list_alerts(ticker: str = "", status: str = "") -> dict:
    db = SessionLocal()
    try:
        q = db.query(PriceAlert)
        if ticker:
            q = q.filter(PriceAlert.ticker == ticker.upper())
        if status:
            q = q.filter(PriceAlert.status == status)
        alerts = q.order_by(PriceAlert.created_at.desc()).limit(50).all()
        return {
            "count": len(alerts),
            "alerts": [{
                "id": a.id, "ticker": a.ticker,
                "direction": a.direction, "threshold": a.threshold_price,
                "label": a.label, "status": a.status,
                "last_check_price": a.last_check_price,
                "triggered_price": a.triggered_price,
            } for a in alerts],
        }
    finally:
        db.close()


def list_due_thesis(days: int = 7) -> dict:
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=days)
        notes = (
            db.query(ThesisNote)
            .filter(
                ThesisNote.status == "pending",
                ThesisNote.review_at != None,  # noqa: E711
                ThesisNote.review_at <= cutoff,
            )
            .order_by(ThesisNote.review_at.asc())
            .all()
        )
        return {
            "count": len(notes),
            "due": [{
                "id": n.id, "ticker": n.ticker,
                "review_at": n.review_at.isoformat() if n.review_at else None,
                "key_points": n.key_points or [],
            } for n in notes],
        }
    finally:
        db.close()


def list_watchlist() -> dict:
    db = SessionLocal()
    try:
        items = db.query(Watchlist).order_by(Watchlist.added_at.desc()).all()
        return {
            "count": len(items),
            "tickers": [w.ticker for w in items],
        }
    finally:
        db.close()


def propose_transaction(
    action: str, ticker: str, lot: int, price: float,
    broker: str = "", trade_date: str = "",
) -> dict:
    """Insert pending EmailTransaction (source=chat). Returns tx_id +
    marker '_requires_buttons' so agent.chat_turn picks it up for follow-up DM.
    """
    import uuid
    from datetime import datetime, date as date_cls, timezone
    from backend.models import EmailTransaction

    action_lower = (action or "").lower()
    if action_lower not in ("buy", "sell"):
        return {"error": "action must be buy or sell"}
    code = (ticker or "").upper().strip()
    if not code or len(code) < 3 or len(code) > 6:
        return {"error": f"invalid ticker: {ticker!r}"}
    try:
        lot_int = int(lot)
        price_f = float(price)
    except (TypeError, ValueError):
        return {"error": "lot/price not numeric"}
    if lot_int <= 0 or price_f <= 0:
        return {"error": "lot and price must be positive"}

    parsed_date = None
    if trade_date:
        try:
            parsed_date = date_cls.fromisoformat(trade_date)
        except ValueError:
            parsed_date = None
    if not parsed_date:
        parsed_date = date_cls.today()

    db = SessionLocal()
    try:
        tx = EmailTransaction(
            message_id=f"chat-{uuid.uuid4().hex[:16]}",
            email_subject="(manual entry via Ginger chat)",
            email_from="user-chat",
            email_received_at=datetime.now(timezone.utc),
            extracted_action=action_lower,
            extracted_ticker=code,
            extracted_lot=lot_int,
            extracted_shares=lot_int * 100,
            extracted_price=price_f,
            extracted_total_value=lot_int * 100 * price_f,
            extracted_broker=(broker or "").strip()[:100],
            extracted_trade_date=parsed_date,
            extraction_confidence=1.0,  # user-typed = ground truth
            extraction_raw="{}",
            status="pending",
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        tx_id = tx.id
    finally:
        db.close()

    return {
        "tx_id": tx_id,
        "action": action_lower,
        "ticker": code,
        "lot": lot_int,
        "shares": lot_int * 100,
        "price": price_f,
        "total_value": lot_int * 100 * price_f,
        "broker": broker,
        "trade_date": parsed_date.isoformat(),
        "status": "pending — awaiting user confirmation",
        "_requires_buttons": True,  # agent.chat_turn picks this up as side-effect
    }


def search_brokers() -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(PortfolioItem.broker, func.count(PortfolioItem.id))
            .group_by(PortfolioItem.broker)
            .all()
        )
        result = []
        for broker, count in rows:
            if not broker:
                broker = "(no broker set)"
            result.append({"broker": broker, "ticker_count": count})
        result.sort(key=lambda x: x["ticker_count"], reverse=True)
        return {"brokers": result, "total_brokers": len(result)}
    finally:
        db.close()


# ── Executor dispatch ────────────────────────────────────────────────

EXECUTORS = {
    "get_portfolio_summary": get_portfolio_summary,
    "list_holdings": list_holdings,
    "get_stock_detail": get_stock_detail,
    "list_thesis": list_thesis,
    "list_alerts": list_alerts,
    "list_due_thesis": list_due_thesis,
    "list_watchlist": list_watchlist,
    "search_brokers": search_brokers,
    "propose_transaction": propose_transaction,
}


def execute_tool(name: str, args: dict) -> Any:
    """Run tool by name with kwargs. Returns dict (or error dict)."""
    fn = EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"invalid args: {e}"}
    except Exception as e:
        logger.exception("tool %s execution failed", name)
        return {"error": f"execution failed: {e}"}
