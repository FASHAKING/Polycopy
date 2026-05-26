import asyncio
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.core.logging import get_logger
from polycopy.core.wallet import generate_wallet
from polycopy.polymarket.clob import derive_api_creds
from polycopy.polymarket.data_api import PolymarketDataClient

log = get_logger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def cmd_email(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        async with db_session() as session:
            user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
            current = user.email if user else None
        await update.message.reply_text(
            f"Your email: {current or '(none set)'}\n\nSet it with `/email you@example.com`",
            parse_mode="Markdown",
        )
        return

    email = ctx.args[0].strip().lower()
    if not _EMAIL_RE.match(email):
        await update.message.reply_text("That doesn't look like a valid email. Try again.")
        return

    async with db_session() as session:
        user = await repo.get_or_create_user(
            session, telegram_id=update.effective_user.id, username=update.effective_user.username
        )
        try:
            await repo.set_email(session, user, email)
        except Exception:  # noqa: BLE001 - unique constraint
            await update.message.reply_text("That email is already in use by another account.")
            return
    await update.message.reply_text(f"✅ Email saved: {email}")


async def cmd_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        cred = await repo.get_credential_meta(session, user) if user else None

    if cred is None:
        buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Create a new wallet", callback_data="wallet:create")],
                [
                    InlineKeyboardButton(
                        "🔗 Link my Polymarket account", callback_data="wallet:link"
                    )
                ],
            ]
        )
        await update.message.reply_text(
            "*Set up your trading wallet*\n\n"
            "• *Create* — I generate a fresh Polymarket wallet for you (custodial: I "
            "hold the key securely). You deposit USDC to start.\n"
            "• *Link* — connect a Polymarket account you already have.\n\n"
            "Each Telegram account controls its own wallet.",
            parse_mode="Markdown",
            reply_markup=buttons,
        )
        return

    address = cred.proxy_address
    try:
        async with PolymarketDataClient() as data:
            value = await data.get_portfolio_value(address)
        value_line = f"${value:,.2f}"
    except Exception:  # noqa: BLE001
        value_line = "(unavailable)"

    origin = "bot-created (custodial)" if cred.origin == "created" else "linked"
    deposit = (
        f"\n\nDeposit *USDC.e on Polygon* to:\n`{address}`"
        if cred.origin == "created"
        else ""
    )
    await update.message.reply_text(
        f"*Your wallet* ({origin})\n"
        f"Address: `{address}`\n"
        f"Balance: {value_line}{deposit}",
        parse_mode="Markdown",
    )


async def wallet_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "link":
        await query.edit_message_text(
            "To link an existing account, send /link and follow the prompts."
        )
        return

    # action == "create"
    async with db_session() as session:
        user = await repo.get_or_create_user(
            session, telegram_id=update.effective_user.id, username=update.effective_user.username
        )
        if await repo.has_credentials(session, user):
            await query.edit_message_text("You already have a wallet set up. See /wallet.")
            return

    await query.edit_message_text("Generating your wallet… 🔐")
    wallet = generate_wallet()

    try:
        api_key, api_secret, api_passphrase = await asyncio.to_thread(
            derive_api_creds, wallet.private_key, wallet.address, 0
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("wallet.create_derive_failed", error=str(exc))
        await query.edit_message_text(
            "Couldn't initialize the wallet with Polymarket right now. Please try /wallet again."
        )
        return

    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        await repo.set_credentials(
            session,
            user,
            proxy_address=wallet.address,
            private_key=wallet.private_key,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            signature_type=0,
            origin="created",
        )

    await query.edit_message_text(
        "✅ *Your wallet is ready!*\n\n"
        f"Address:\n`{wallet.address}`\n\n"
        "*To start trading:*\n"
        "1. Deposit *USDC.e on the Polygon network* to the address above.\n"
        "2. Keep a little *POL* in it for one-time trading approvals.\n\n"
        "Then /follow a trader or turn on /auto. Check balance with /wallet.\n\n"
        "_Note: trading approvals for newly-created wallets require live on-chain "
        "verification before relying on them with significant funds._",
        parse_mode="Markdown",
    )
