from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.workers.scout import ScoutConfig

_DEFAULT = ScoutConfig()


async def cmd_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/auto on|off|status — toggle auto-following scouted traders."""
    arg = (ctx.args[0].lower() if ctx.args else "status")

    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None:
            await update.message.reply_text("Use /start first.")
            return

        if arg in ("on", "enable"):
            if not await repo.has_credentials(session, user):
                await update.message.reply_text("Connect your account first with /link.")
                return
            user.auto_scout_enabled = True
            await update.message.reply_text(
                "🤖 *Auto-copy ON*.\n"
                f"I'll automatically follow up to {_DEFAULT.max_auto_follows} traders that are:\n"
                f"• profitable and active in the last {_DEFAULT.active_within_days} days\n"
                f"• win rate {_DEFAULT.min_win_rate:.0%}–{_DEFAULT.max_win_rate:.0%} "
                f"over ≥{_DEFAULT.min_settled} resolved markets\n\n"
                "See picks with /list. Turn off with /auto off.",
                parse_mode="Markdown",
            )
        elif arg in ("off", "disable"):
            user.auto_scout_enabled = False
            await update.message.reply_text(
                "Auto-copy OFF. Existing auto-follows stay active — remove them with "
                "/unfollow if you want."
            )
        else:
            state = "ON" if user.auto_scout_enabled else "OFF"
            await update.message.reply_text(
                f"Auto-copy is *{state}*.\n"
                f"Target: win rate {_DEFAULT.min_win_rate:.0%}–{_DEFAULT.max_win_rate:.0%}, "
                f"active in last {_DEFAULT.active_within_days} days.\n"
                "Use /auto on or /auto off.",
                parse_mode="Markdown",
            )
