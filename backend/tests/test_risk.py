from polycopy.core import repo
from polycopy.workers.risk import apply_risk_caps


async def _user(session, **kw):
    user = await repo.get_or_create_user(session, telegram_id=1)
    for k, v in kw.items():
        setattr(user, k, v)
    await session.flush()
    return user


async def test_no_caps_allows_full_size(session):
    user = await _user(session)
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert out.allowed
    assert out.size == 100


async def test_per_trade_cap_shrinks(session):
    # 100 sh * $0.50 = $50 notional; cap $20 -> size 40
    user = await _user(session, max_notional_per_trade_usd=20)
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert out.allowed
    assert out.size == 40


async def test_daily_cap_blocks_when_exhausted(session):
    user = await _user(session, daily_spend_cap_usd=30)
    trader = await repo.get_or_create_trader(session, wallet="0xt")
    # Already spent $30 today.
    await repo.record_copied_trade(
        session,
        user_id=user.id,
        trader_id=trader.id,
        market_id="m",
        outcome="YES",
        side="BUY",
        leader_price=0.5,
        leader_size=1,
        our_price=0.5,
        our_size=60,  # 60 * 0.5 = $30
        status="submitted",
    )
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert not out.allowed
    assert "daily" in out.reason


async def test_daily_cap_shrinks_to_remaining(session):
    user = await _user(session, daily_spend_cap_usd=30)
    trader = await repo.get_or_create_trader(session, wallet="0xt")
    await repo.record_copied_trade(
        session,
        user_id=user.id,
        trader_id=trader.id,
        market_id="m",
        outcome="YES",
        side="BUY",
        leader_price=0.5,
        leader_size=1,
        our_price=0.5,
        our_size=40,  # $20 spent, $10 remaining
        status="submitted",
    )
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert out.allowed
    assert out.size == 20  # $10 remaining / $0.50


async def test_capped_below_minimum_skips(session):
    user = await _user(session, max_notional_per_trade_usd=0.5)
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert not out.allowed
    assert "minimum" in out.reason
