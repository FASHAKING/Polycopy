from telegram import Update
from telegram.ext import Application, CommandHandler

from polycopy.bot.handlers.link import (
    build_link_conversation,
    cmd_status,
    cmd_unlink,
)
from polycopy.bot.handlers.start import cmd_help, cmd_start
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
    return app


async def _on_startup(_app: Application) -> None:
    await init_db()
    log.info("bot.startup")


def run() -> None:
    configure_logging()
    app = build_application()
    app.post_init = _on_startup
    app.run_polling(allowed_updates=Update.ALL_TYPES)
