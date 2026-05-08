"""REST endpoints for price alerts. Mirrors merriot/routes.py style."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import PriceAlert
from backend.alerts import storage

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_TICKER_RE = re.compile(r"^[A-Z0-9]{3,6}$")
_VALID_DIR = {"above", "below"}
_VALID_STATUS = {"armed", "triggered", "cancelled", "expired"}


def _serialize(a: PriceAlert) -> dict:
    return {
        "id": a.id,
        "ticker": a.ticker,
        "direction": a.direction,
        "threshold_price": a.threshold_price,
        "label": a.label,
        "status": a.status,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        "triggered_price": a.triggered_price,
        "drift_pct": a.drift_pct,
        "last_check_price": a.last_check_price,
        "last_checked_at": a.last_checked_at.isoformat() if a.last_checked_at else None,
        "chat_id": a.chat_id,
        "source": a.source,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


class CreateAlertIn(BaseModel):
    ticker: str = Field(..., min_length=3, max_length=10)
    direction: str = Field(..., pattern="^(above|below)$")
    threshold_price: float = Field(..., gt=0)
    label: Optional[str] = Field("", max_length=200)


class UpdateAlertIn(BaseModel):
    label: Optional[str] = None
    status: Optional[str] = None


@router.get("")
def list_alerts(
    status: str = "",
    ticker: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(PriceAlert)
    if status:
        q = q.filter(PriceAlert.status == status)
    if ticker:
        q = q.filter(PriceAlert.ticker == ticker.upper())
    rows = q.order_by(PriceAlert.created_at.desc()).limit(min(limit, 500)).all()
    return {"alerts": [_serialize(a) for a in rows]}


@router.get("/{alert_id}")
def get_one(alert_id: int, db: Session = Depends(get_db)):
    a = storage.get_alert(db, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    return _serialize(a)


@router.post("")
def create_alert(payload: CreateAlertIn, db: Session = Depends(get_db)):
    ticker = payload.ticker.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(400, "invalid ticker format")
    if payload.direction not in _VALID_DIR:
        raise HTTPException(400, "direction must be 'above' or 'below'")
    # Dedup check (mirrors Telegram path) — refuse near-duplicate within 24h.
    dups = storage.find_duplicates(db, ticker, payload.direction,
                                   payload.threshold_price, window_h=24, tolerance=0.005)
    if dups:
        raise HTTPException(409, f"duplicate of armed alert #{dups[0].id}")
    a = storage.create_alert(
        db,
        ticker=ticker,
        direction=payload.direction,
        threshold=payload.threshold_price,
        label=payload.label or "",
        source="web",
    )
    return _serialize(a)


@router.put("/{alert_id}")
def update_alert(alert_id: int, payload: UpdateAlertIn, db: Session = Depends(get_db)):
    a = storage.get_alert(db, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    if payload.label is not None:
        a.label = payload.label[:200]
    if payload.status is not None:
        # Restrict transitions: only armed → cancelled or armed → expired allowed.
        # 'triggered' is cron-only path (preserves drift_pct + triggered_price integrity).
        allowed = {"cancelled", "expired"}
        if payload.status not in allowed:
            raise HTTPException(400, f"status via PUT must be one of {allowed} (use cron/handlers for triggered)")
        if a.status != "armed":
            raise HTTPException(400, f"cannot transition from {a.status} via PUT")
        a.status = payload.status
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    a = storage.get_alert(db, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    db.delete(a)
    db.commit()
    return {"deleted": alert_id}


@router.post("/{alert_id}/cancel")
def cancel_alert(alert_id: int, db: Session = Depends(get_db)):
    a = storage.cancel(db, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    return _serialize(a)


@router.post("/check")
async def trigger_check_now():
    """Admin / debugging — run scan_and_evaluate once immediately."""
    from backend.alerts.cron import scan_and_evaluate
    result = await scan_and_evaluate()
    return result
