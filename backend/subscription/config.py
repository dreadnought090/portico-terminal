"""Subscription tiers + runtime config."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    stars: int          # price in Telegram Stars (XTR currency)
    duration_days: int  # how long subscription is active after payment
    blurb: str          # short description shown at /subscribe


# Telegram Stars pricing. 1 Star ≈ $0.013 USD ≈ Rp 210.
# Rp 49.000/month target → ~235 Stars. Round to 250 for friendlier UX.
# Annual at 2.500 = equivalent to 10 months (save 2 months).
PLANS: list[Plan] = [
    Plan(
        key="monthly",
        label="Monthly",
        stars=150,
        duration_days=30,
        blurb="Daily IDX briefing selama 30 hari",
    ),
    Plan(
        key="annual",
        label="Annual",
        stars=1500,
        duration_days=365,
        blurb="1 tahun akses — save 2 bulan (equivalent ~125 Stars/mo)",
    ),
]

PLANS_BY_KEY = {p.key: p for p in PLANS}


# Channel the subscriber joins after successful payment. Same env as the
# briefing sender so both share one private channel.
def subscription_channel_id() -> int:
    raw = os.environ.get("BRIEFING_CHANNEL_ID", "").strip()
    if not raw:
        raise RuntimeError("BRIEFING_CHANNEL_ID not set in env")
    return int(raw)


def bot_token() -> str:
    token = os.environ.get("SUBSCRIPTION_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SUBSCRIPTION_BOT_TOKEN not set in env")
    return token


# Admin chat — receives feedback digest + ops alerts.
def admin_chat_id() -> int | None:
    raw = os.environ.get("BRIEFING_CHAT_ID", "").strip()
    return int(raw) if raw else None


# Grace period after expiry before user is kicked from channel. Prevents
# kicking someone who's 1 hour late to renew.
GRACE_HOURS = 24

# Reminder DM schedule (days before expiry).
REMINDER_DAYS = [7, 3, 1]
