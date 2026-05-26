from polycopy.polymarket.data_api import Trade
from polycopy.workers.mirror import decide_mirror


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
