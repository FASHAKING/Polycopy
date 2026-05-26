from datetime import datetime

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
