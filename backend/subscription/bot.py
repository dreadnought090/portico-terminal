"""python-telegram-bot Application lifecycle — polling loop started at Portico boot."""
import asyncio
import logging

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from backend.subscription import config, handlers

logger = logging.getLogger("mybloomberg.subscription")

_app: Application | None = None
_bg_task: asyncio.Task | None = None


def _build_app() -> Application:
    app = Application.builder().token(config.bot_token()).build()
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("subscribe", handlers.cmd_subscribe))
    app.add_handler(CommandHandler("renew", handlers.cmd_renew))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("feedback", handlers.cmd_feedback))
    app.add_handler(CommandHandler("brief", handlers.cmd_brief))      # admin: manual run
    app.add_handler(CommandHandler("mode", handlers.cmd_mode))        # admin: get/set cron mode
    app.add_handler(CommandHandler("intraday", handlers.cmd_intraday))  # admin: toggle live alerts
    app.add_handler(CallbackQueryHandler(handlers.on_buy_button, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(handlers.on_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handlers.on_successful_payment))
    return app


PUBLIC_COMMANDS = [
    BotCommand("start", "Mulai + lihat info"),
    BotCommand("subscribe", "Daftar paket berlangganan"),
    BotCommand("status", "Cek masa aktif subscription"),
    BotCommand("renew", "Perpanjang langganan"),
    BotCommand("feedback", "Kirim saran/kritik ke admin"),
    BotCommand("help", "Panduan command"),
]
ADMIN_EXTRA_COMMANDS = [
    BotCommand("brief", "[admin] trigger briefing manual"),
    BotCommand("mode", "[admin] view/set cron mode"),
    BotCommand("intraday", "[admin] toggle live alerts"),
]


async def _setup_command_menus(app: Application) -> None:
    """Register two command lists: public (everyone) and admin (just owner).

    Telegram clients honor the scope and show different autocomplete menus per
    user — keeps admin commands invisible to subscribers (defense in depth on
    top of the existing chat_id check inside each handler).
    """
    await app.bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    admin = config.admin_chat_id()
    if admin:
        await app.bot.set_my_commands(
            PUBLIC_COMMANDS + ADMIN_EXTRA_COMMANDS,
            scope=BotCommandScopeChat(chat_id=admin),
        )
        logger.info("admin command menu set for chat_id=%s", admin)


async def _run_polling(app: Application) -> None:
    """Run until cancelled. Initialize + start + poll forever."""
    await app.initialize()
    await app.start()
    try:
        await _setup_command_menus(app)
    except Exception:
        logger.exception("failed to set scoped command menus (non-fatal)")
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("subscription bot polling started")
    try:
        # Block until cancellation
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("subscription bot cancellation received")
    finally:
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            logger.exception("error during subscription bot shutdown")


async def _supervised_polling() -> None:
    """Watchdog wrapper: if polling task dies (network exhaustion, etc.),
    rebuild app and retry with exponential backoff (5s → 10s → ... → 5min cap)."""
    global _app
    backoff = 5
    while True:
        try:
            _app = _build_app()
            await _run_polling(_app)
            return  # only returns on cancellation
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("subscription bot polling crashed — restarting in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)


def start_bot() -> None:
    """Boot the subscription bot as an asyncio task. Idempotent. Supervised."""
    global _app, _bg_task
    if _bg_task and not _bg_task.done():
        return
    # Validate config once before starting; supervisor handles re-builds on crash.
    try:
        _build_app()
    except RuntimeError as e:
        logger.warning("subscription bot NOT started: %s", e)
        return
    _bg_task = asyncio.create_task(_supervised_polling(), name="subscription-bot")
    logger.info("subscription bot polling started (supervised)")


async def stop_bot() -> None:
    global _app, _bg_task
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()
        try:
            await _bg_task
        except asyncio.CancelledError:
            pass
    _bg_task = None
    _app = None


def get_bot() -> Application | None:
    return _app
