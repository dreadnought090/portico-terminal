"""PriceAlert query layer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import PriceAlert


def create_alert(
    db: Session, *,
    ticker: str,
    direction: str,            # 'above' | 'below'
    threshold: float,
    label: str = "",
    chat_id: int | None = None,
    source: str = "telegram",
) -> PriceAlert:
    a = PriceAlert(
        ticker=ticker.upper(),
        direction=direction.lower(),
        threshold_price=float(threshold),
        label=(label or "").strip()[:200],
        chat_id=chat_id,
        source=source,
        status="armed",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def get_alert(db: Session, alert_id: int) -> Optional[PriceAlert]:
    return db.query(PriceAlert).filter(PriceAlert.id == alert_id).first()


def list_armed(db: Session) -> list[PriceAlert]:
    return (
        db.query(PriceAlert)
        .filter(PriceAlert.status == "armed")
        .order_by(PriceAlert.created_at.desc())
        .all()
    )


def list_armed_tickers(db: Session) -> list[str]:
    """Distinct tickers that have armed alerts. Used to batch fetch prices."""
    rows = (
        db.query(PriceAlert.ticker)
        .filter(PriceAlert.status == "armed")
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def list_for_ticker(db: Session, ticker: str,
                    statuses: list[str] | None = None) -> list[PriceAlert]:
    q = db.query(PriceAlert).filter(PriceAlert.ticker == ticker.upper())
    if statuses:
        q = q.filter(PriceAlert.status.in_(statuses))
    return q.order_by(PriceAlert.created_at.desc()).all()


def list_history(db: Session, limit: int = 50) -> list[PriceAlert]:
    return (
        db.query(PriceAlert)
        .filter(PriceAlert.status.in_(("triggered", "cancelled", "expired")))
        .order_by(PriceAlert.created_at.desc())
        .limit(limit)
        .all()
    )


def list_all(db: Session, limit: int = 100) -> list[PriceAlert]:
    return (
        db.query(PriceAlert)
        .order_by(PriceAlert.created_at.desc())
        .limit(limit)
        .all()
    )


def cancel(db: Session, alert_id: int) -> Optional[PriceAlert]:
    a = get_alert(db, alert_id)
    if not a or a.status != "armed":
        return a
    a.status = "cancelled"
    db.commit()
    db.refresh(a)
    return a


def mark_triggered(db: Session, alert_id: int, hit_price: float) -> Optional[PriceAlert]:
    """Persistent fire: record fire timestamp + price but KEEP status='armed'.

    Alert stays alive until user explicitly Done/Cancel. Cron uses cross-event
    detection (prev_price vs threshold) to avoid spamming on every cycle.
    """
    a = get_alert(db, alert_id)
    if not a:
        return None
    if a.status != "armed":
        return None
    # Repurpose triggered_at as last_fired_at (no schema change needed)
    a.triggered_at = datetime.now(timezone.utc)
    a.triggered_price = float(hit_price)
    if a.threshold_price:
        a.drift_pct = round(((hit_price - a.threshold_price) / a.threshold_price) * 100, 4)
    # status stays 'armed' — persistent mode
    db.commit()
    db.refresh(a)
    return a


def mark_done(db: Session, alert_id: int) -> Optional[PriceAlert]:
    """User explicitly stops the alert via Done button. Sets status='cancelled'."""
    a = get_alert(db, alert_id)
    if not a:
        return None
    if a.status not in ("armed",):
        return a
    a.status = "cancelled"
    db.commit()
    db.refresh(a)
    return a


def touch_check(db: Session, alert_id: int, last_price: float) -> None:
    """Cron observability — record price/timestamp on every check."""
    a = get_alert(db, alert_id)
    if not a:
        return
    a.last_check_price = float(last_price)
    a.last_checked_at = datetime.now(timezone.utc)
    db.commit()


def find_duplicates(
    db: Session, ticker: str, direction: str, threshold: float,
    window_h: int = 24, tolerance: float = 0.005,
) -> list[PriceAlert]:
    """Match same ticker+direction with threshold within ±tolerance, recent armed only."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_h)
    low = threshold * (1 - tolerance)
    high = threshold * (1 + tolerance)
    return (
        db.query(PriceAlert)
        .filter(
            PriceAlert.ticker == ticker.upper(),
            PriceAlert.direction == direction.lower(),
            PriceAlert.status == "armed",
            PriceAlert.threshold_price >= low,
            PriceAlert.threshold_price <= high,
            PriceAlert.created_at >= cutoff,
        )
        .all()
    )


def matches_threshold(direction: str, current_price: float, threshold: float) -> bool:
    """One-shot evaluation: is current price past threshold in the alert direction?"""
    if direction == "above":
        return current_price >= threshold
    if direction == "below":
        return current_price <= threshold
    return False
