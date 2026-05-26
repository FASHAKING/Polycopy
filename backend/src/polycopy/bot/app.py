from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from polycopy.bot.handlers.auto import cmd_auto
from polycopy.bot.handlers.follow import (
    cmd_follow,
    cmd_list,
    cmd_unfollow,
    follow_callback,
)
from polycopy.bot.handlers.link import (
    build_link_conversation,
    cmd_status,
    cmd_unlink,
)
from polycopy.bot.handlers.risk import cmd_risk
from polycopy.bot.handlers.start import cmd_help, cmd_start
from polycopy.bot.handlers.wallet import cmd_email, cmd_wallet, wallet_callback
from polycopy.core.config import get_settings
from polycopy.core.db import init_db
from polycopy.core.logging import configure_logging, get_logger

log = get_logger(__name__)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(build_link_conversation())
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("unlink", cmd_unlink))
    app.add_handler(CommandHandler("follow", cmd_follow))
    app.add_handler(CommandHandler("unfollow", cmd_unfollow))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("email", cmd_email))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(CallbackQueryHandler(follow_callback, pattern=r"^follow:"))
    app.add_handler(CallbackQueryHandler(wallet_callback, pattern=r"^wallet:"))
    return app


async def _on_startup(_app: Application) -> None:
    await init_db()
    log.info("bot.startup")


def run() -> None:
    configure_logging()
    app = build_application()
    app.post_init = _on_startup
    app.run_polling(allowed_updates=Update.ALL_TYPES)
