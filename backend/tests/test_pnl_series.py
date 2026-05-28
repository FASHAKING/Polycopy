from datetime import datetime, timedelta

from polycopy.core import repo


async def test_paper_series_is_cumulative_within_window(session):
    user = await repo.get_or_create_user(session, telegram_id=1)
    await repo.set_paper_balance(session, user, 1000)
    trader = await repo.get_or_create_trader(session, wallet="0xt")

    async def _closed(pnl, when):
        t = await repo.record_copied_trade(
            session, user_id=user.id, trader_id=trader.id, market_id="m",
            outcome="YES", side="SELL", leader_price=0.5, leader_size=1,
            our_price=0.6, our_size=10, status="paper", pnl_usd=pnl,
        )
        t.created_at = when
        await session.flush()

    now = datetime.utcnow()
    await _closed(5.0, now - timedelta(hours=3))   # outside a 1h window
    await _closed(10.0, now - timedelta(minutes=30))
    await _closed(-4.0, now - timedelta(minutes=10))

    day = await repo.paper_pnl_series(session, user, since=now - timedelta(days=1))
    assert [p for _, p in day] == [5.0, 15.0, 11.0]  # cumulative

    hour = await repo.paper_pnl_series(session, user, since=now - timedelta(hours=1))
    assert [p for _, p in hour] == [10.0, 6.0]  # window excludes the -3h trade


async def test_real_snapshots_round_trip(session):
    user = await repo.get_or_create_user(session, telegram_id=2)
    now = datetime.utcnow()
    s1 = await repo.record_account_snapshot(
        session, user, account="real", portfolio_value=100, pnl=0
    )
    s1.created_at = now - timedelta(minutes=20)
    s2 = await repo.record_account_snapshot(
        session, user, account="real", portfolio_value=130, pnl=30
    )
    s2.created_at = now - timedelta(minutes=5)
    # A paper snapshot must not leak into the real series.
    await repo.record_account_snapshot(
        session, user, account="paper", portfolio_value=999, pnl=999
    )
    await session.flush()

    snaps = await repo.get_account_snapshots(
        session, user, account="real", since=now - timedelta(hours=1)
    )
    assert [s.pnl for s in snaps] == [0, 30]


async def test_snapshot_worker_records_enabled_accounts(session, monkeypatch):
    from polycopy.workers import snapshot

    user = await repo.get_or_create_user(session, telegram_id=3)
    await repo.set_paper_balance(session, user, 500)
    await session.commit()

    # snapshot_once opens its own sessions; point them at the test session.
    class _Maker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(snapshot, "SessionLocal", _Maker())
    monkeypatch.setattr(session, "commit", session.flush)

    await snapshot.snapshot_once()

    snaps = await repo.get_account_snapshots(
        session, user, account="paper", since=datetime.utcnow() - timedelta(hours=1)
    )
    assert len(snaps) == 1
    assert snaps[0].portfolio_value == 500  # cash only, no positions yet
