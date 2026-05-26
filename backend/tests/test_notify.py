from types import SimpleNamespace

from polycopy.polymarket.data_api import Trade
from polycopy.workers.mirror import format_copy_notification


def _trade(side="BUY", price=0.62, outcome="Yes", title="Will it rain?") -> Trade:
    return Trade.model_validate(
        {
            "proxyWallet": "0xleader",
            "side": side,
            "asset": "tok",
            "conditionId": "0xc",
            "size": 100,
            "price": price,
            "timestamp": 1,
            "outcome": outcome,
            "title": title,
        }
    )


def test_buy_says_opened_and_copying():
    msg = format_copy_notification(
        "swisstony", _trade(side="BUY"), status="submitted", our_size=20, reason=None
    )
    assert "swisstony" in msg
    assert "opened" in msg
    assert "Copying" in msg
    assert "20" in msg


def test_sell_says_closed():
    msg = format_copy_notification(
        "swisstony", _trade(side="SELL"), status="submitted", our_size=20, reason=None
    )
    assert "closed" in msg


def test_skipped_shows_reason():
    msg = format_copy_notification(
        "X", _trade(), status="skipped", our_size=None, reason="below minimum order"
    )
    assert "Not copied" in msg
    assert "below minimum" in msg


def test_rejected_shows_reason():
    msg = format_copy_notification(
        "X", _trade(), status="rejected", our_size=None, reason="insufficient balance"
    )
    assert "Couldn't copy" in msg
    assert "insufficient balance" in msg


async def test_execute_mirror_notifies(session, monkeypatch):
    from polycopy.core import repo
    from polycopy.workers import mirror

    user = await repo.get_or_create_user(session, telegram_id=42)
    trader = await repo.get_or_create_trader(session, wallet="0xlead", display_name="Lead")
    follow = await repo.add_follow(session, user, trader)

    sent = []

    async def fake_notify(tg_id, text):
        sent.append((tg_id, text))

    monkeypatch.setattr("polycopy.core.notify.notify_user", fake_notify)

    # Tiny trade -> skipped (below minimum), no order placed, but should notify.
    trade = _trade(side="BUY", price=0.5)
    trade.size = 1  # $0.50 notional < $1 min
    creds = SimpleNamespace(
        proxy_address="0x", private_key="0x", api_key="", api_secret="",
        api_passphrase="", signature_type=0,
    )
    await mirror.execute_mirror(
        session, user=user, trader=trader, follow=follow, trade=trade, creds=creds
    )
    assert len(sent) == 1
    assert sent[0][0] == 42
    assert "Not copied" in sent[0][1]


async def test_no_notify_when_disabled(session, monkeypatch):
    from polycopy.core import repo
    from polycopy.workers import mirror

    user = await repo.get_or_create_user(session, telegram_id=43)
    user.notifications_enabled = False
    await session.flush()
    trader = await repo.get_or_create_trader(session, wallet="0xlead2")
    follow = await repo.add_follow(session, user, trader)

    sent = []
    monkeypatch.setattr(
        "polycopy.core.notify.notify_user",
        lambda tg, text: sent.append(tg),
    )

    trade = _trade(side="BUY", price=0.5)
    trade.size = 1
    creds = SimpleNamespace(
        proxy_address="0x", private_key="0x", api_key="", api_secret="",
        api_passphrase="", signature_type=0,
    )
    await mirror.execute_mirror(
        session, user=user, trader=trader, follow=follow, trade=trade, creds=creds
    )
    assert sent == []
