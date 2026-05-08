"""Alerts config — env-driven."""
import os
from datetime import timezone, timedelta

WIB = timezone(timedelta(hours=7))


def admin_chat_id() -> int:
    """Default chat for notifications. Reuses Merriot/Briefing chat id."""
    val = (
        os.getenv("MERRIOT_ADMIN_CHAT_ID")
        or os.getenv("BRIEFING_CHAT_ID", "0")
    )
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def cron_interval_minutes() -> int:
    """Polling interval during market hours (default 5)."""
    try:
        return max(1, int(os.getenv("ALERTS_INTERVAL_MIN", "5")))
    except ValueError:
        return 5


def dry_run() -> bool:
    return os.getenv("ALERTS_DRY_RUN", "0") in ("1", "true", "yes")
