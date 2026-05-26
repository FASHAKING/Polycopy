from polycopy.polymarket.data_api import Position
from polycopy.polymarket.stats import compute_stats


def _pos(cash_pnl: float, initial: float, cur_price: float, redeemable: bool = False) -> Position:
    return Position.model_validate(
        {
            "proxyWallet": "0xabc",
            "asset": "1",
            "conditionId": "0x1",
            "size": 100,
            "avgPrice": 0.5,
            "initialValue": initial,
            "currentValue": initial + cash_pnl,
            "cashPnl": cash_pnl,
            "curPrice": cur_price,
            "redeemable": redeemable,
        }
    )


def test_empty():
    s = compute_stats([])
    assert s.win_rate is None
    assert s.trades_count == 0


def test_win_rate_from_resolved():
    # 6 resolved (cur_price at extremes): 4 wins, 2 losses => 0.667
    positions = [
        _pos(10, 100, 1.0),
        _pos(10, 100, 1.0),
        _pos(10, 100, 0.99),
        _pos(10, 100, 0.0),  # win but resolved at 0 (sold/realized)
        _pos(-20, 100, 0.0),
        _pos(-20, 100, 0.01),
    ]
    s = compute_stats(positions, min_sample=5)
    assert s.trades_count == 6
    assert s.win_rate is not None
    assert abs(s.win_rate - 4 / 6) < 1e-6
    assert s.win_rate_pct == 66.7


def test_roi_uses_deployed_capital():
    positions = [_pos(50, 100, 1.0), _pos(-25, 100, 0.0)]
    # too few resolved for min_sample=5, falls back to all (still these 2)
    s = compute_stats(positions, min_sample=5)
    assert s.roi is not None
    assert abs(s.roi - (25 / 200)) < 1e-6
