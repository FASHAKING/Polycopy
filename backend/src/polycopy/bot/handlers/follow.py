import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.polymarket.data_api import PolymarketDataClient

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


async def _require_linked(update: Update) -> bool:
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        linked = user is not None and await repo.has_credentials(session, user)
    if not linked:
        await update.message.reply_text("Connect your account first with /link.")
    return linked


async def cmd_follow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /follow `<username|0x-wallet>`\n"
            "e.g. `/follow swisstony` or `/follow 0xabc…`",
            parse_mode="Markdown",
        )
        return
    if not await _require_linked(update):
        return

    query = ctx.args[0].strip()

    if _ADDRESS_RE.match(query):
        await _follow_wallet(update, wallet=query, display_name=None)
        return

    # Resolve a username -> possibly several wallets.
    async with PolymarketDataClient() as data:
        matches = await data.resolve_username(query, limit=5)

    if not matches:
        await update.message.reply_text(
            f"No Polymarket trader found for “{query}”. "
            "Try the exact username, or paste their 0x wallet."
        )
        return

    if len(matches) == 1:
        m = matches[0]
        await _follow_wallet(update, wallet=m.wallet, display_name=m.name)
        return

    # Disambiguate with inline buttons.
    buttons = [
        [
            InlineKeyboardButton(
                f"{m.name or m.pseudonym or 'unknown'} · {m.wallet[:6]}…{m.wallet[-4:]}",
                callback_data=f"follow:{m.wallet}:{(m.name or '')[:32]}",
            )
        ]
        for m in matches
    ]
    await update.message.reply_text(
        f"Multiple traders match “{query}”. Pick one:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def follow_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, wallet, name = query.data.split(":", 2)
    await _follow_wallet(update, wallet=wallet, display_name=name or None, via_callback=True)


async def _follow_wallet(
    update: Update, *, wallet: str, display_name: str | None, via_callback: bool = False
) -> None:
    wallet = wallet.lower()
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        trader = await repo.get_or_create_trader(session, wallet=wallet, display_name=display_name)
        await repo.add_follow(session, user, trader, source="manual")

    label = display_name or f"{wallet[:6]}…{wallet[-4:]}"
    text = (
        f"✅ Now copying *{label}*.\n"
        "New trades they make will be mirrored into your account. "
        "Manage with /list and /unfollow."
    )
    if via_callback:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None:
            await update.message.reply_text("Use /start first.")
            return
        follows = await repo.list_active_follows(session, user)

    if not follows:
        await update.message.reply_text(
            "You're not copying anyone yet. Use /follow `<username|wallet>`.",
            parse_mode="Markdown",
        )
        return

    lines = ["*Traders you're copying:*"]
    for follow, trader in follows:
        label = trader.display_name or f"{trader.wallet[:6]}…{trader.wallet[-4:]}"
        src = "auto" if follow.source == "auto" else "manual"
        lines.append(f"• {label}  _({src})_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_unfollow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /unfollow `<username|0x-wallet>`", parse_mode="Markdown"
        )
        return

    query = ctx.args[0].strip().lower()
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None:
            await update.message.reply_text("Use /start first.")
            return
        follows = await repo.list_active_follows(session, user)
        target = None
        for _follow, trader in follows:
            if trader.wallet == query or (trader.display_name or "").lower() == query:
                target = trader
                break
        if target is None:
            await update.message.reply_text("You're not copying that trader. See /list.")
            return
        await repo.deactivate_follow(session, user, target)

    label = target.display_name or f"{target.wallet[:6]}…{target.wallet[-4:]}"
    await update.message.reply_text(f"Stopped copying *{label}*.", parse_mode="Markdown")
