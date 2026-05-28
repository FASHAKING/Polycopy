from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polycopy.polymarket.data_api import Trade
from polycopy.workers.watcher import new_trades_since


def _trade(ts: int, h: str) -> Trade:
    return Trade.model_validate(
        {
            "proxyWallet": "0xleader",
            "side": "BUY",
            "asset": "tok",
            "conditionId": "0xcond",
            "size": 10.0,
            "price": 0.5,
            "timestamp": ts,
            "transactionHash": h,
        }
    )


# Newest-first, as the API returns them.
TRADES = [_trade(300, "c"), _trade(200, "b"), _trade(100, "a")]


def test_no_cursor_means_no_copy():
    assert new_trades_since(TRADES, None, None) == []


def test_stops_at_known_hash_and_returns_oldest_first():
    last_ts = datetime.utcfromtimestamp(100)
    fresh = new_trades_since(TRADES, last_ts, "a")
    # "b" and "c" are new; "a" is the watermark; order oldest-first
    assert [t.tx_hash for t in fresh] == ["b", "c"]


def test_nothing_new_when_latest_is_known():
    last_ts = datetime.utcfromtimestamp(300)
    assert new_trades_since(TRADES, last_ts, "c") == []


def test_timestamp_guard_when_hash_missing():
    # Hash not present; bound by timestamp >= cutoff (200) => keeps b, c
    last_ts = datetime.utcfromtimestamp(200)
    fresh = new_trades_since(TRADES, last_ts, "unknown-hash")
    assert [t.tx_hash for t in fresh] == ["b", "c"]


def _paper_trade() -> Trade:
    return Trade.model_validate(
        {
            "proxyWallet": "0xlead",
            "side": "BUY",
            "asset": "tok",
            "conditionId": "0xcond",
            "size": 100.0,
            "price": 0.5,
            "timestamp": 1,
            "outcome": "Yes",
            "title": "Market?",
        }
    )


async def test_fan_out_persists_paper_balance(tmp_path, monkeypatch):
    """A paper buy fanned out to a follower must debit the persisted balance.

    The fan-out loads followers in one session then mirrors each in a fresh
    per-follower session; the user must be re-attached there or the cash
    debit is silently dropped (it lives on a detached object).
    """
    from polycopy.core import models, repo
    from polycopy.core.db import Base
    from polycopy.workers import mirror, watcher

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(watcher, "SessionLocal", maker)

    async with maker() as s:
        user = await repo.get_or_create_user(s, telegram_id=99)
        user.paper_trading = True
        await repo.set_paper_balance(s, user, 100.0)
        trader = await repo.get_or_create_trader(s, wallet="0xlead", display_name="Lead")
        await repo.add_follow(s, user, trader)
        await repo.set_credentials(
            s, user, proxy_address="0x", private_key="0x",
            api_key="k", api_secret="sec", api_passphrase="pp",
        )
        await s.commit()
        user_id, trader_id = user.id, trader.id

    monkeypatch.setattr(
        mirror.ClobClient, "place_order",
        lambda self, o: (_ for _ in ()).throw(AssertionError("no real order in paper mode")),
    )

    async def _noop(tg, t):
        return None

    monkeypatch.setattr("polycopy.core.notify.notify_user", _noop)

    await watcher._fan_out(_paper_trade(), trader_id)

    async with maker() as s:
        u = await s.get(models.User, user_id)
        # 100 - (100 shares * $0.51 slippage-padded BUY price).
        assert u.paper_balance == 49.0
        positions = await repo.get_paper_positions(s, u)
        assert len(positions) == 1 and positions[0].shares == 100
    await engine.dispose()
