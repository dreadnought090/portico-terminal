"""IdxTicker query helpers — read-only access for other modules."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import IdxTicker


def get_by_code(code: str) -> dict | None:
    """Lookup single ticker. Returns dict or None."""
    code = (code or "").strip().upper()
    if not code:
        return None
    db = SessionLocal()
    try:
        row = db.query(IdxTicker).filter(IdxTicker.code == code).first()
        if not row:
            return None
        return _to_dict(row)
    finally:
        db.close()


def is_valid_ticker(code: str) -> bool:
    """True if ticker exists in registry (active OR inactive)."""
    code = (code or "").strip().upper()
    if not code:
        return False
    db = SessionLocal()
    try:
        return db.query(IdxTicker).filter(IdxTicker.code == code).first() is not None
    finally:
        db.close()


def list_active_codes() -> list[str]:
    """All currently-listed ticker codes. Used for Merriot context injection."""
    db = SessionLocal()
    try:
        rows = db.query(IdxTicker.code).filter(IdxTicker.is_active == 1).order_by(IdxTicker.code).all()
        return [r[0] for r in rows]
    finally:
        db.close()


def list_active() -> list[dict]:
    """All currently-listed tickers with full metadata."""
    db = SessionLocal()
    try:
        rows = db.query(IdxTicker).filter(IdxTicker.is_active == 1).order_by(IdxTicker.code).all()
        return [_to_dict(r) for r in rows]
    finally:
        db.close()


def search(query: str, limit: int = 20) -> list[dict]:
    """Search by code prefix or name (case-insensitive)."""
    q = (query or "").strip().upper()
    if not q:
        return []
    db = SessionLocal()
    try:
        from sqlalchemy import or_, func
        rows = db.query(IdxTicker).filter(
            IdxTicker.is_active == 1,
            or_(
                IdxTicker.code.like(f"{q}%"),
                func.upper(IdxTicker.name).like(f"%{q}%"),
            ),
        ).order_by(IdxTicker.code).limit(limit).all()
        return [_to_dict(r) for r in rows]
    finally:
        db.close()


def count() -> dict:
    """Stats."""
    db = SessionLocal()
    try:
        total = db.query(IdxTicker).count()
        active = db.query(IdxTicker).filter(IdxTicker.is_active == 1).count()
        return {"total": total, "active": active, "inactive": total - active}
    finally:
        db.close()


def _to_dict(row: IdxTicker) -> dict:
    return {
        "code": row.code,
        "name": row.name or "",
        "sector": row.sector or "",
        "last_close": float(row.last_close or 0),
        "market_cap": float(row.market_cap or 0),
        "is_active": bool(row.is_active),
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }
