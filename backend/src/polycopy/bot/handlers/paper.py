from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.core.config import get_settings


async def cmd_paper(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/paper on|off|status — simulate copies without placing real orders."""
    arg = (ctx.args[0].lower() if ctx.args else "status")
    global_paper = get_settings().paper_trading

    async with db_session() as session:
        user = await repo.get_or_create_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        if arg in ("on", "enable"):
            user.paper_trading = True
            msg = (
                "📝 *Paper trading ON*. I'll simulate every copy — sizing, risk caps, "
                "and alerts — but place *no real orders*. Great for testing. /paper off to go live."
            )
        elif arg in ("off", "disable"):
            user.paper_trading = False
            msg = "🟢 *Paper trading OFF*. Copies will now place real orders on Polymarket."
        else:
            state = "ON" if (user.paper_trading or global_paper) else "OFF"
            forced = " (forced globally by the operator)" if global_paper else ""
            msg = f"Paper trading is *{state}*{forced}. Use /paper on or /paper off."

    await update.message.reply_text(msg, parse_mode="Markdown")
