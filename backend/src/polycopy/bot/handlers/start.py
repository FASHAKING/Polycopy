from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo

HELP_TEXT = (
    "*Polycopy* — copy-trade Polymarket from Telegram.\n\n"
    "*Getting started*\n"
    "  /email `you@example.com` — set your email\n"
    "  /wallet — create a new wallet or link an existing one\n"
    "  /approve — enable trading on a created wallet (one time, uses your POL)\n"
    "  /link — link an existing Polymarket account\n"
    "  /status — check your connection and balance\n"
    "  /unlink — remove your stored credentials\n\n"
    "*Copying traders*\n"
    "  /follow `<username|wallet>` — copy a trader\n"
    "  /unfollow `<username|wallet>` — stop copying\n"
    "  /list — who you're copying\n\n"
    "*Auto-copy*\n"
    "  /auto on — auto-follow profitable, active traders in a 60–80% win-rate band\n"
    "  /auto off — stop auto-following\n"
    "  /auto status — current setting\n\n"
    "*Risk controls*\n"
    "  /risk — view your caps\n"
    "  /risk maxtrade 25 — max $ per copied trade\n"
    "  /risk daycap 100 — max $ copied per day\n\n"
    "*Alerts*\n"
    "  /notify on|off — trade alerts when a trader you follow trades\n\n"
    "*Paper trading*\n"
    "  /paper on|off — simulate copies without placing real orders\n"
    "  /paper balance 1000 — fund an imaginary account (resets it)\n"
    "  /paper — view your paper portfolio\n\n"
    "*Portfolio*\n"
    "  /portfolio — your real and paper portfolios\n\n"
    "*Dashboard*\n"
    "  /login — get a private link to sign in to the web dashboard\n\n"
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
        "I copy trades from top Polymarket traders into your wallet.\n\n"
        "To get started:\n"
        "1. /email `you@example.com` — sign up with your email\n"
        "2. /wallet — create a new custodial wallet or link your own\n"
        "3. /follow a trader, or /auto to auto-pick winners\n\n"
        "See /help for everything I can do.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
