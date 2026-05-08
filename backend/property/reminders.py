"""Property reminders — daily checks for due payments and expiring leases.

Follows the Portico convention used by `backend.merriot.reminders`,
`backend.alerts.cron`, etc.: expose `register_cron(scheduler)` and let
`app.py` own the global APScheduler instance.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import date

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.property.config import TELEGRAM_API, get_authorized_users, PROPERTIES
from backend.property.sheets import SheetsClient

logger = logging.getLogger("property.reminders")


# Module-level singletons set by `register_cron` so the bot's runtime
# `SheetsClient` and httpx client are reused for sending.
_sheets: SheetsClient | None = None
_http: httpx.AsyncClient | None = None


def configure(sheets_client: SheetsClient, http_client: httpx.AsyncClient) -> None:
    """Wire the runtime sheets/http clients before the scheduler fires."""
    global _sheets, _http
    _sheets = sheets_client
    _http = http_client


def register_cron(scheduler: AsyncIOScheduler) -> None:
    """Add property reminder jobs to Portico's global scheduler."""
    scheduler.add_job(
        _check_due_reminders,
        CronTrigger(hour=8, minute=0, timezone="Asia/Jakarta"),
        id="property_due_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        _check_expiring_leases,
        CronTrigger(hour=8, minute=5, timezone="Asia/Jakarta"),
        id="property_lease_expiry",
        replace_existing=True,
    )
    logger.info("Property reminder cron registered (08:00 + 08:05 WIB)")


async def _check_due_reminders() -> None:
    if _sheets is None or _http is None:
        logger.warning("property reminders not configured; skipping due check")
        return

    today = date.today()
    try:
        reminders = await asyncio.to_thread(_sheets.get_active_reminders)
    except Exception as e:
        logger.error(f"failed to read reminders: {e}")
        return

    for r in reminders:
        try:
            due_day = int(r.get("Due Day"))
        except (ValueError, TypeError):
            continue
        if due_day != today.day:
            continue
        msg = _format_reminder(
            r.get("Property", ""), r.get("Type", ""), r.get("Description", ""),
            r.get("Amount", 0), r.get("Notes", ""),
        )
        await _send_to_all(msg)


async def _check_expiring_leases() -> None:
    if _sheets is None or _http is None:
        return

    try:
        expiring = await asyncio.to_thread(_sheets.get_expiring_leases, 30)
    except Exception as e:
        logger.error(f"failed to check expiring leases: {e}")
        return

    alert_days = {30, 14, 7, 3, 1}
    for tenant in expiring:
        days_left = tenant.get("_days_left", 999)
        if days_left not in alert_days:
            continue

        prop_key = tenant.get("Property", "")
        prop_name = PROPERTIES.get(prop_key, {}).get("name", prop_key)
        name = tenant.get("Name", "?")
        end = tenant.get("Contract End", "?")

        if days_left == 0:
            urgency = "🔴 <b>HARI INI</b>"
        elif days_left == 1:
            urgency = "🟠 <b>BESOK</b>"
        elif days_left <= 3:
            urgency = f"🟠 <b>{days_left} hari lagi</b>"
        elif days_left <= 7:
            urgency = f"🟡 {days_left} hari lagi"
        else:
            urgency = f"🟢 {days_left} hari lagi"

        msg = (
            f"📆 <b>Lease Expiring</b>\n\n"
            f"Property: {prop_name}\n"
            f"Tenant: {name}\n"
            f"End Date: {end}\n"
            f"Status: {urgency}\n"
        )
        await _send_to_all(msg)


def _format_reminder(prop: str, rtype: str, desc: str, amount, notes: str) -> str:
    try:
        amount_int = int(amount) if amount else 0
    except (ValueError, TypeError):
        amount_int = 0
    icon = {"sewa": "🏠", "bill": "💡", "pbb": "🏛️", "insurance": "🛡️"}.get(rtype, "📌")

    msg = f"{icon} Reminder: {desc}\nProperty: {prop}\n"
    if amount_int > 0:
        msg += f"Amount: Rp {amount_int:,}\n"
    if notes:
        msg += f"Notes: {notes}\n"
    return msg


async def _send_to_all(message: str) -> None:
    for chat_id in get_authorized_users():
        try:
            await _http.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            )
        except Exception as e:
            logger.error(f"failed to send to {chat_id}: {e}")
