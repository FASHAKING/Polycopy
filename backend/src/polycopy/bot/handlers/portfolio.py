from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import portfolio as portfolio_svc
from polycopy.core import repo


async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/portfolio — show your real and paper portfolios."""
    async with db_session() as session:
        user = await repo.get_user_by_telegram_id(session, update.effective_user.id)
        if user is None:
            await update.message.reply_text("Use /start first.")
            return
        real = await portfolio_svc.real_portfolio(session, user)
        paper = await portfolio_svc.paper_portfolio(session, user)

    blocks: list[str] = []
    if real.wallet_address:
        sign = "+" if real.realized_pnl >= 0 else ""
        blocks.append(
            "💼 *Real portfolio*\n"
            f"Value: *${real.portfolio_value:,.2f}*\n"
            f"Unrealized: ${real.unrealized_pnl:,.2f} · "
            f"Realized: {sign}${real.realized_pnl:,.2f}\n"
            f"Open positions: {real.open_positions}"
        )
    else:
        blocks.append("💼 *Real portfolio*\nNo wallet linked. Use /wallet to set one up.")

    if paper.enabled:
        psign = "+" if paper.total_pnl >= 0 else ""
        blocks.append(
            "📝 *Paper portfolio*\n"
            f"Value: *${paper.portfolio_value:,.2f}*  "
            f"({psign}${paper.total_pnl:,.2f} vs ${paper.starting_balance:,.2f})\n"
            f"Cash: ${paper.cash:,.2f} · Positions: {paper.open_positions}\n"
            "Details: /paper"
        )
    else:
        blocks.append(
            "📝 *Paper portfolio*\nNo bankroll set. Try `/paper balance 1000` to start."
        )

    await update.message.reply_text(
        "\n\n".join(blocks), parse_mode="Markdown", disable_web_page_preview=True
    )
