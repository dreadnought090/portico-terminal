"""Email inbox config — multi-account, env-driven.

Each account: EMAIL_ACCOUNT_<N>_USER, _PASSWORD, _HOST, _PORT, _BROKERS
N starts at 1, contiguous (stops at first missing N).

Cron window: EMAIL_POLL_HOUR_START/END (WIB) — outside window, scan_new_emails no-ops.
"""
import os
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def _account(n: int) -> dict | None:
    user = os.getenv(f"EMAIL_ACCOUNT_{n}_USER", "").strip()
    pwd = os.getenv(f"EMAIL_ACCOUNT_{n}_PASSWORD", "").strip()
    if not user or not pwd:
        return None
    brokers_raw = os.getenv(f"EMAIL_ACCOUNT_{n}_BROKERS", "").strip()
    brokers = [s.strip().lower() for s in brokers_raw.split(",") if s.strip()]
    if not brokers:
        return None
    try:
        port = int(os.getenv(f"EMAIL_ACCOUNT_{n}_PORT", "993"))
    except ValueError:
        port = 993
    return {
        "user": user,
        "password": pwd,
        "host": os.getenv(f"EMAIL_ACCOUNT_{n}_HOST", "imap.gmail.com").strip(),
        "port": port,
        "folder": os.getenv(f"EMAIL_ACCOUNT_{n}_FOLDER", "INBOX").strip(),
        "brokers": brokers,
    }


def accounts() -> list[dict]:
    """Return all configured accounts. Stops at first missing N."""
    out = []
    n = 1
    while True:
        acc = _account(n)
        if acc is None:
            break
        out.append(acc)
        n += 1
    return out


def poll_interval_min() -> int:
    try:
        return max(5, int(os.getenv("EMAIL_POLL_INTERVAL_MIN", "30")))
    except ValueError:
        return 30


def poll_window() -> tuple[int, int]:
    """(start_hour, end_hour) in WIB. Default 17-22."""
    try:
        start = int(os.getenv("EMAIL_POLL_HOUR_START", "17"))
        end = int(os.getenv("EMAIL_POLL_HOUR_END", "22"))
    except ValueError:
        start, end = 17, 22
    return start, end


def is_in_window(now: datetime | None = None) -> bool:
    start, end = poll_window()
    h = (now or datetime.now(WIB)).astimezone(WIB).hour
    return start <= h <= end


def is_configured() -> bool:
    return len(accounts()) > 0


def dry_run() -> bool:
    return os.getenv("EMAIL_INBOX_DRY_RUN", "0") in ("1", "true", "yes")
