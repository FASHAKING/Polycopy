from polycopy.polymarket.data_api import Activity
from polycopy.polymarket.stats import compute_realized_stats


def _act(cond, type_, side=None, size=0.0, usdc=0.0, outcome=0) -> Activity:
    return Activity.model_validate(
        {
            "proxyWallet": "0xw",
            "timestamp": 1,
            "type": type_,
            "conditionId": cond,
            "side": side or "",
            "size": size,
            "usdcSize": usdc,
            "outcomeIndex": outcome,
        }
    )


def test_no_settled_markets_returns_none():
    # Open position: bought, never sold/redeemed -> excluded.
    acts = [_act("c1", "TRADE", "BUY", size=100, usdc=50)]
    s = compute_realized_stats(acts)
    assert s.win_rate is None
    assert s.trades_count == 0


def test_redeemed_winner_counts_as_win():
    # Bought $50, redeemed $100 -> win.
    acts = [
        _act("c1", "TRADE", "BUY", size=100, usdc=50),
        _act("c1", "REDEEM", usdc=100),
    ]
    s = compute_realized_stats(acts)
    assert s.trades_count == 1
    assert s.win_rate == 1.0
    assert s.roi == 1.0  # net +50 on 50 deployed


def test_losing_market_via_full_exit():
    # Bought $50 (100 sh), sold all for $20 -> net -30, fully exited -> loss.
    acts = [
        _act("c2", "TRADE", "BUY", size=100, usdc=50),
        _act("c2", "TRADE", "SELL", size=100, usdc=20),
    ]
    s = compute_realized_stats(acts)
    assert s.trades_count == 1
    assert s.win_rate == 0.0


def test_mixed_winrate():
    acts = [
        # winner
        _act("w", "TRADE", "BUY", size=100, usdc=40),
        _act("w", "REDEEM", usdc=100),
        # loser (resolved worthless, redeem 0)
        _act("l", "TRADE", "BUY", size=100, usdc=60),
        _act("l", "REDEEM", usdc=0),
        # still open -> excluded
        _act("o", "TRADE", "BUY", size=100, usdc=50),
    ]
    s = compute_realized_stats(acts)
    assert s.trades_count == 2
    assert s.win_rate == 0.5
