"""Ginger bot lifecycle — supervised polling pattern (auto-recover network drops)."""
from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from backend.ginger import config, handlers

logger = logging.getLogger("ginger.bot")

_app: Application | None = None
_bg_task: asyncio.Task | None = None


COMMANDS = [
    BotCommand("start", "Welcome + cara pakai"),
    BotCommand("help", "Info bantuan"),
    BotCommand("reset", "Reset memori percakapan"),
]


def _build_app() -> Application:
    app = ApplicationBuilder().token(config.bot_token()).build()
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("reset", handlers.cmd_reset))
    # Email-tx confirm/reject buttons (etx_ prefix routed only here)
    app.add_handler(CallbackQueryHandler(handlers.on_email_tx_callback, pattern=r"^etx_(ok|no):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_message))
    return app


async def _setup_command_menu(app: Application) -> None:
    admin = config.admin_chat_id()
    try:
        await app.bot.set_my_commands(COMMANDS, scope=BotCommandScopeChat(chat_id=admin))
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)


async def _run_polling(app: Application) -> None:
    await app.initialize()
    await _setup_command_menu(app)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await app.updater.stop()
        except Exception:
            pass
        await app.stop()
        await app.shutdown()


async def _supervised_polling() -> None:
    global _app
    backoff = 5
    while True:
        try:
            _app = _build_app()
            await _run_polling(_app)
            return
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Ginger polling crashed — restarting in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)


def start_bot() -> None:
    """Idempotent — no-op if not configured."""
    global _bg_task
    if _bg_task is not None and not _bg_task.done():
        return
    if not config.is_configured():
        logger.warning("Ginger not configured (GINGER_BOT_TOKEN missing) — skipping bot start")
        return
    _bg_task = asyncio.create_task(_supervised_polling(), name="ginger-bot")
    logger.info("Ginger bot polling started (supervised)")


async def stop_bot() -> None:
    global _bg_task, _app
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()
        try:
            await _bg_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("error stopping ginger bot")
    _bg_task = None
    _app = None
