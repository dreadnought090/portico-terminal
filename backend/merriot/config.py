"""Merriot config — env-driven, no hardcoded secrets."""
import os
from datetime import timezone, timedelta

WIB = timezone(timedelta(hours=7))


def bot_token() -> str:
    return os.getenv("MERRIOT_BOT_TOKEN", "").strip()


def admin_chat_id() -> int:
    """Single-user bot. Defaults to BRIEFING_CHAT_ID if MERRIOT_ADMIN_CHAT_ID unset."""
    val = os.getenv("MERRIOT_ADMIN_CHAT_ID") or os.getenv("BRIEFING_CHAT_ID", "0")
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def reminder_hour() -> int:
    return int(os.getenv("MERRIOT_REMINDER_HOUR", "7"))


def reminder_minute() -> int:
    return int(os.getenv("MERRIOT_REMINDER_MINUTE", "30"))


def llm_model() -> str:
    return os.getenv("MERRIOT_LLM_MODEL", "claude-haiku-4-5")


def dry_run() -> bool:
    return os.getenv("MERRIOT_DRY_RUN", "0") in ("1", "true", "yes")


def is_configured() -> bool:
    """Bot will start only if both token and admin chat_id are set."""
    return bool(bot_token()) and admin_chat_id() > 0
