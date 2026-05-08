"""Telegram channel membership operations — invite link + ban/unban (kick)."""
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot

from backend.subscription.config import subscription_channel_id

logger = logging.getLogger("mybloomberg.subscription")

INVITE_TTL_HOURS = 1


async def create_single_use_invite(bot: Bot, label: str) -> str:
    """Create a single-use, time-limited invite link to the subscription channel."""
    link = await bot.create_chat_invite_link(
        chat_id=subscription_channel_id(),
        member_limit=1,
        expire_date=datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS),
        name=label[:32],
    )
    return link.invite_link


async def kick_member(bot: Bot, user_id: int) -> bool:
    """Remove a user from the subscription channel.

    We ban+unban so the user CAN rejoin if they re-subscribe. A plain ban is
    permanent per Telegram semantics.
    """
    chat_id = subscription_channel_id()
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        return True
    except Exception as e:
        logger.warning("kick failed for user %s: %s", user_id, e)
        return False
