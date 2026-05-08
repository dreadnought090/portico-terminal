"""Merriot bot lifecycle — clones subscription/bot.py pattern."""
from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from backend.merriot import config, handlers

logger = logging.getLogger("merriot.bot")

_app: Application | None = None
_bg_task: asyncio.Task | None = None


COMMANDS = [
    BotCommand("start", "Welcome + cara pakai"),
    BotCommand("help", "Info bantuan"),
    BotCommand("tickers", "Semua saham yang punya thesis"),
    BotCommand("all", "Semua notes (filter optional: /all pending)"),
    BotCommand("timeline", "Timeline review chronological"),
    BotCommand("thesis", "List notes per ticker (mis. /thesis BBCA)"),
    BotCommand("due", "Notes due minggu ini"),
    BotCommand("recent", "10 notes terakhir"),
    BotCommand("del", "Hapus note (mis. /del 42)"),
    BotCommand("alert", "Set price alert (mis. /alert BBCA above 12000)"),
    BotCommand("alerts", "List alert armed"),
    BotCommand("delalert", "Cancel alert (mis. /delalert 5)"),
]


def _build_app() -> Application:
    app = ApplicationBuilder().token(config.bot_token()).build()
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("tickers", handlers.cmd_tickers))
    app.add_handler(CommandHandler("all", handlers.cmd_all))
    app.add_handler(CommandHandler("timeline", handlers.cmd_timeline))
    app.add_handler(CommandHandler("thesis", handlers.cmd_thesis))
    app.add_handler(CommandHandler("due", handlers.cmd_due))
    app.add_handler(CommandHandler("recent", handlers.cmd_recent))
    app.add_handler(CommandHandler("del", handlers.cmd_del))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_handler(ChatMemberHandler(handlers.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_message))
    # Alerts feature — registers /alert /alerts /delalert + a* callback prefix
    try:
        from backend.alerts import register_handlers as alerts_register_handlers
        alerts_register_handlers(app)
    except Exception:
        logger.exception("failed to register alerts handlers")
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
        await asyncio.Future()  # park forever
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
    """Watchdog wrapper: if polling task dies (network exhaustion, etc.),
    rebuild app and retry with exponential backoff. Logs every restart.
    """
    global _app
    backoff = 5
    while True:
        try:
            _app = _build_app()
            await _run_polling(_app)
            # _run_polling only returns on cancellation — propagate.
            return
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Merriot polling crashed — restarting in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)  # cap at 5 min


def start_bot() -> None:
    """Idempotent — no-op if already started or unconfigured."""
    global _app, _bg_task
    if _bg_task is not None and not _bg_task.done():
        return
    if not config.is_configured():
        logger.warning("Merriot not configured (MERRIOT_BOT_TOKEN or admin chat_id missing) — skipping bot start")
        return
    _bg_task = asyncio.create_task(_supervised_polling(), name="merriot-bot")
    logger.info("Merriot bot polling started (supervised)")


async def stop_bot() -> None:
    global _bg_task, _app
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()
        try:
            await _bg_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("error stopping merriot bot")
    _bg_task = None
    _app = None


def get_app() -> Application | None:
    return _app
