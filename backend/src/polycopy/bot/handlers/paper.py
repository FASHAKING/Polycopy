from telegram import Update
from telegram.ext import ContextTypes

from polycopy.bot.session import db_session
from polycopy.core import portfolio as portfolio_svc
from polycopy.core import repo
from polycopy.core.config import get_settings


def _parse_amount(raw: str) -> float | None:
    try:
        return float(raw.replace("$", "").replace(",", ""))
    except ValueError:
        return None


async def cmd_paper(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/paper on|off|balance <amt>|status — run a simulated trading account."""
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
                "and alerts — but place *no real orders*. Set a bankroll with "
                "`/paper balance 1000`. /paper off to go live."
            )
        elif arg in ("off", "disable"):
            user.paper_trading = False
            msg = "🟢 *Paper trading OFF*. Copies will now place real orders on Polymarket."
        elif arg in ("balance", "fund", "reset", "setbalance"):
            if len(ctx.args) < 2 or (amount := _parse_amount(ctx.args[1])) is None:
                msg = (
                    "Usage: `/paper balance 1000` — set your imaginary "
                    "bankroll (resets the account)."
                )
            elif amount < 0:
                msg = "Balance can't be negative."
            else:
                await repo.set_paper_balance(session, user, amount)
                if not user.paper_trading:
                    user.paper_trading = True
                msg = (
                    f"💰 Paper account funded with *${amount:,.2f}*. "
                    "Open positions were reset. Paper trading is *ON* — use /paper to view it."
                )
        else:
            p = await portfolio_svc.paper_portfolio(session, user)
            state = "ON" if (user.paper_trading or global_paper) else "OFF"
            forced = " (forced globally)" if global_paper else ""
            if not p.enabled:
                msg = (
                    f"Paper trading is *{state}*{forced}.\n"
                    "No bankroll set — set one with `/paper balance 1000` to track a "
                    "simulated portfolio. /paper on or /paper off to toggle."
                )
            else:
                msg = _format_paper(p, state, forced)

    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)


def _format_paper(p: portfolio_svc.PaperPortfolio, state: str, forced: str) -> str:
    sign = "+" if p.total_pnl >= 0 else ""
    value_line = (
        f"Value: *${p.portfolio_value:,.2f}*  "
        f"({sign}${p.total_pnl:,.2f} vs ${p.starting_balance:,.2f})"
    )
    lines = [
        f"📝 *Paper portfolio* (trading {state}{forced})",
        value_line,
        f"Cash: ${p.cash:,.2f} · Positions: ${p.market_value:,.2f}",
        f"Unrealized: ${p.unrealized_pnl:,.2f} · Realized: ${p.realized_pnl:,.2f}",
    ]
    if p.positions:
        lines.append("")
        for pos in p.positions[:10]:
            q = (pos.market_question or "market").strip()
            psign = "+" if pos.unrealized_pnl >= 0 else ""
            lines.append(
                f"• {pos.outcome} · {pos.shares:g} @ ${pos.avg_price:.2f} "
                f"→ ${pos.cur_price:.2f} ({psign}${pos.unrealized_pnl:,.2f})\n  _{q}_"
            )
    return "\n".join(lines)
