"""Merriot storage helpers — query layer over ThesisNote / ThesisReminderLog."""
from __future__ import annotations

from datetime import datetime, timedelta, date as date_cls, timezone
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models import ThesisNote, ThesisReminderLog
from backend.merriot.config import WIB


def _today_wib() -> date_cls:
    return datetime.now(WIB).date()


def create_note(
    db: Session, *,
    ticker: str,
    body: str,
    thesis_type: str = "other",
    thesis_direction: str = "neutral",
    key_points: list[str] | None = None,
    tags: list[str] | None = None,
    source: str = "telegram",
    confidence: float = 0.0,
    review_at: date_cls | None = None,
    review_reasoning: str = "",
) -> ThesisNote:
    note = ThesisNote(
        ticker=ticker.upper(),
        body=body,
        thesis_type=thesis_type,
        thesis_direction=thesis_direction,
        key_points=key_points or [],
        tags=tags or [],
        source=source,
        confidence=confidence,
        review_at=review_at or (_today_wib() + timedelta(days=30)),
        review_reasoning=review_reasoning,
        status="pending",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def get_note(db: Session, note_id: int) -> Optional[ThesisNote]:
    return db.query(ThesisNote).filter(ThesisNote.id == note_id).first()


def list_for_ticker(db: Session, ticker: str, limit: int = 50) -> list[ThesisNote]:
    return (
        db.query(ThesisNote)
        .filter(ThesisNote.ticker == ticker.upper())
        .order_by(ThesisNote.created_at.desc())
        .limit(limit)
        .all()
    )


def list_recent(db: Session, limit: int = 10) -> list[ThesisNote]:
    return (
        db.query(ThesisNote)
        .order_by(ThesisNote.created_at.desc())
        .limit(limit)
        .all()
    )


def latest_pending_for_ticker(db: Session, ticker: str) -> Optional[ThesisNote]:
    """Most recent pending note for ticker — used by 'add MDIA ...' shortcut."""
    return (
        db.query(ThesisNote)
        .filter(ThesisNote.ticker == ticker.upper(), ThesisNote.status == "pending")
        .order_by(ThesisNote.created_at.desc())
        .first()
    )


def append_to_note(db: Session, note_id: int, addition_text: str,
                   addition_key_point: str | None = None) -> Optional[ThesisNote]:
    """Append new info to existing note's body + key_points. Refreshes updated_at."""
    from datetime import datetime
    note = get_note(db, note_id)
    if not note:
        return None
    timestamp = datetime.now().strftime("%-d %b %H:%M")
    note.body = (note.body or "") + f"\n\n[{timestamp}] {addition_text}"
    new_kp = (addition_key_point or addition_text).strip()
    if new_kp:
        existing = list(note.key_points or [])
        existing.append(new_kp[:100])
        note.key_points = existing
    db.commit()
    db.refresh(note)
    return note


def list_all(db: Session, limit: int = 50, status: str | None = None) -> tuple[list[ThesisNote], int]:
    """All notes, newest first. Returns (notes, total_count) — total may exceed limit."""
    q = db.query(ThesisNote)
    if status:
        q = q.filter(ThesisNote.status == status)
    total = q.count()
    notes = q.order_by(ThesisNote.created_at.desc()).limit(limit).all()
    return notes, total


def list_tickers_with_counts(db: Session) -> list[dict]:
    """Per-ticker aggregates: total, pending, reviewed, invalid, last note date.

    Used by /tickers (Telegram) and /api/thesis/tickers (web). Sorted by
    most recent note first.
    """
    from sqlalchemy import func
    rows = (
        db.query(
            ThesisNote.ticker,
            func.count(ThesisNote.id).label("total"),
            func.sum(
                func.coalesce(
                    func.iif(ThesisNote.status == "pending", 1, 0)
                    if hasattr(func, "iif")
                    else (ThesisNote.status == "pending"),
                    0,
                )
            ).label("pending"),
            func.max(ThesisNote.created_at).label("last_at"),
        )
        .group_by(ThesisNote.ticker)
        .order_by(func.max(ThesisNote.created_at).desc())
        .all()
    )
    out = []
    for r in rows:
        # Count by status (separate small queries — keeps cross-DB compat)
        pending = db.query(func.count(ThesisNote.id)).filter(
            ThesisNote.ticker == r.ticker, ThesisNote.status == "pending"
        ).scalar() or 0
        reviewed = db.query(func.count(ThesisNote.id)).filter(
            ThesisNote.ticker == r.ticker, ThesisNote.status == "reviewed"
        ).scalar() or 0
        invalid = db.query(func.count(ThesisNote.id)).filter(
            ThesisNote.ticker == r.ticker, ThesisNote.status == "invalid"
        ).scalar() or 0
        out.append({
            "ticker": r.ticker,
            "total": int(r.total),
            "pending": int(pending),
            "reviewed": int(reviewed),
            "invalid": int(invalid),
            "last_at": r.last_at,
        })
    return out


def list_due_within(db: Session, days: int = 7) -> list[ThesisNote]:
    today = _today_wib()
    end = today + timedelta(days=days)
    return (
        db.query(ThesisNote)
        .filter(
            ThesisNote.status == "pending",
            ThesisNote.review_at != None,  # noqa: E711
            ThesisNote.review_at <= end,
        )
        .order_by(ThesisNote.review_at.asc())
        .all()
    )


def list_overdue(db: Session) -> list[ThesisNote]:
    today = _today_wib()
    return (
        db.query(ThesisNote)
        .filter(
            ThesisNote.status == "pending",
            ThesisNote.review_at != None,  # noqa: E711
            ThesisNote.review_at < today,
        )
        .order_by(ThesisNote.review_at.asc())
        .all()
    )


def mark_reviewed(db: Session, note_id: int, follow_up: str = "") -> Optional[ThesisNote]:
    note = get_note(db, note_id)
    if not note:
        return None
    note.status = "reviewed"
    note.reviewed_at = datetime.now(timezone.utc)
    if follow_up:
        note.follow_up = follow_up
    db.commit()
    db.refresh(note)
    return note


def postpone(db: Session, note_id: int, days: int = 7) -> Optional[ThesisNote]:
    note = get_note(db, note_id)
    if not note or not note.review_at:
        return None
    note.review_at = note.review_at + timedelta(days=days)
    # Reset reminder log for this note so the new date triggers fresh H-7/H-1/H+0.
    db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    db.commit()
    db.refresh(note)
    return note


def mark_invalid(db: Session, note_id: int) -> Optional[ThesisNote]:
    note = get_note(db, note_id)
    if not note:
        return None
    note.status = "invalid"
    # Clear reminder log so a future status-flip back to pending re-arms reminders.
    db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    db.commit()
    db.refresh(note)
    return note


def reset_reminders_for(db: Session, note_id: int) -> None:
    """Wipe reminder log for a note. Use when status/review_at changes re-arm cron."""
    db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    db.commit()


def delete_note(db: Session, note_id: int) -> bool:
    note = get_note(db, note_id)
    if not note:
        return False
    db.query(ThesisReminderLog).filter(ThesisReminderLog.note_id == note_id).delete()
    db.delete(note)
    db.commit()
    return True


def find_duplicates(db: Session, ticker: str, body: str, days: int = 7,
                    threshold: float = 0.7) -> list[ThesisNote]:
    """Cheap fuzzy similarity over recent notes for the same ticker."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates = (
        db.query(ThesisNote)
        .filter(
            ThesisNote.ticker == ticker.upper(),
            ThesisNote.created_at >= cutoff,
        )
        .all()
    )
    matches = []
    for c in candidates:
        ratio = SequenceMatcher(None, body.lower(), (c.body or "").lower()).ratio()
        if ratio >= threshold:
            matches.append(c)
    return matches


def reminders_already_sent(db: Session, note_id: int) -> set[str]:
    rows = db.query(ThesisReminderLog.kind).filter(
        ThesisReminderLog.note_id == note_id
    ).all()
    return {r[0] for r in rows}


def log_reminder_sent(db: Session, note_id: int, kind: str) -> None:
    """Idempotent — relies on unique (note_id, kind) constraint.

    Only swallows IntegrityError (duplicate). Other exceptions propagate so
    real failures (disk full, schema drift) aren't masked.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(ThesisReminderLog(note_id=note_id, kind=kind))
        db.commit()
    except IntegrityError:
        db.rollback()


def needs_reminders_today(db: Session) -> list[tuple[ThesisNote, str]]:
    """Returns (note, kind) pairs that need reminding today.

    kind ∈ {'H-7','H-1','H+0'}. Skips kinds already sent. H-7 and H-1 are
    suppressed if note has been reviewed/postponed (status != pending).
    H+0 always fires while status == pending.
    """
    today = _today_wib()
    pending = db.query(ThesisNote).filter(
        ThesisNote.status == "pending",
        ThesisNote.review_at != None,  # noqa: E711
    ).all()

    pairs: list[tuple[ThesisNote, str]] = []
    for n in pending:
        if not n.review_at:
            continue
        delta = (n.review_at - today).days
        kind = None
        if delta == 7:
            kind = "H-7"
        elif delta == 1:
            kind = "H-1"
        elif delta <= 0:  # today or overdue — fire H+0 once
            kind = "H+0"
        if not kind:
            continue
        sent = reminders_already_sent(db, n.id)
        if kind in sent:
            continue
        pairs.append((n, kind))
    return pairs
