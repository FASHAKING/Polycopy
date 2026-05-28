"""Per-user risk caps applied to a mirrored order before it's placed.

Each cap is independent and disabled at 0 (prices use their open defaults):
- max_notional_per_trade_usd: shrink an order to fit one-trade ceiling.
- daily_spend_cap_usd: bound total notional placed per UTC day.
- max_open_exposure_usd: bound total capital standing in open positions (BUYs).
- max_open_positions: cap the number of concurrent positions (BUYs into new markets).
- min_price / max_price: skip BUYs at extreme odds.

Shrinking caps reduce the order to fit; if the result falls below the exchange
minimum the trade is skipped. Position-count and price filters are hard skips.
Standing-risk caps apply to BUYs only — closing a position never adds risk.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import repo
from polycopy.core.logging import get_logger
from polycopy.core.models import User
from polycopy.workers.mirror import MIN_NOTIONAL_USD

log = get_logger(__name__)


@dataclass
class RiskOutcome:
    allowed: bool
    size: float
    reason: str | None = None


def _shrink_to_notional(price: float, budget: float) -> float:
    return budget / price if price > 0 else 0.0


async def _open_positions(
    session: AsyncSession, user: User, *, paper: bool, funder: str | None
) -> list[tuple[str, float]]:
    """(token_id, cost_basis_usd) for each open position on the relevant account."""
    if paper:
        positions = await repo.get_paper_positions(session, user)
        return [(p.token_id, p.shares * p.avg_price) for p in positions]
    if not funder:
        return []
    from polycopy.polymarket.data_api import PolymarketDataClient

    async with PolymarketDataClient() as data:
        positions = await data.get_positions(funder)
    return [(p.token_id, p.size * p.avg_price) for p in positions]


async def apply_risk_caps(
    session: AsyncSession,
    user: User,
    *,
    size: float,
    price: float,
    min_notional: float = MIN_NOTIONAL_USD,
    paper: bool = False,
    side: str = "BUY",
    token_id: str | None = None,
    leader_price: float | None = None,
    funder: str | None = None,
) -> RiskOutcome:
    is_buy = side.upper() == "BUY"

    # Extreme-odds filter (BUYs only — always allow exits).
    if is_buy and leader_price is not None:
        if user.min_price > 0 and leader_price < user.min_price:
            return RiskOutcome(
                False, 0.0, f"price {leader_price:.2f} below min {user.min_price:.2f}"
            )
        if user.max_price < 1 and leader_price > user.max_price:
            return RiskOutcome(
                False, 0.0, f"price {leader_price:.2f} above max {user.max_price:.2f}"
            )

    notional = size * price

    # Per-trade cap.
    if user.max_notional_per_trade_usd > 0 and notional > user.max_notional_per_trade_usd:
        size = _shrink_to_notional(price, user.max_notional_per_trade_usd)
        notional = size * price

    # Daily spend cap.
    if user.daily_spend_cap_usd > 0:
        spent = await repo.spent_today_usd(session, user, include_paper=paper)
        remaining = user.daily_spend_cap_usd - spent
        if remaining <= 0:
            return RiskOutcome(False, 0.0, "daily spend cap reached")
        if notional > remaining:
            size = _shrink_to_notional(price, remaining)
            notional = size * price

    # Standing-risk caps (open exposure + position count), BUYs only.
    if is_buy and (user.max_open_positions > 0 or user.max_open_exposure_usd > 0):
        try:
            positions = await _open_positions(session, user, paper=paper, funder=funder)
        except Exception as exc:  # noqa: BLE001 - tolerate upstream hiccups; don't block copies
            log.warning("risk.open_positions_failed", user=user.id, error=str(exc))
            positions = None

        if positions is not None:
            held = {tok for tok, _ in positions}
            opens_new = token_id is not None and token_id not in held
            if (
                user.max_open_positions > 0
                and opens_new
                and len(positions) >= user.max_open_positions
            ):
                return RiskOutcome(
                    False, 0.0, f"max open positions ({user.max_open_positions}) reached"
                )
            if user.max_open_exposure_usd > 0:
                current = sum(cost for _, cost in positions)
                remaining = user.max_open_exposure_usd - current
                if remaining <= 0:
                    return RiskOutcome(False, 0.0, "max open exposure reached")
                if notional > remaining:
                    size = _shrink_to_notional(price, remaining)
                    notional = size * price

    size = round(size, 2)
    if size <= 0 or size * price < min_notional:
        return RiskOutcome(False, 0.0, "capped below minimum order")
    return RiskOutcome(True, size)
