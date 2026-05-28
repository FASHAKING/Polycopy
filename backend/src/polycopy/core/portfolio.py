"""Portfolio views shared by the API and the bot.

`real_portfolio` reads the user's live Polymarket account; `paper_portfolio`
values the simulated paper account (cash + open positions marked to live market
prices). Both tolerate upstream hiccups and degrade gracefully.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import repo
from polycopy.core.models import User
from polycopy.polymarket.data_api import PolymarketDataClient
from polycopy.polymarket.stats import compute_realized_stats


@dataclass
class RealPortfolio:
    wallet_address: str | None
    portfolio_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    win_rate: float | None = None
    settled_markets: int = 0
    open_positions: int = 0


@dataclass
class PaperPositionView:
    token_id: str
    condition_id: str
    market_question: str | None
    market_slug: str | None
    outcome: str
    shares: float
    avg_price: float
    cur_price: float
    value: float
    unrealized_pnl: float


@dataclass
class PaperPortfolio:
    enabled: bool
    starting_balance: float = 0.0
    cash: float = 0.0
    market_value: float = 0.0
    portfolio_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    open_positions: int = 0
    win_rate: float | None = None
    settled_markets: int = 0
    positions: list[PaperPositionView] = field(default_factory=list)


async def close_paper(
    session: AsyncSession, user: User, *, token_id: str, shares: float | None = None
):
    """Close a paper position at the current market mid (cost basis if unavailable)."""
    price = None
    try:
        async with PolymarketDataClient() as data:
            price = await data.get_midpoint(token_id)
    except Exception:  # noqa: BLE001 - fall back to cost basis on a data hiccup
        price = None
    return await repo.close_paper_position(
        session, user, token_id=token_id, price=price, shares=shares
    )


async def real_portfolio(session: AsyncSession, user: User) -> RealPortfolio:
    cred = await repo.get_credential_meta(session, user)
    if cred is None:
        return RealPortfolio(wallet_address=None)

    out = RealPortfolio(wallet_address=cred.proxy_address)
    try:
        async with PolymarketDataClient() as data:
            positions = await data.get_positions(cred.proxy_address)
            out.portfolio_value = round(await data.get_portfolio_value(cred.proxy_address), 2)
            activity = await data.get_activity_paged(cred.proxy_address, max_events=2000)
        out.unrealized_pnl = round(sum(p.cash_pnl for p in positions), 2)
        out.open_positions = len(positions)
        rstats = compute_realized_stats(activity)
        out.win_rate = rstats.win_rate
        out.settled_markets = rstats.trades_count
        out.realized_pnl = round(
            (rstats.roi or 0.0) * rstats.volume_usd if rstats.roi else 0.0, 2
        )
    except Exception:  # noqa: BLE001 - dashboard tolerates upstream hiccups
        pass
    return out


async def paper_portfolio(session: AsyncSession, user: User) -> PaperPortfolio:
    starting = user.paper_starting_balance
    cash = user.paper_balance
    positions = await repo.get_paper_positions(session, user)

    prices: dict[str, float] = {}
    if positions:
        try:
            async with PolymarketDataClient() as data:
                prices = await data.get_prices([p.token_id for p in positions])
        except Exception:  # noqa: BLE001 - fall back to cost basis below
            prices = {}

    views: list[PaperPositionView] = []
    market_value = unrealized = 0.0
    for p in positions:
        cur = prices.get(p.token_id, p.avg_price)
        value = p.shares * cur
        upnl = p.shares * (cur - p.avg_price)
        market_value += value
        unrealized += upnl
        views.append(
            PaperPositionView(
                token_id=p.token_id,
                condition_id=p.condition_id,
                market_question=p.market_question,
                market_slug=p.market_slug,
                outcome=p.outcome,
                shares=round(p.shares, 2),
                avg_price=round(p.avg_price, 4),
                cur_price=round(cur, 4),
                value=round(value, 2),
                unrealized_pnl=round(upnl, 2),
            )
        )

    realized, win_rate, settled = await repo.paper_realized_stats(session, user)
    portfolio_value = cash + market_value
    return PaperPortfolio(
        enabled=starting > 0,
        starting_balance=round(starting, 2),
        cash=round(cash, 2),
        market_value=round(market_value, 2),
        portfolio_value=round(portfolio_value, 2),
        unrealized_pnl=round(unrealized, 2),
        realized_pnl=realized,
        total_pnl=round(portfolio_value - starting, 2),
        open_positions=len(views),
        win_rate=win_rate,
        settled_markets=settled,
        positions=views,
    )
