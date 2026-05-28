from types import SimpleNamespace

from polycopy.polymarket.data_api import Trade
from polycopy.workers import mirror
from polycopy.workers.mirror import format_copy_notification


def _trade(side="BUY", price=0.5, size=100) -> Trade:
    return Trade.model_validate(
        {
            "proxyWallet": "0xleader",
            "side": side,
            "asset": "tok",
            "conditionId": "0xc",
            "size": size,
            "price": price,
            "timestamp": 1,
            "outcome": "Yes",
            "title": "Market?",
        }
    )


def test_paper_notification_text():
    msg = format_copy_notification(
        "swisstony", _trade(), status="paper", our_size=50, reason=None
    )
    assert "Paper trade" in msg
    assert "No real order placed" in msg


async def test_paper_mode_records_paper_and_skips_placement(session, monkeypatch):
    from polycopy.core import repo

    user = await repo.get_or_create_user(session, telegram_id=1)
    user.paper_trading = True
    await session.flush()
    trader = await repo.get_or_create_trader(session, wallet="0xlead", display_name="Lead")
    follow = await repo.add_follow(session, user, trader)

    # Fail loudly if a real order is attempted.
    def _boom(self, order):  # noqa: ANN001
        raise AssertionError("place_order must not run in paper mode")

    monkeypatch.setattr(mirror.ClobClient, "place_order", _boom)

    sent = []

    async def _capture(tg, t):
        sent.append(t)

    monkeypatch.setattr("polycopy.core.notify.notify_user", _capture)

    creds = SimpleNamespace(
        proxy_address="0x", private_key="0x", api_key="", api_secret="",
        api_passphrase="", signature_type=0,
    )
    await mirror.execute_mirror(
        session, user=user, trader=trader, follow=follow, trade=_trade(), creds=creds
    )

    trades = await repo.list_copied_trades(session, user)
    assert len(trades) == 1
    assert trades[0].status == "paper"
    assert trades[0].our_size == 100  # size_pct default 1.0
    assert sent and "Paper trade" in sent[0]


async def test_paper_balance_accounting_buy_then_sell(session):
    from polycopy.core import repo

    user = await repo.get_or_create_user(session, telegram_id=10)
    await repo.set_paper_balance(session, user, 100.0)
    assert user.paper_balance == 100.0

    buy = await repo.apply_paper_fill(
        session, user, token_id="t1", condition_id="0xc", market_question="Q",
        market_slug="q", outcome="Yes", side="BUY", size=100, price=0.50,
    )
    assert buy.allowed
    assert user.paper_balance == 50.0
    positions = await repo.get_paper_positions(session, user)
    assert len(positions) == 1 and positions[0].shares == 100 and positions[0].avg_price == 0.50

    sell = await repo.apply_paper_fill(
        session, user, token_id="t1", condition_id="0xc", market_question="Q",
        market_slug="q", outcome="Yes", side="SELL", size=100, price=0.60,
    )
    assert sell.allowed
    assert sell.realized_pnl == 10.0  # 100 * (0.60 - 0.50)
    assert user.paper_balance == 110.0
    assert await repo.get_paper_positions(session, user) == []


async def test_paper_balance_insufficient_is_rejected(session):
    from polycopy.core import repo

    user = await repo.get_or_create_user(session, telegram_id=11)
    await repo.set_paper_balance(session, user, 10.0)
    fill = await repo.apply_paper_fill(
        session, user, token_id="t1", condition_id="0xc", market_question=None,
        market_slug=None, outcome="Yes", side="BUY", size=100, price=0.50,
    )
    assert not fill.allowed
    assert "insufficient paper balance" in fill.reason
    assert user.paper_balance == 10.0  # untouched


async def test_paper_fill_noop_without_balance(session):
    from polycopy.core import repo

    user = await repo.get_or_create_user(session, telegram_id=12)  # no balance set
    fill = await repo.apply_paper_fill(
        session, user, token_id="t1", condition_id="0xc", market_question=None,
        market_slug=None, outcome="Yes", side="BUY", size=100, price=0.50,
    )
    assert fill.allowed
    assert await repo.get_paper_positions(session, user) == []


async def test_global_paper_forces_simulation(session, monkeypatch):
    from polycopy.core import config, repo

    config.get_settings.cache_clear()
    monkeypatch.setattr(
        config, "get_settings", lambda: config.Settings(paper_trading=True, fernet_key="x")
    )
    # mirror imports get_settings from polycopy.core.config at call time
    monkeypatch.setattr(
        "polycopy.core.config.get_settings",
        lambda: config.Settings(paper_trading=True, fernet_key="x"),
    )

    user = await repo.get_or_create_user(session, telegram_id=2)  # user flag stays False
    trader = await repo.get_or_create_trader(session, wallet="0xlead2")
    follow = await repo.add_follow(session, user, trader)

    monkeypatch.setattr(
        mirror.ClobClient,
        "place_order",
        lambda self, o: (_ for _ in ()).throw(AssertionError("no real order")),
    )
    async def _noop(tg, t):
        return None

    monkeypatch.setattr("polycopy.core.notify.notify_user", _noop)

    creds = SimpleNamespace(
        proxy_address="0x", private_key="0x", api_key="", api_secret="",
        api_passphrase="", signature_type=0,
    )
    await mirror.execute_mirror(
        session, user=user, trader=trader, follow=follow, trade=_trade(), creds=creds
    )
    trades = await repo.list_copied_trades(session, user)
    assert trades[0].status == "paper"
