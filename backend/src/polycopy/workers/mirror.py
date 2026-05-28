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
from polycopy.polymarket.data_api import PolymarketDataClient, Trade
from polycopy.polymarket.urls import market_url, profile_url

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
    our_size: float | None = None,
) -> MirrorDecision:
    """Scale a leader trade to a follower order.

    By default `size_pct` multiplies the leader's share count (1.0 = mirror 1:1).
    Pass `our_size` to use a precomputed share count instead (e.g. proportional
    sizing). Returns a skip decision (with a reason) when the trade can't/shouldn't
    be copied, otherwise an OrderRequest with a slippage-padded limit price.
    """
    if not 0 < trade.price < 1:
        return MirrorDecision(False, skip_reason=f"leader price out of range ({trade.price})")

    if our_size is None:
        if size_pct <= 0:
            return MirrorDecision(False, skip_reason="size_pct is zero")
        our_size = trade.size * size_pct

    our_size = round(our_size, 2)
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
    trader_wallet: str | None = None,
) -> str:
    """Human message sent to a follower when their leader trades.

    Trader and market are rendered as Markdown links to their polymarket.com
    pages so a follower can tap through from the Telegram alert.
    """
    action = "opened" if trade.side.upper() == "BUY" else "closed"
    market = (trade.title or "a market").strip()
    trader_md = (
        f"[{trader_label}]({profile_url(trader_wallet)})" if trader_wallet else f"*{trader_label}*"
    )
    murl = market_url(trade.event_slug or trade.slug)
    market_md = f"[{market}]({murl})" if murl else f"_{market}_"
    head = (
        f"🔔 {trader_md} {action} a position\n"
        f"{trade.outcome or '?'} · {trade.side} @ ${trade.price:.2f}\n"
        f"{market_md}\n"
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
        _trader_label(trader),
        trade,
        status=status,
        our_size=our_size,
        reason=reason,
        trader_wallet=trader.wallet,
    )
    await notify_user(user.telegram_id, text)


def _effective(follow: Follow, user: User) -> tuple[float, int, str]:
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
    sizing_mode = follow.sizing_mode_override or user.sizing_mode
    return size_pct, slippage, sizing_mode


async def _follower_portfolio_value(
    session: AsyncSession,
    data: PolymarketDataClient,
    user: User,
    *,
    paper: bool,
    funder: str,
) -> float:
    """Current total value of the follower's account (basis for proportional sizing)."""
    if paper:
        positions = await repo.get_paper_positions(session, user)
        value = user.paper_balance
        if positions:
            prices = await data.get_prices([p.token_id for p in positions])
            value += sum(p.shares * prices.get(p.token_id, p.avg_price) for p in positions)
        return value
    return await data.get_portfolio_value(funder)


async def _follower_held_shares(
    session: AsyncSession,
    data: PolymarketDataClient,
    user: User,
    token_id: str,
    *,
    paper: bool,
    funder: str,
) -> float:
    if paper:
        positions = await repo.get_paper_positions(session, user)
        return next((p.shares for p in positions if p.token_id == token_id), 0.0)
    positions = await data.get_positions(funder)
    return next((p.size for p in positions if p.token_id == token_id), 0.0)


async def _proportional_size(
    session: AsyncSession,
    *,
    user: User,
    trader: Trader,
    trade: Trade,
    paper: bool,
    funder: str,
) -> float | None:
    """Share count that mirrors the leader's portfolio allocation onto the follower.

    BUY: our_shares = leader_size * (our_portfolio / leader_portfolio) — i.e. the
    same fraction of our book the leader put into theirs (price cancels out).
    SELL: close the same fraction of our held position the leader closed of theirs.
    Returns None to fall back to multiplier sizing when a needed value is missing.
    """
    try:
        async with PolymarketDataClient() as data:
            follower_pv = await _follower_portfolio_value(
                session, data, user, paper=paper, funder=funder
            )
            if follower_pv <= 0:
                return None

            if trade.side.upper() == "BUY":
                leader_pv = await data.get_portfolio_value(trader.wallet)
                if leader_pv <= 0:
                    return None
                return trade.size * (follower_pv / leader_pv)

            # SELL: leader's position pre-sale ~= what remains now + what they sold.
            positions = await data.get_positions(trader.wallet)
            leader_remaining = next(
                (p.size for p in positions if p.token_id == trade.token_id), 0.0
            )
            leader_before = leader_remaining + trade.size
            if leader_before <= 0:
                return None
            fraction_closed = min(trade.size / leader_before, 1.0)
            held = await _follower_held_shares(
                session, data, user, trade.token_id, paper=paper, funder=funder
            )
            if held <= 0:
                return None
            return fraction_closed * held
    except Exception as exc:  # noqa: BLE001 - fall back to multiplier on any data hiccup
        log.warning("mirror.proportional_failed", user=user.id, error=str(exc))
        return None


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
    from polycopy.core.config import get_settings

    paper = get_settings().paper_trading or getattr(user, "paper_trading", False)
    size_pct, slippage, sizing_mode = _effective(follow, user)

    our_size = None
    if sizing_mode == "proportional":
        # None falls back to the size_pct multiplier inside decide_mirror.
        our_size = await _proportional_size(
            session, user=user, trader=trader, trade=trade, paper=paper,
            funder=creds.proxy_address,
        )
    decision = decide_mirror(
        trade, size_pct=size_pct, max_slippage_bps=slippage, our_size=our_size
    )

    common = dict(
        user_id=user.id,
        trader_id=trader.id,
        market_id=trade.condition_id,
        market_question=trade.title,
        market_slug=trade.event_slug or trade.slug,
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
        session,
        user,
        size=decision.our_size,
        price=decision.our_price,
        paper=paper,
        side=trade.side,
        token_id=trade.token_id,
        leader_price=trade.price,
        funder=creds.proxy_address,
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
    if paper:
        fill = await repo.apply_paper_fill(
            session,
            user,
            token_id=trade.token_id,
            condition_id=trade.condition_id,
            market_question=trade.title,
            market_slug=trade.event_slug or trade.slug,
            outcome=trade.outcome or "",
            side=trade.side,
            size=risk.size,
            price=decision.our_price,
        )
        if not fill.allowed:
            await repo.record_copied_trade(
                session, status="skipped", skip_reason=fill.reason, **common
            )
            log.info("mirror.paper_skip", user=user.id, reason=fill.reason)
            await _maybe_notify_copy(
                user, trader, trade, status="skipped", our_size=None, reason=fill.reason
            )
            return
        await repo.record_copied_trade(
            session,
            status="paper",
            our_price=decision.our_price,
            our_size=risk.size,
            pnl_usd=fill.realized_pnl,
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
