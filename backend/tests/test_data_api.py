import httpx
import pytest

from polycopy.polymarket.data_api import PolymarketDataClient

TRADES = [
    {
        "proxyWallet": "0x57b9d4bbb36a57c3137aea7c4f5f6be8a37b05a0",
        "side": "BUY",
        "asset": "98855062429487547496325609727885041281247543035813933331393016389076492928884",
        "conditionId": "0x57714e82df0eb07af2fff7353cbbba540d09038890486ae0469d5bd5e5e9fcce",
        "size": 149.22,
        "price": 0.12,
        "timestamp": 1779784494,
        "title": "Dota 2: Team Falcons vs GLYPH",
        "outcome": "GLYPH",
        "outcomeIndex": 1,
        "name": "gjm84",
        "pseudonym": "Known-Petitioner",
        "transactionHash": "0x8e433de92ea774857d7a02bfd3e559ca9f15a35fab9cc7785833716a0393c8e3",
    }
]

POSITIONS = [
    {
        "proxyWallet": "0x57b9d4bbb36a57c3137aea7c4f5f6be8a37b05a0",
        "asset": "60963372599824472528886795089588813393479967165259128770591929671251170491457",
        "conditionId": "0xdaf38c44d24d6b9ca2c81cb90b5136be77d4a66925fc535190145abb189cfbbe",
        "size": 2238.09,
        "avgPrice": 0.02,
        "initialValue": 44.86,
        "currentValue": 3.35,
        "cashPnl": -41.5,
        "percentPnl": -92.5,
        "realizedPnl": 0,
        "curPrice": 0.0015,
        "redeemable": False,
        "title": "Singapore temp",
        "outcome": "Yes",
        "endDate": "2026-05-26",
    }
]

PROFILES = {
    "profiles": [
        {
            "name": "swisstony",
            "pseudonym": "Frail-Possible",
            "displayUsernamePublic": True,
            "bio": "loincloth chic",
            "proxyWallet": "0x204f72f35326db932158cba6adff0b9a1da95e14",
        },
        {
            "name": "swisstony8",
            "pseudonym": "Jaded-Feed",
            "displayUsernamePublic": True,
            "proxyWallet": "0x19a644960679f35b7adbbc5dc56a2000b1cf5a80",
        },
    ]
}

LEADERBOARD = [
    {
        "proxyWallet": "0x56687bf447db6ffa42ffe2204a05edaa20f55839",
        "amount": 22053933.75,
        "pseudonym": "Theo4",
        "name": "Theo4",
    }
]


async def _client(httpx_mock) -> PolymarketDataClient:
    return PolymarketDataClient(client=httpx.AsyncClient())


async def test_get_trades_for_wallet(httpx_mock):
    httpx_mock.add_response(json=TRADES)
    c = await _client(httpx_mock)
    trades = await c.get_trades_for_wallet("0xabc", limit=1)
    await c.close()
    assert len(trades) == 1
    t = trades[0]
    assert t.wallet == "0x57b9d4bbb36a57c3137aea7c4f5f6be8a37b05a0"
    assert t.side == "BUY"
    assert t.token_id.startswith("98855")
    assert t.name == "gjm84"
    assert t.price == 0.12


async def test_get_positions(httpx_mock):
    httpx_mock.add_response(json=POSITIONS)
    c = await _client(httpx_mock)
    positions = await c.get_positions("0xabc")
    await c.close()
    assert positions[0].cash_pnl == -41.5
    assert positions[0].avg_price == 0.02
    assert positions[0].cur_price == 0.0015


async def test_resolve_username_multiple(httpx_mock):
    httpx_mock.add_response(json=PROFILES)
    c = await _client(httpx_mock)
    matches = await c.resolve_username("swisstony")
    await c.close()
    assert len(matches) == 2
    assert matches[0].wallet == "0x204f72f35326db932158cba6adff0b9a1da95e14"
    assert matches[0].name == "swisstony"


async def test_leaderboard(httpx_mock):
    httpx_mock.add_response(json=LEADERBOARD)
    c = await _client(httpx_mock)
    entries = await c.get_leaderboard(metric="profit", period="month", limit=1)
    await c.close()
    assert entries[0].name == "Theo4"
    assert entries[0].amount == pytest.approx(22053933.75)


async def test_portfolio_value(httpx_mock):
    httpx_mock.add_response(json=[{"user": "0xabc", "value": 772.21}])
    c = await _client(httpx_mock)
    val = await c.get_portfolio_value("0xabc")
    await c.close()
    assert val == pytest.approx(772.21)
