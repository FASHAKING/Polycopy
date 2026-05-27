import asyncio
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.core.logging import get_logger
from polycopy.polymarket.clob import derive_api_creds
from polycopy.polymarket.data_api import PolymarketDataClient

log = get_logger(__name__)

ASK_TYPE, ASK_ADDRESS, ASK_KEY = range(3)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_PRIVKEY_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")

# Polymarket signs orders differently depending on how the account was created.
# Email/Google sign-ups are Magic proxy wallets (POLY_PROXY = 1); browser-wallet
# connections (MetaMask, etc.) are Gnosis-Safe proxies (POLY_GNOSIS_SAFE = 2).
_SIG_EMAIL = 1
_SIG_WALLET = 2


async def link_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please /link in a private chat with me, not a group.")
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📧 Email / Google login", callback_data=f"link:sig:{_SIG_EMAIL}")],
            [InlineKeyboardButton("🦊 Browser wallet (MetaMask…)", callback_data=f"link:sig:{_SIG_WALLET}")],
        ]
    )
    await update.message.reply_text(
        "⚠️ *Connect your Polymarket account*\n\n"
        "I am *non-custodial*: your funds never leave your own Polymarket account. "
        "To place copy-trades I need your *signing key*, which I store encrypted.\n\n"
        "*Strong advice:* use a dedicated wallet funded with only the capital you "
        "want to trade. I will delete your key message from this chat the instant I "
        "read it.\n\n"
        "First — *how did you sign up for Polymarket?* This tells me how to sign your "
        "orders correctly.\n\n"
        "Send /cancel any time to abort.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return ASK_TYPE


async def link_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    sig = int(query.data.rsplit(":", 1)[1])
    ctx.user_data["signature_type"] = sig
    label = "email / Google login" if sig == _SIG_EMAIL else "browser wallet"
    await query.edit_message_text(
        f"Account type: *{label}*.\n\n"
        "Now send your *Polymarket address* (the 0x... funder address shown in "
        "your Polymarket profile).",
        parse_mode="Markdown",
    )
    return ASK_ADDRESS


async def link_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    address = (update.message.text or "").strip()
    if not _ADDRESS_RE.match(address):
        await update.message.reply_text(
            "That doesn't look like a 0x address (40 hex chars). Try again, or /cancel."
        )
        return ASK_ADDRESS
    ctx.user_data["proxy_address"] = address
    await update.message.reply_text(
        "Got it. Now send your *private key* (64 hex chars, with or without 0x).\n\n"
        "I'll delete your message immediately after reading it.",
        parse_mode="Markdown",
    )
    return ASK_KEY


async def link_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    private_key = (update.message.text or "").strip()

    # Delete the key from the chat ASAP, regardless of validity.
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001 - best effort; bot may lack delete rights
        log.warning("link.delete_key_message_failed")

    if not _PRIVKEY_RE.match(private_key):
        await ctx.bot.send_message(
            update.effective_chat.id,
            "That doesn't look like a private key (64 hex chars). Send it again, or /cancel.",
        )
        return ASK_KEY

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    proxy_address = ctx.user_data["proxy_address"]
    signature_type = ctx.user_data.get("signature_type", _SIG_WALLET)
    status = await ctx.bot.send_message(update.effective_chat.id, "Verifying credentials…")

    try:
        api_key, api_secret, api_passphrase = await asyncio.to_thread(
            derive_api_creds, private_key, proxy_address, signature_type
        )
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        log.warning("link.derive_failed", error=str(exc))
        await status.edit_text(
            "I couldn't connect to Polymarket with that key + address. "
            "Double-check the address matches the key, then /link again."
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    async with db_session() as session:
        user = await repo.get_or_create_user(
            session, telegram_id=update.effective_user.id, username=update.effective_user.username
        )
        await repo.set_credentials(
            session,
            user,
            proxy_address=proxy_address,
            private_key=private_key,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            signature_type=signature_type,
            origin="linked",
        )

    # Best-effort balance readout.
    balance_line = ""
    try:
        async with PolymarketDataClient() as data:
            value = await data.get_portfolio_value(proxy_address)
        balance_line = f"\nPortfolio value: *${value:,.2f}*"
    except Exception:  # noqa: BLE001
        pass

    ctx.user_data.clear()
    await status.edit_text(
        "✅ Connected! Your credentials are encrypted and stored." + balance_line +
        "\n\nNext: /follow `<username|wallet>` to start copying a trader (coming online soon).",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def link_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("Linking cancelled.")
    return ConversationHandler.END


async def cmd_unlink(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    from sqlalchemy import delete

    from polycopy.core.models import PolymarketCredential

    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None or not await repo.has_credentials(session, user):
            await update.message.reply_text("You don't have any credentials stored.")
            return
        await session.execute(
            delete(PolymarketCredential).where(PolymarketCredential.user_id == user.id)
        )
    await update.message.reply_text("\U0001f5d1️ Your stored credentials have been removed.")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None or not await repo.has_credentials(session, user):
            await update.message.reply_text(
                "Not connected yet. Use /link to connect your Polymarket account."
            )
            return
        bundle = await repo.get_credential_bundle(session, user)
        follows = await repo.list_active_follows(session, user)

    address = bundle.proxy_address
    try:
        async with PolymarketDataClient() as data:
            value = await data.get_portfolio_value(address)
        value_line = f"*${value:,.2f}*"
    except Exception:  # noqa: BLE001
        value_line = "(unavailable)"

    await update.message.reply_text(
        "*Your Polycopy status*\n"
        f"Connected: `{address[:6]}…{address[-4:]}`\n"
        f"Portfolio value: {value_line}\n"
        f"Active follows: *{len(follows)}*",
        parse_mode="Markdown",
    )


def build_link_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("link", link_start)],
        states={
            ASK_TYPE: [CallbackQueryHandler(link_type, pattern=r"^link:sig:")],
            ASK_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_address)
            ],
            ASK_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_key)],
        },
        fallbacks=[CommandHandler("cancel", link_cancel)],
        name="link",
    )
