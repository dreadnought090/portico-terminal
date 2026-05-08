"""Ginger config — env-driven."""
import os


def bot_token() -> str:
    return os.getenv("GINGER_BOT_TOKEN", "").strip()


def admin_chat_id() -> int:
    """Single-user. Defaults to BRIEFING_CHAT_ID."""
    val = (
        os.getenv("GINGER_ADMIN_CHAT_ID")
        or os.getenv("BRIEFING_CHAT_ID", "0")
    )
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def llm_model() -> str:
    return os.getenv("GINGER_LLM_MODEL", "claude-haiku-4-5")


def is_configured() -> bool:
    return bool(bot_token()) and admin_chat_id() > 0


def dry_run() -> bool:
    return os.getenv("GINGER_DRY_RUN", "0") in ("1", "true", "yes")
