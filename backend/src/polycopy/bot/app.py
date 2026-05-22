from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from polycopy.core.config import get_settings
from polycopy.core.db import init_db
from polycopy.core.logging import configure_logging, get_logger

log = get_logger(__name__)


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name if user else 'there'} — Polycopy bot is alive.\n\n"
        "Phase 1 scaffold. Commands like /follow, /auto, /list, /balance are coming "
        "in later phases. /help for the current list."
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available so far:\n"
        "  /start — say hi\n"
        "  /help  — this message\n"
        "\n"
        "Coming next: /link (Polymarket API), /follow, /unfollow, /list, /auto, /balance"
    )


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    return app


async def _on_startup(app: Application) -> None:
    await init_db()
    log.info("bot.startup")


def run() -> None:
    configure_logging()
    app = build_application()
    app.post_init = _on_startup
    app.run_polling(allowed_updates=Update.ALL_TYPES)
