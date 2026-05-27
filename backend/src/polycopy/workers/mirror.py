"""Turn a leader's trade into a mirrored order for a follower, and execute it.

`decide_mirror` is pure and the unit-testable heart of copy sizing; `execute_mirror`
performs the side effects (place order via CLOB, record the CopiedTrade).
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import repo
from polycopy.core.logging import get_logger
from polycopy.core.models import Follow, Trader, User
from polycopy.polymarket.clob import ClobClient, CredBundle, OrderRequest, clamp_price
from polycopy.polymarket.data_api import Trade

log = get_logger(__name__)

# Polymarket's practical minimum order is ~$1 notional.
MIN_NOTIONAL_USD = 1.0


@dataclass
class MirrorDecision:
    should_copy: bool
    order: OrderRequest | None = None
    our_size: float | None = None
    our_price: float | None = None
    skip_reason: str | None = None


def decide_mirror(
    trade: Trade,
    *,
    size_pct: float,
    max_slippage_bps: int,
    min_notional_usd: float = MIN_NOTIONAL_USD,
) -> MirrorDecision:
    """Scale a leader trade to a follower order.

    `size_pct` is a multiplier on the leader's share count (1.0 = mirror 1:1).
    Returns a skip decision (with a reason) when the trade can't/shouldn't be
    copied, otherwise an OrderRequest with a slippage-padded limit price.
    """
    if size_pct <= 0:
        return MirrorDecision(False, skip_reason="size_pct is zero")
    if not 0 < trade.price < 1:
        return MirrorDecision(False, skip_reason=f"leader price out of range ({trade.price})")

    our_size = round(trade.size * size_pct, 2)
    notional = our_size * trade.price
    if our_size <= 0 or notional < min_notional_usd:
        return MirrorDecision(
            False, skip_reason=f"below minimum order (${notional:.2f} < ${min_notional_usd:.2f})"
        )

    our_price = clamp_price(trade.price, trade.side, max_slippage_bps)
    order = OrderRequest(
        token_id=trade.token_id, side=trade.side, price=our_price, size=our_size
    )
    return MirrorDecision(True, order=order, our_size=our_size, our_price=our_price)


def _trader_label(trader: Trader) -> str:
    return trader.display_name or f"{trader.wallet[:6]}…{trader.wallet[-4:]}"


def format_copy_notification(
    trader_label: str,
    trade: Trade,
    *,
    status: str,
    our_size: float | None,
    reason: str | None,
) -> str:
    """Human message sent to a follower when their leader trades."""
    action = "opened" if trade.side.upper() == "BUY" else "closed"
    market = (trade.title or "a market").strip()
    head = (
        f"🔔 *{trader_label}* {action} a position\n"
        f"{trade.outcome or '?'} · {trade.side} @ ${trade.price:.2f}\n"
        f"_{market}_\n"
    )
    if status == "paper":
        notional = (our_size or 0) * trade.price
        tail = (
            f"\n📝 *Paper trade* — would copy {our_size:g} shares "
            f"(~${notional:,.2f}). No real order placed."
        )
    elif status in ("submitted", "filled"):
        notional = (our_size or 0) * trade.price
        tail = f"\n✅ Copying *{our_size:g}* shares (~${notional:,.2f}) into your wallet"
    elif status == "rejected":
        tail = f"\n⚠️ Couldn't copy: {reason or 'order rejected'}"
    else:  # skipped
        tail = f"\n↳ Not copied: {reason or 'skipped'}"
    return head + tail


async def _maybe_notify_copy(
    user: User,
    trader: Trader,
    trade: Trade,
    *,
    status: str,
    our_size: float | None,
    reason: str | None,
) -> None:
    if not getattr(user, "notifications_enabled", True):
        return
    from polycopy.core.notify import notify_user

    text = format_copy_notification(
        _trader_label(trader), trade, status=status, our_size=our_size, reason=reason
    )
    await notify_user(user.telegram_id, text)


def _effective(follow: Follow, user: User) -> tuple[float, int]:
    size_pct = (
        follow.size_pct_override
        if follow.size_pct_override is not None
        else user.default_size_pct
    )
    slippage = (
        follow.max_slippage_bps_override
        if follow.max_slippage_bps_override is not None
        else user.max_slippage_bps
    )
    return size_pct, slippage


async def execute_mirror(
    session: AsyncSession,
    *,
    user: User,
    trader: Trader,
    follow: Follow,
    trade: Trade,
    creds: CredBundle,
) -> None:
    """Decide, place (if applicable), and persist a mirrored trade for one follower."""
    size_pct, slippage = _effective(follow, user)
    decision = decide_mirror(trade, size_pct=size_pct, max_slippage_bps=slippage)

    common = dict(
        user_id=user.id,
        trader_id=trader.id,
        market_id=trade.condition_id,
        market_question=trade.title,
        outcome=trade.outcome or "",
        side=trade.side,
        leader_tx_hash=trade.tx_hash,
        leader_price=trade.price,
        leader_size=trade.size,
    )

    if not decision.should_copy:
        await repo.record_copied_trade(
            session, status="skipped", skip_reason=decision.skip_reason, **common
        )
        log.info("mirror.skip", user=user.id, reason=decision.skip_reason)
        await _maybe_notify_copy(
            user, trader, trade, status="skipped", our_size=None, reason=decision.skip_reason
        )
        return

    # Apply per-user risk caps; may shrink the order or skip it entirely.
    from polycopy.workers.risk import apply_risk_caps

    risk = await apply_risk_caps(
        session, user, size=decision.our_size, price=decision.our_price
    )
    if not risk.allowed:
        await repo.record_copied_trade(
            session, status="skipped", skip_reason=risk.reason, **common
        )
        log.info("mirror.risk_skip", user=user.id, reason=risk.reason)
        await _maybe_notify_copy(
            user, trader, trade, status="skipped", our_size=None, reason=risk.reason
        )
        return

    order = decision.order
    order.size = risk.size

    # Paper mode: run everything except the real order placement.
    from polycopy.core.config import get_settings

    if get_settings().paper_trading or getattr(user, "paper_trading", False):
        await repo.record_copied_trade(
            session,
            status="paper",
            our_price=decision.our_price,
            our_size=risk.size,
            **common,
        )
        log.info("mirror.paper", user=user.id, trader=trader.wallet, size=risk.size)
        await _maybe_notify_copy(
            user, trader, trade, status="paper", our_size=risk.size, reason=None
        )
        return

    client = ClobClient(creds)
    result = await asyncio.to_thread(client.place_order, order)

    status = "submitted" if result.accepted else "rejected"
    reason = None if result.accepted else (result.error or "order rejected")
    await repo.record_copied_trade(
        session,
        status=status,
        our_order_id=result.order_id,
        our_price=decision.our_price,
        our_size=risk.size,
        skip_reason=reason,
        **common,
    )
    log.info(
        "mirror.executed",
        user=user.id,
        trader=trader.wallet,
        accepted=result.accepted,
        order_id=result.order_id,
    )
    await _maybe_notify_copy(
        user, trader, trade, status=status, our_size=risk.size, reason=reason
    )
