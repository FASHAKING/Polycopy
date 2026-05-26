from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo


async def cmd_notify(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/notify on|off — toggle trade alerts."""
    arg = (ctx.args[0].lower() if ctx.args else "status")
    async with db_session() as session:
        user = await repo.get_or_create_user(
            session, telegram_id=update.effective_user.id, username=update.effective_user.username
        )
        if arg in ("on", "enable"):
            user.notifications_enabled = True
            msg = "🔔 Trade alerts *on*. I'll message you when a trader you follow trades."
        elif arg in ("off", "disable", "mute"):
            user.notifications_enabled = False
            msg = "🔕 Trade alerts *off*. Re-enable with /notify on."
        else:
            state = "on" if user.notifications_enabled else "off"
            msg = f"Trade alerts are *{state}*. Use /notify on or /notify off."
    await update.message.reply_text(msg, parse_mode="Markdown")
