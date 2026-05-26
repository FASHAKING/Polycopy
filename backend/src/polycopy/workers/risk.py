"""Per-user risk caps applied to a mirrored order before it's placed.

Caps are enforceable from recorded trades (no realized-PnL needed):
- max_notional_per_trade_usd: shrink an order to fit, or skip if the shrunk
  size would fall below the exchange minimum.
- daily_spend_cap_usd: bound total notional placed per UTC day; shrink the
  order to the remaining budget, or skip if no room.

A cap of 0 means disabled.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import repo
from polycopy.core.models import User
from polycopy.workers.mirror import MIN_NOTIONAL_USD


@dataclass
class RiskOutcome:
    allowed: bool
    size: float
    reason: str | None = None


def _shrink_to_notional(price: float, budget: float) -> float:
    return budget / price if price > 0 else 0.0


async def apply_risk_caps(
    session: AsyncSession,
    user: User,
    *,
    size: float,
    price: float,
    min_notional: float = MIN_NOTIONAL_USD,
) -> RiskOutcome:
    notional = size * price

    # Per-trade cap.
    if user.max_notional_per_trade_usd > 0 and notional > user.max_notional_per_trade_usd:
        size = _shrink_to_notional(price, user.max_notional_per_trade_usd)
        notional = size * price

    # Daily spend cap.
    if user.daily_spend_cap_usd > 0:
        spent = await repo.spent_today_usd(session, user)
        remaining = user.daily_spend_cap_usd - spent
        if remaining <= 0:
            return RiskOutcome(False, 0.0, "daily spend cap reached")
        if notional > remaining:
            size = _shrink_to_notional(price, remaining)
            notional = size * price

    size = round(size, 2)
    if size <= 0 or size * price < min_notional:
        return RiskOutcome(False, 0.0, "capped below minimum order")
    return RiskOutcome(True, size)
