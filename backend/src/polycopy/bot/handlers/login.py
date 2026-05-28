from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import repo
from polycopy.core.config import get_settings
from polycopy.core.security import make_session_token


async def cmd_login(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    async with db_session() as session:
        await repo.get_or_create_user(session, telegram_id=tg.id, username=tg.username)

    token = make_session_token(tg.id)
    base = get_settings().dashboard_url.rstrip("/")
    url = f"{base}/dashboard#token={token}"

    await update.message.reply_text(
        "Here's your private dashboard link — tap to sign in.\n"
        "Don't share it: it logs in as you and is valid for 30 days.\n\n"
        f"{url}",
        disable_web_page_preview=True,
    )
