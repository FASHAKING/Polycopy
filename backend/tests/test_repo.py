
from polycopy.core import repo


async def test_get_or_create_user_is_idempotent(session):
    u1 = await repo.get_or_create_user(session, telegram_id=123, username="alice")
    u2 = await repo.get_or_create_user(session, telegram_id=123, username="alice2")
    assert u1.id == u2.id
    assert u2.telegram_username == "alice2"  # username refreshed


async def test_credentials_roundtrip_encrypted(session):
    from sqlalchemy import select

    from polycopy.core.models import PolymarketCredential

    user = await repo.get_or_create_user(session, telegram_id=1)
    await repo.set_credentials(
        session,
        user,
        proxy_address="0xfunder",
        private_key="0x" + "ab" * 32,
        api_key="key",
        api_secret="secret",
        api_passphrase="pass",
    )

    # Stored ciphertext must not equal plaintext.
    res = await session.execute(
        select(PolymarketCredential).where(PolymarketCredential.user_id == user.id)
    )
    cred = res.scalar_one()
    assert cred.api_secret_enc != "secret"
    assert cred.private_key_enc != "0x" + "ab" * 32

    bundle = await repo.get_credential_bundle(session, user)
    assert bundle is not None
    assert bundle.private_key == "0x" + "ab" * 32
    assert bundle.api_secret == "secret"
    assert bundle.api_passphrase == "pass"
    assert bundle.proxy_address == "0xfunder"


async def test_set_credentials_replaces_existing(session):
    user = await repo.get_or_create_user(session, telegram_id=2)
    await repo.set_credentials(
        session, user, proxy_address="0x1", private_key="k1",
        api_key="a1", api_secret="s1", api_passphrase="p1",
    )
    await repo.set_credentials(
        session, user, proxy_address="0x2", private_key="k2",
        api_key="a2", api_secret="s2", api_passphrase="p2",
    )
    bundle = await repo.get_credential_bundle(session, user)
    assert bundle.proxy_address == "0x2"
    assert bundle.private_key == "k2"


async def test_no_credentials_returns_none(session):
    user = await repo.get_or_create_user(session, telegram_id=3)
    assert await repo.get_credential_bundle(session, user) is None
    assert await repo.has_credentials(session, user) is False


async def test_trader_wallet_normalized(session):
    t1 = await repo.get_or_create_trader(session, wallet="0xABCDEF", display_name="Bob")
    t2 = await repo.get_or_create_trader(session, wallet="0xabcdef")
    assert t1.id == t2.id
    assert t1.wallet == "0xabcdef"


async def test_follow_lifecycle(session):
    user = await repo.get_or_create_user(session, telegram_id=4)
    trader = await repo.get_or_create_trader(session, wallet="0xtrader")

    await repo.add_follow(session, user, trader, source="manual")
    follows = await repo.list_active_follows(session, user)
    assert len(follows) == 1
    assert follows[0][1].wallet == "0xtrader"

    # Trader now appears in the watcher's work list.
    watched = await repo.list_watched_traders(session)
    assert [t.wallet for t in watched] == ["0xtrader"]

    # Unfollow deactivates.
    assert await repo.deactivate_follow(session, user, trader) is True
    assert await repo.list_active_follows(session, user) == []
    assert await repo.list_watched_traders(session) == []

    # Re-following reactivates the same row.
    await repo.add_follow(session, user, trader)
    assert len(await repo.list_active_follows(session, user)) == 1


async def test_followers_fanout(session):
    trader = await repo.get_or_create_trader(session, wallet="0xstar")
    u1 = await repo.get_or_create_user(session, telegram_id=10)
    u2 = await repo.get_or_create_user(session, telegram_id=11)
    await repo.add_follow(session, u1, trader)
    await repo.add_follow(session, u2, trader)

    followers = await repo.list_followers_of_trader(session, trader)
    assert {f[1].telegram_id for f in followers} == {10, 11}


async def test_record_and_list_copied_trades(session):
    user = await repo.get_or_create_user(session, telegram_id=5)
    trader = await repo.get_or_create_trader(session, wallet="0xt")
    await repo.record_copied_trade(
        session,
        user_id=user.id,
        trader_id=trader.id,
        market_id="m1",
        outcome="YES",
        side="BUY",
        leader_price=0.5,
        leader_size=100.0,
        status="filled",
    )
    trades = await repo.list_copied_trades(session, user)
    assert len(trades) == 1
    assert trades[0].market_id == "m1"
