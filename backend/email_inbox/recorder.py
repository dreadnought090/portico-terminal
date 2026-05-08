"""Apply confirmed email transactions to PortfolioItem."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import EmailTransaction, PortfolioItem

logger = logging.getLogger("email_inbox.recorder")


def _find_item(db: Session, ticker: str, broker: str) -> PortfolioItem | None:
    """Find existing PortfolioItem matching ticker+broker (case-insensitive broker match)."""
    rows = db.query(PortfolioItem).filter(PortfolioItem.ticker == ticker).all()
    if not broker:
        return rows[0] if rows else None
    broker_lower = broker.lower()
    for r in rows:
        if (r.broker or "").lower() == broker_lower:
            return r
    return None  # exists but different broker → caller decides


def apply_transaction(tx_id: int, chat_id: int | None = None) -> dict:
    """Apply a pending transaction to portfolio.

    Race-safe: atomic UPDATE pending→processing returns rowcount; only proceed
    if exactly 1 row updated (prevents double-tap double-apply).

    Returns: {ok: bool, message: str, item_id: int|None}
    """
    db = SessionLocal()
    try:
        # Atomic claim — only one caller wins the pending→processing transition
        from sqlalchemy import update
        result = db.execute(
            update(EmailTransaction)
            .where(EmailTransaction.id == tx_id)
            .where(EmailTransaction.status == "pending")
            .values(status="processing")
        )
        db.commit()
        if result.rowcount == 0:
            tx = db.query(EmailTransaction).filter(EmailTransaction.id == tx_id).first()
            if not tx:
                return {"ok": False, "message": "Transaction not found"}
            return {"ok": False, "message": f"Transaction already {tx.status}"}

        tx: EmailTransaction = db.query(EmailTransaction).filter(EmailTransaction.id == tx_id).first()
        if not tx:
            return {"ok": False, "message": "Transaction disappeared mid-claim"}

        ticker = (tx.extracted_ticker or "").upper()
        action = (tx.extracted_action or "").lower()
        shares = int(tx.extracted_shares or (tx.extracted_lot or 0) * 100)
        price = float(tx.extracted_price or 0)
        broker = (tx.extracted_broker or "").strip()

        if not ticker or action not in ("buy", "sell") or shares <= 0 or price <= 0:
            tx.status = "failed"
            tx.error_message = "incomplete extracted data"
            db.commit()
            return {"ok": False, "message": "Data tidak lengkap untuk apply"}

        item = _find_item(db, ticker, broker)

        if action == "buy":
            if item is None:
                # New position
                item = PortfolioItem(
                    ticker=ticker,
                    company_name="",
                    security_type="Saham",
                    sub_sector="Other",
                    lot=shares // 100,
                    shares=shares,
                    avg_price=price,
                    total_cost=shares * price,
                    current_price=price,
                    market_value=shares * price,
                    unrealized_pnl=0,
                    unrealized_pnl_pct=0,
                    broker=broker,
                    last_updated=datetime.now(timezone.utc),
                )
                db.add(item)
                db.flush()  # populate id
            else:
                # Weighted average cost
                old_shares = item.shares or 0
                old_cost = item.total_cost or 0
                new_shares = old_shares + shares
                new_cost = old_cost + (shares * price)
                item.shares = new_shares
                item.lot = new_shares // 100
                item.total_cost = new_cost
                item.avg_price = (new_cost / new_shares) if new_shares else price
                item.current_price = price  # latest
                item.market_value = new_shares * price
                item.unrealized_pnl = item.market_value - new_cost
                item.unrealized_pnl_pct = (item.unrealized_pnl / new_cost * 100) if new_cost else 0
                item.last_updated = datetime.now(timezone.utc)

        else:  # sell
            if item is None or (item.shares or 0) < shares:
                tx.status = "failed"
                tx.error_message = (
                    f"Sell {shares} shares but holding insufficient ({item.shares if item else 0})"
                )
                db.commit()
                return {"ok": False, "message": tx.error_message}
            old_shares = item.shares
            old_cost = item.total_cost or 0
            avg = (old_cost / old_shares) if old_shares else 0
            realized_pnl = (price - avg) * shares  # for record-keeping
            new_shares = old_shares - shares
            new_cost = old_cost - (shares * avg)
            if new_shares == 0:
                # Position closed — delete row to prevent zombie holdings
                deleted_item_id = item.id
                db.delete(item)
                # Mark tx confirmed + record realized P&L in error_message audit
                tx.status = "confirmed"
                tx.confirmed_at = datetime.now(timezone.utc)
                tx.portfolio_item_id = deleted_item_id
                tx.error_message = f"realized_pnl={realized_pnl:.0f}; position closed"
                db.commit()
                return {
                    "ok": True,
                    "message": f"Sold all {shares} {ticker} @ {price} → position closed (realized P&L Rp {realized_pnl:,.0f})",
                    "item_id": deleted_item_id,
                }
            item.shares = new_shares
            item.lot = new_shares // 100
            item.total_cost = new_cost
            item.current_price = price
            item.market_value = new_shares * price
            item.unrealized_pnl = item.market_value - new_cost
            item.unrealized_pnl_pct = (item.unrealized_pnl / new_cost * 100) if new_cost else 0
            item.last_updated = datetime.now(timezone.utc)

        # Mark tx confirmed + link
        tx.status = "confirmed"
        tx.confirmed_at = datetime.now(timezone.utc)
        tx.portfolio_item_id = item.id
        db.commit()
        return {
            "ok": True,
            "message": f"Applied {action} {shares} {ticker} @ {price} → item #{item.id}",
            "item_id": item.id,
        }
    except Exception as e:
        logger.exception("apply_transaction failed")
        db.rollback()
        return {"ok": False, "message": f"Error: {e}"}
    finally:
        db.close()


def reject_transaction(tx_id: int) -> dict:
    db = SessionLocal()
    try:
        tx: EmailTransaction = db.query(EmailTransaction).filter(EmailTransaction.id == tx_id).first()
        if not tx:
            return {"ok": False, "message": "Transaction not found"}
        if tx.status != "pending":
            return {"ok": False, "message": f"Transaction already {tx.status}"}
        tx.status = "rejected"
        tx.rejected_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "message": "Transaction rejected"}
    finally:
        db.close()
