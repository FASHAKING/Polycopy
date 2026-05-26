from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo

HELP_TEXT = (
    "*Polycopy* — copy-trade Polymarket from Telegram.\n\n"
    "*Getting started*\n"
    "  /link — connect your Polymarket account (one time)\n"
    "  /status — check your connection and balance\n"
    "  /unlink — remove your stored credentials\n\n"
    "*Coming next*\n"
    "  /follow `<username|wallet>` — copy a trader\n"
    "  /unfollow, /list — manage who you copy\n"
    "  /auto — auto-pick profitable, active traders\n\n"
    "Non-custodial: your funds stay in your own Polymarket account."
)


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    async with db_session() as session:
        await repo.get_or_create_user(
            session, telegram_id=tg.id, username=tg.username
        )
    await update.message.reply_text(
        f"Hi {tg.first_name or 'there'} \U0001f44b\n\n"
        "I copy trades from Polymarket traders into your own account.\n\n"
        "Start with /link to connect your Polymarket account, then /help to see "
        "everything I can do.",
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
