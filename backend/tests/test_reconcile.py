from polycopy.core import repo
from polycopy.polymarket.clob import OrderStatus


def test_status_filled():
    s = OrderStatus(raw_status="MATCHED", original_size=100, size_matched=100, price=0.5)
    assert s.resolved == "filled"


def test_status_partial():
    s = OrderStatus(raw_status="LIVE", original_size=100, size_matched=40, price=0.5)
    assert s.resolved == "partial"


def test_status_still_open():
    s = OrderStatus(raw_status="LIVE", original_size=100, size_matched=0, price=0.5)
    assert s.resolved == "submitted"


def test_status_canceled():
    s = OrderStatus(raw_status="CANCELED", original_size=100, size_matched=0, price=None)
    assert s.resolved == "canceled"


def test_status_not_found_is_canceled():
    s = OrderStatus(raw_status="", original_size=0, size_matched=0, price=None, found=False)
    assert s.resolved == "canceled"


async def test_list_pending_fills_filters(session):
    user = await repo.get_or_create_user(session, telegram_id=1)
    trader = await repo.get_or_create_trader(session, wallet="0xt")
    base = dict(
        user_id=user.id, trader_id=trader.id, market_id="m", outcome="YES",
        side="BUY", leader_price=0.5, leader_size=10,
    )
    await repo.record_copied_trade(session, status="submitted", our_order_id="o1", **base)
    await repo.record_copied_trade(session, status="partial", our_order_id="o2", **base)
    await repo.record_copied_trade(session, status="filled", our_order_id="o3", **base)
    await repo.record_copied_trade(session, status="skipped", our_order_id=None, **base)
    await repo.record_copied_trade(session, status="submitted", our_order_id=None, **base)

    pending = await repo.list_pending_fills(session)
    ids = {t.our_order_id for t in pending}
    assert ids == {"o1", "o2"}
