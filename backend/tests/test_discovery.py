import time

import httpx

from polycopy.polymarket.data_api import PolymarketDataClient
from polycopy.polymarket.discovery import find_active_profitable_traders

NOW = int(time.time())
RECENT = NOW - 2 * 86400  # 2 days ago -> active
STALE = NOW - 30 * 86400  # 30 days ago -> inactive

LEADERS = [
    {"proxyWallet": "0xactive", "amount": 5000.0, "name": "Live", "pseudonym": "Live"},
    {"proxyWallet": "0xstale", "amount": 9000.0, "name": "Quiet", "pseudonym": "Quiet"},
    {"proxyWallet": "0xpoor", "amount": 10.0, "name": "Small", "pseudonym": "Small"},
]


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/profit"):
        return httpx.Response(200, json=LEADERS)
    if path.endswith("/trades"):
        wallet = request.url.params.get("user")
        ts = {"0xactive": RECENT, "0xstale": STALE, "0xpoor": RECENT}.get(wallet)
        trade = [
            {
                "proxyWallet": wallet,
                "side": "BUY",
                "asset": "1",
                "conditionId": "0x1",
                "size": 1.0,
                "price": 0.5,
                "timestamp": ts,
            }
        ]
        return httpx.Response(200, json=trade)
    return httpx.Response(404)


async def test_filters_to_active_and_profitable(httpx_mock):
    httpx_mock.add_callback(_handler, is_reusable=True)
    c = PolymarketDataClient(client=httpx.AsyncClient())
    results = await find_active_profitable_traders(
        c, active_within_days=7, min_profit_usd=100.0
    )
    await c.close()

    wallets = [r.wallet for r in results]
    # 0xstale dropped (inactive), 0xpoor dropped (below min profit)
    assert wallets == ["0xactive"]
    assert results[0].last_trade_age_days is not None
    assert results[0].last_trade_age_days <= 7
