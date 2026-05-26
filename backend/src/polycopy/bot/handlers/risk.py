from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo

_FIELDS = {
    "size": ("default_size_pct", float, "copy size multiplier (1.0 = mirror 1:1)"),
    "slippage": ("max_slippage_bps", int, "max slippage in bps (200 = 2%)"),
    "maxtrade": ("max_notional_per_trade_usd", float, "max $ per copied trade (0 = off)"),
    "daycap": ("daily_spend_cap_usd", float, "max $ copied per day (0 = off)"),
}


def _summary(user) -> str:
    return (
        "*Your risk settings*\n"
        f"• `size` — {user.default_size_pct} (copy multiplier)\n"
        f"• `slippage` — {user.max_slippage_bps} bps\n"
        f"• `maxtrade` — ${user.max_notional_per_trade_usd:g} per trade"
        f"{' (off)' if user.max_notional_per_trade_usd == 0 else ''}\n"
        f"• `daycap` — ${user.daily_spend_cap_usd:g} per day"
        f"{' (off)' if user.daily_spend_cap_usd == 0 else ''}\n\n"
        "Set with: `/risk <name> <value>`  e.g. `/risk maxtrade 25`"
    )


async def cmd_risk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None:
            await update.message.reply_text("Use /start first.")
            return

        if not ctx.args:
            await update.message.reply_text(_summary(user), parse_mode="Markdown")
            return

        if len(ctx.args) != 2:
            await update.message.reply_text(
                "Usage: `/risk <name> <value>`\nNames: "
                + ", ".join(f"`{k}`" for k in _FIELDS),
                parse_mode="Markdown",
            )
            return

        name, raw = ctx.args[0].lower(), ctx.args[1]
        if name not in _FIELDS:
            await update.message.reply_text(
                "Unknown setting. Options: " + ", ".join(_FIELDS), parse_mode="Markdown"
            )
            return

        attr, caster, _desc = _FIELDS[name]
        try:
            value = caster(raw)
        except ValueError:
            await update.message.reply_text(f"“{raw}” isn't a valid value for {name}.")
            return
        if value < 0:
            await update.message.reply_text("Value can't be negative.")
            return

        setattr(user, attr, value)
        await update.message.reply_text(
            f"✅ Updated *{name}* to `{value}`.", parse_mode="Markdown"
        )
