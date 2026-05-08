"""IDX ticker registry refresher — daily upsert from idx_native.fetch_stock_summary.

Schedule: 17:00 WIB (after market close 16:00, gives IDX 1h to publish full summary).
Bootstrap: runs once on Portico startup if registry empty.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.database import SessionLocal
from backend.idx_native import fetch_stock_summary
from backend.models import IdxTicker

logger = logging.getLogger("idx_registry.refresher")

WIB = timezone(timedelta(hours=7))

# Tickers not seen in feed for N days → marked inactive (delisted/suspended).
INACTIVE_THRESHOLD_DAYS = 30


async def refresh_idx_tickers() -> dict:
    """Pull /primary/TradingSummary/GetStockSummary, upsert IdxTicker rows.

    Returns: {fetched, inserted, updated, marked_inactive}
    """
    try:
        rows = await fetch_stock_summary()
    except Exception:
        logger.exception("fetch_stock_summary failed")
        return {"status": "fetch_failed", "fetched": 0}

    if not rows:
        logger.warning("fetch_stock_summary returned empty — skipping upsert")
        return {"status": "empty_feed", "fetched": 0}

    now = datetime.now(timezone.utc)
    seen_codes: set[str] = set()
    inserted = 0
    updated = 0

    db = SessionLocal()
    try:
        # Bulk-load existing rows once to avoid N queries
        existing = {r.code: r for r in db.query(IdxTicker).all()}

        for item in rows:
            code = (item.get("code") or "").strip().upper()
            if not code or len(code) < 3 or len(code) > 6:
                continue
            seen_codes.add(code)

            name = (item.get("name") or "").strip()[:200]
            close = float(item.get("close") or 0)

            row = existing.get(code)
            if row is None:
                row = IdxTicker(
                    code=code,
                    name=name,
                    last_close=close,
                    is_active=1,
                    last_seen_at=now,
                )
                db.add(row)
                inserted += 1
            else:
                row.name = name or row.name
                row.last_close = close or row.last_close
                row.is_active = 1
                row.last_seen_at = now
                updated += 1

        # Mark stale tickers inactive (not seen in 30d AND missing from current feed)
        cutoff = now - timedelta(days=INACTIVE_THRESHOLD_DAYS)
        marked_inactive = 0
        for code, row in existing.items():
            if code in seen_codes:
                continue
            if row.is_active and row.last_seen_at and row.last_seen_at < cutoff:
                row.is_active = 0
                marked_inactive += 1

        db.commit()
    except Exception:
        logger.exception("idx_registry upsert failed")
        db.rollback()
        return {"status": "db_error", "fetched": len(rows)}
    finally:
        db.close()

    summary = {
        "status": "ok",
        "fetched": len(rows),
        "inserted": inserted,
        "updated": updated,
        "marked_inactive": marked_inactive,
    }
    logger.info("idx_registry refresh done: %s", summary)
    return summary


async def bootstrap_if_empty() -> None:
    """Called on Portico startup. Refresh if registry table empty."""
    db = SessionLocal()
    try:
        n = db.query(IdxTicker).count()
    finally:
        db.close()

    if n == 0:
        logger.info("idx_registry empty — bootstrapping initial refresh")
        await refresh_idx_tickers()
    else:
        logger.info("idx_registry has %d tickers — skip bootstrap", n)


def register_cron(scheduler) -> None:
    """Daily refresh at 17:00 WIB."""
    scheduler.add_job(
        refresh_idx_tickers, "cron",
        hour=17, minute=0,
        timezone=WIB,
        id="idx_registry_refresh",
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    logger.info("idx_registry cron registered: daily 17:00 WIB")
