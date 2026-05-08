"""Merriot REST endpoints — Portico web UI integration."""
from __future__ import annotations

from datetime import date as date_cls, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import ThesisNote
from backend.merriot import extractor, storage

router = APIRouter(prefix="/api/thesis", tags=["thesis"])


def _serialize(n: ThesisNote) -> dict:
    return {
        "id": n.id,
        "ticker": n.ticker,
        "body": n.body,
        "thesis_type": n.thesis_type,
        "thesis_direction": n.thesis_direction,
        "key_points": n.key_points or [],
        "tags": n.tags or [],
        "source": n.source,
        "confidence": n.confidence,
        "review_at": n.review_at.isoformat() if n.review_at else None,
        "review_reasoning": n.review_reasoning,
        "status": n.status,
        "reviewed_at": n.reviewed_at.isoformat() if n.reviewed_at else None,
        "follow_up": n.follow_up,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


import re as _re

_TICKER_PATTERN = _re.compile(r"^[A-Z0-9]{3,6}$")
_VALID_STATUS = {"pending", "reviewed", "invalid"}


class CreateNoteIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)
    auto_extract: bool = True
    # Manual override fields (used if auto_extract=False)
    ticker: Optional[str] = None
    review_at: Optional[date_cls] = None
    # Pre-extracted payload — if provided, skips a redundant LLM call
    extracted: Optional[dict] = None


class UpdateNoteIn(BaseModel):
    body: Optional[str] = None
    ticker: Optional[str] = None
    review_at: Optional[date_cls] = None
    status: Optional[str] = None
    follow_up: Optional[str] = None
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None


@router.get("")
def list_notes(
    ticker: str = "",
    status: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(ThesisNote)
    if ticker:
        q = q.filter(ThesisNote.ticker == ticker.upper())
    if status:
        q = q.filter(ThesisNote.status == status)
    rows = q.order_by(ThesisNote.created_at.desc()).limit(min(limit, 200)).all()
    return {"notes": [_serialize(n) for n in rows]}


@router.get("/due")
def due_notes(days: int = 7, db: Session = Depends(get_db)):
    rows = storage.list_due_within(db, days=days)
    return {"notes": [_serialize(n) for n in rows]}


@router.get("/{note_id}")
def get_one(note_id: int, db: Session = Depends(get_db)):
    n = storage.get_note(db, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    return _serialize(n)


@router.post("/extract")
async def preview_extract(payload: CreateNoteIn, db: Session = Depends(get_db)):
    """Dry-run: extract structure without saving. Used by UI for preview."""
    from backend.models import PortfolioItem, Watchlist
    port = [r.ticker for r in db.query(PortfolioItem.ticker).distinct().all()]
    wl = [r.ticker for r in db.query(Watchlist.ticker).distinct().all()]
    result = await extractor.extract(payload.body, port, wl)
    if isinstance(result, extractor.ExtractionError):
        return {"error": result.error, "suggestion": result.suggestion}
    return {
        "ticker": result.ticker,
        "thesis_type": result.thesis_type,
        "thesis_direction": result.thesis_direction,
        "key_points": result.key_points,
        "tags": result.tags,
        "suggested_review_date": result.suggested_review_date.isoformat(),
        "review_reasoning": result.review_reasoning,
        "confidence": result.confidence,
        "warnings": result.warnings,
    }


@router.post("")
async def create_note(payload: CreateNoteIn, db: Session = Depends(get_db)):
    """Create a note. Skips LLM if pre-extracted payload is provided."""
    if payload.extracted:
        # Web UI flow: preview already happened, reuse those fields. No LLM call.
        ext = payload.extracted
        ticker = ext.get("ticker")
        if isinstance(ticker, list):
            ticker = ticker[0] if ticker else None
        if not ticker or not _TICKER_PATTERN.match(str(ticker).upper().strip()):
            raise HTTPException(400, "invalid ticker in extracted payload")
        review_at = ext.get("suggested_review_date")
        if isinstance(review_at, str):
            review_at = date_cls.fromisoformat(review_at)
        note = storage.create_note(
            db,
            ticker=str(ticker).upper().strip(),
            body=payload.body,
            thesis_type=ext.get("thesis_type", "other"),
            thesis_direction=ext.get("thesis_direction", "neutral"),
            key_points=ext.get("key_points", []),
            tags=ext.get("tags", []),
            source="web",
            confidence=float(ext.get("confidence", 0.0)),
            review_at=review_at,
            review_reasoning=ext.get("review_reasoning", ""),
        )
        return _serialize(note)

    if payload.auto_extract:
        from backend.models import PortfolioItem, Watchlist
        port = [r.ticker for r in db.query(PortfolioItem.ticker).distinct().all()]
        wl = [r.ticker for r in db.query(Watchlist.ticker).distinct().all()]
        result = await extractor.extract(payload.body, port, wl)
        if isinstance(result, extractor.ExtractionError):
            raise HTTPException(400, f"{result.error}: {result.suggestion}")
        ticker = result.ticker[0] if isinstance(result.ticker, list) else result.ticker
        note = storage.create_note(
            db,
            ticker=ticker,
            body=payload.body,
            thesis_type=result.thesis_type,
            thesis_direction=result.thesis_direction,
            key_points=result.key_points,
            tags=result.tags,
            source="web",
            confidence=result.confidence,
            review_at=result.suggested_review_date,
            review_reasoning=result.review_reasoning,
        )
    else:
        ticker = (payload.ticker or "").upper().strip()
        if not ticker or not _TICKER_PATTERN.match(ticker):
            raise HTTPException(400, "ticker required (3-6 uppercase chars) when auto_extract=False")
        note = storage.create_note(
            db,
            ticker=ticker,
            body=payload.body,
            source="web",
            review_at=payload.review_at,
        )
    return _serialize(note)


@router.put("/{note_id}")
def update_note(note_id: int, payload: UpdateNoteIn, db: Session = Depends(get_db)):
    n = storage.get_note(db, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    if payload.body is not None:
        n.body = payload.body
    if payload.ticker is not None:
        ticker = payload.ticker.upper().strip()
        if not _TICKER_PATTERN.match(ticker):
            raise HTTPException(400, "invalid ticker (must be 3-6 uppercase chars)")
        n.ticker = ticker
    if payload.review_at is not None:
        n.review_at = payload.review_at
        # Reset reminder log so new date triggers fresh
        from backend.models import ThesisReminderLog
        db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    if payload.status is not None:
        if payload.status not in _VALID_STATUS:
            raise HTTPException(400, f"invalid status (must be one of {_VALID_STATUS})")
        prev_status = n.status
        n.status = payload.status
        if payload.status == "reviewed":
            n.reviewed_at = datetime.now(timezone.utc)
        # If status flips back to pending, re-arm reminders.
        if payload.status == "pending" and prev_status != "pending":
            from backend.models import ThesisReminderLog
            db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    if payload.follow_up is not None:
        n.follow_up = payload.follow_up
    if payload.key_points is not None:
        n.key_points = payload.key_points
    if payload.tags is not None:
        n.tags = [t.lower().strip() for t in payload.tags if t.strip()]
    db.commit()
    db.refresh(n)
    return _serialize(n)


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    ok = storage.delete_note(db, note_id)
    if not ok:
        raise HTTPException(404, "note not found")
    return {"deleted": note_id}


@router.post("/{note_id}/reviewed")
def mark_reviewed(note_id: int, follow_up: str = "", db: Session = Depends(get_db)):
    n = storage.mark_reviewed(db, note_id, follow_up=follow_up)
    if not n:
        raise HTTPException(404, "note not found")
    return _serialize(n)


@router.post("/{note_id}/postpone")
def postpone(note_id: int, days: int = 7, db: Session = Depends(get_db)):
    n = storage.postpone(db, note_id, days=days)
    if not n:
        raise HTTPException(404, "note not found")
    return _serialize(n)
