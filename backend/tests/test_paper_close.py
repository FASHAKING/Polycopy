from polycopy.core import repo


async def _funded_user_with_position(session, *, shares=100, price=0.50):
    user = await repo.get_or_create_user(session, telegram_id=1)
    await repo.set_paper_balance(session, user, 1000.0)
    await repo.apply_paper_fill(
        session, user, token_id="t1", condition_id="0xc", market_question="Q",
        market_slug="q", outcome="Yes", side="BUY", size=shares, price=price,
    )
    return user


async def test_close_realizes_profit_into_cash(session):
    user = await _funded_user_with_position(session)  # spent $50, cash = $950
    fill = await repo.close_paper_position(session, user, token_id="t1", price=0.80)
    assert fill.allowed
    assert fill.realized_pnl == 30.0  # 100 * (0.80 - 0.50)
    assert user.paper_balance == 1030.0  # 950 + 100 * 0.80 proceeds
    assert await repo.get_paper_positions(session, user) == []  # fully closed


async def test_close_realizes_loss(session):
    user = await _funded_user_with_position(session)
    fill = await repo.close_paper_position(session, user, token_id="t1", price=0.30)
    assert fill.allowed
    assert fill.realized_pnl == -20.0  # 100 * (0.30 - 0.50)
    assert user.paper_balance == 980.0  # 950 + 30 proceeds


async def test_partial_close_keeps_remaining_position(session):
    user = await _funded_user_with_position(session)
    fill = await repo.close_paper_position(session, user, token_id="t1", price=0.60, shares=40)
    assert fill.allowed and fill.realized_pnl == 4.0  # 40 * 0.10
    positions = await repo.get_paper_positions(session, user)
    assert len(positions) == 1 and positions[0].shares == 60


async def test_close_records_realized_trade_for_stats(session):
    user = await _funded_user_with_position(session)
    await repo.close_paper_position(session, user, token_id="t1", price=0.80)
    realized, win_rate, settled = await repo.paper_realized_stats(session, user)
    assert realized == 30.0 and settled == 1 and win_rate == 1.0


async def test_close_missing_position_is_rejected(session):
    user = await repo.get_or_create_user(session, telegram_id=2)
    await repo.set_paper_balance(session, user, 100.0)
    fill = await repo.close_paper_position(session, user, token_id="nope", price=0.5)
    assert not fill.allowed
    assert "no paper position" in fill.reason
