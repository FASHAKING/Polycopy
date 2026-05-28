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


async def test_daily_cap_ignores_paper_fills_by_default(session):
    # A paper fill today shouldn't consume the real daily budget.
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
        our_size=60,  # $30 of simulated spend
        status="paper",
    )
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert out.allowed and out.size == 60  # full $30 budget still available


async def test_daily_cap_counts_paper_fills_in_paper_mode(session):
    # In paper mode the same simulated spend should exhaust the daily budget.
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
        our_size=60,  # $30 of simulated spend
        status="paper",
    )
    out = await apply_risk_caps(session, user, size=100, price=0.5, paper=True)
    assert not out.allowed
    assert "daily" in out.reason


async def test_capped_below_minimum_skips(session):
    user = await _user(session, max_notional_per_trade_usd=0.5)
    out = await apply_risk_caps(session, user, size=100, price=0.5)
    assert not out.allowed
    assert "minimum" in out.reason


async def _hold(session, user, token, shares, price=0.5):
    await repo.apply_paper_fill(
        session, user, token_id=token, condition_id="0xc", market_question="Q",
        market_slug="q", outcome="Yes", side="BUY", size=shares, price=price,
    )


async def test_exposure_cap_shrinks_to_remaining(session):
    user = await _user(session, max_open_exposure_usd=60)
    await repo.set_paper_balance(session, user, 10_000)
    await _hold(session, user, "held", 100, 0.5)  # $50 cost basis open
    out = await apply_risk_caps(
        session, user, size=100, price=0.5, paper=True, side="BUY", token_id="new"
    )
    assert out.allowed and out.size == 20  # $10 of $60 budget left / $0.50


async def test_exposure_cap_blocks_when_full(session):
    user = await _user(session, max_open_exposure_usd=50)
    await repo.set_paper_balance(session, user, 10_000)
    await _hold(session, user, "held", 100, 0.5)  # $50 already at risk
    out = await apply_risk_caps(
        session, user, size=100, price=0.5, paper=True, side="BUY", token_id="new"
    )
    assert not out.allowed
    assert "exposure" in out.reason


async def test_max_positions_blocks_new_market(session):
    user = await _user(session, max_open_positions=1)
    await repo.set_paper_balance(session, user, 10_000)
    await _hold(session, user, "held", 100, 0.5)
    out = await apply_risk_caps(
        session, user, size=10, price=0.5, paper=True, side="BUY", token_id="new"
    )
    assert not out.allowed
    assert "positions" in out.reason


async def test_max_positions_allows_adding_to_held(session):
    user = await _user(session, max_open_positions=1)
    await repo.set_paper_balance(session, user, 10_000)
    await _hold(session, user, "held", 100, 0.5)
    out = await apply_risk_caps(
        session, user, size=10, price=0.5, paper=True, side="BUY", token_id="held"
    )
    assert out.allowed and out.size == 10  # topping up an existing position is fine


async def test_price_filter_skips_extreme_buys(session):
    user = await _user(session, min_price=0.1, max_price=0.9)
    low = await apply_risk_caps(
        session, user, size=100, price=0.5, side="BUY", leader_price=0.05
    )
    assert not low.allowed and "below min" in low.reason
    high = await apply_risk_caps(
        session, user, size=100, price=0.5, side="BUY", leader_price=0.95
    )
    assert not high.allowed and "above max" in high.reason


async def test_price_filter_ignores_sells(session):
    # Exits should go through even at extreme odds.
    user = await _user(session, min_price=0.1, max_price=0.9)
    out = await apply_risk_caps(
        session, user, size=100, price=0.5, side="SELL", leader_price=0.95
    )
    assert out.allowed
