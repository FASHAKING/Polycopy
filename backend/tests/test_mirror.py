from types import SimpleNamespace

from polycopy.core import repo
from polycopy.polymarket.data_api import Position, Trade
from polycopy.workers import mirror
from polycopy.workers.mirror import _effective, _proportional_size, decide_mirror


def _trade(side="BUY", price=0.5, size=100.0) -> Trade:
    return Trade.model_validate(
        {
            "proxyWallet": "0xleader",
            "side": side,
            "asset": "tok",
            "conditionId": "0xcond",
            "size": size,
            "price": price,
            "timestamp": 1779784494,
            "outcome": "Yes",
        }
    )


def _position(token_id="tok", size=300.0) -> Position:
    return Position.model_validate(
        {
            "proxyWallet": "0xleader",
            "asset": token_id,
            "conditionId": "0xcond",
            "size": size,
            "avgPrice": 0.5,
        }
    )


class _FakeData:
    """Stand-in for PolymarketDataClient used as an async context manager."""

    def __init__(self, *, pv=0.0, positions=None, prices=None):
        self._pv = pv
        self._positions = positions or []
        self._prices = prices or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get_portfolio_value(self, _wallet):
        return self._pv

    async def get_positions(self, _wallet):
        return self._positions

    async def get_prices(self, _token_ids):
        return self._prices


def test_mirror_scales_size():
    d = decide_mirror(_trade(size=100), size_pct=0.5, max_slippage_bps=200)
    assert d.should_copy
    assert d.our_size == 50.0
    assert d.order.token_id == "tok"


def test_mirror_buy_pads_price_up():
    d = decide_mirror(_trade(side="BUY", price=0.50), size_pct=1.0, max_slippage_bps=200)
    assert d.our_price == 0.51


def test_mirror_sell_pads_price_down():
    d = decide_mirror(_trade(side="SELL", price=0.50), size_pct=1.0, max_slippage_bps=200)
    assert d.our_price == 0.49


def test_mirror_skips_below_minimum():
    # 1 share * $0.50 = $0.50 notional < $1 minimum
    d = decide_mirror(_trade(price=0.50, size=1), size_pct=1.0, max_slippage_bps=200)
    assert not d.should_copy
    assert "minimum" in d.skip_reason


def test_mirror_skips_zero_size_pct():
    d = decide_mirror(_trade(), size_pct=0.0, max_slippage_bps=200)
    assert not d.should_copy


def test_mirror_skips_out_of_range_price():
    d = decide_mirror(_trade(price=1.0), size_pct=1.0, max_slippage_bps=200)
    assert not d.should_copy
    assert "out of range" in d.skip_reason


def test_mirror_honors_explicit_size():
    # our_size overrides the multiplier but still pads price + checks minimum.
    d = decide_mirror(_trade(size=100), size_pct=1.0, max_slippage_bps=200, our_size=12.3)
    assert d.should_copy
    assert d.our_size == 12.3
    assert d.our_price == 0.51


def test_effective_resolves_sizing_mode():
    user = SimpleNamespace(default_size_pct=1.0, max_slippage_bps=200, sizing_mode="multiplier")
    follow = SimpleNamespace(
        size_pct_override=None, max_slippage_bps_override=None, sizing_mode_override=None
    )
    assert _effective(follow, user)[2] == "multiplier"
    follow.sizing_mode_override = "proportional"  # per-follow override wins
    assert _effective(follow, user)[2] == "proportional"


async def test_proportional_buy_matches_portfolio_fraction(session, monkeypatch):
    # Leader book $1000, ours $200 -> we deploy 1/5 of their 100 shares = 20.
    user = await repo.get_or_create_user(session, telegram_id=1)
    await repo.set_paper_balance(session, user, 200.0)
    trader = await repo.get_or_create_trader(session, wallet="0xlead")
    monkeypatch.setattr(mirror, "PolymarketDataClient", lambda: _FakeData(pv=1000.0))

    size = await _proportional_size(
        session, user=user, trader=trader, trade=_trade(side="BUY", size=100),
        paper=True, funder="0xme",
    )
    assert size == 20.0


async def test_proportional_sell_mirrors_close_fraction(session, monkeypatch):
    # Leader had 400 (300 left + 100 sold) -> closed 25%; we hold 80 -> sell 20.
    user = await repo.get_or_create_user(session, telegram_id=2)
    await repo.set_paper_balance(session, user, 100.0)
    await repo.apply_paper_fill(
        session, user, token_id="tok", condition_id="0xc", market_question="Q",
        market_slug="q", outcome="Yes", side="BUY", size=80, price=0.5,
    )
    trader = await repo.get_or_create_trader(session, wallet="0xlead")
    monkeypatch.setattr(
        mirror, "PolymarketDataClient",
        lambda: _FakeData(positions=[_position(size=300)], prices={"tok": 0.5}),
    )

    size = await _proportional_size(
        session, user=user, trader=trader, trade=_trade(side="SELL", size=100),
        paper=True, funder="0xme",
    )
    assert size == 20.0


async def test_proportional_falls_back_when_leader_book_unknown(session, monkeypatch):
    user = await repo.get_or_create_user(session, telegram_id=3)
    await repo.set_paper_balance(session, user, 200.0)
    trader = await repo.get_or_create_trader(session, wallet="0xlead")
    monkeypatch.setattr(mirror, "PolymarketDataClient", lambda: _FakeData(pv=0.0))

    size = await _proportional_size(
        session, user=user, trader=trader, trade=_trade(side="BUY", size=100),
        paper=True, funder="0xme",
    )
    assert size is None  # caller falls back to multiplier sizing
