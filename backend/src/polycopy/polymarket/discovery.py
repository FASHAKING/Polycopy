"""Find profitable traders who are still actively trading.

The leaderboard ranks by cumulative profit, so it surfaces traders who may have
gone quiet months ago. This module cross-checks each candidate's most recent
trade timestamp and keeps only those active within a recency window.
"""

import asyncio
import time
from dataclasses import dataclass

from polycopy.core.logging import get_logger
from polycopy.polymarket.data_api import LeaderPeriod, PolymarketDataClient

log = get_logger(__name__)


@dataclass
class ActiveTrader:
    wallet: str
    name: str | None
    pseudonym: str | None
    profit_usd: float
    last_trade_ts: int | None
    last_trade_age_days: float | None

    @property
    def is_active(self) -> bool:
        return self.last_trade_age_days is not None


async def _last_trade_ts(client: PolymarketDataClient, wallet: str) -> int | None:
    trades = await client.get_trades_for_wallet(wallet, limit=1)
    return trades[0].timestamp if trades else None


async def find_active_profitable_traders(
    client: PolymarketDataClient,
    *,
    period: LeaderPeriod = "month",
    active_within_days: int = 7,
    min_profit_usd: float = 0.0,
    candidate_limit: int = 100,
    result_limit: int = 25,
    concurrency: int = 10,
) -> list[ActiveTrader]:
    """Return profitable leaderboard traders active within `active_within_days`.

    - `period`: leaderboard profit window to pull candidates from.
    - `active_within_days`: trader must have a trade no older than this.
    - `min_profit_usd`: drop candidates below this cumulative profit.
    - `candidate_limit`: how many leaderboard entries to consider.
    - `result_limit`: cap on returned (active) traders.
    """
    leaders = await client.get_leaderboard(
        metric="profit", period=period, limit=candidate_limit
    )
    candidates = [e for e in leaders if e.amount >= min_profit_usd]

    now = time.time()
    cutoff_secs = active_within_days * 86400
    sem = asyncio.Semaphore(concurrency)

    async def check(entry) -> ActiveTrader:
        async with sem:
            ts = await _last_trade_ts(client, entry.wallet)
        age_days = (now - ts) / 86400 if ts is not None else None
        active = ts is not None and (now - ts) <= cutoff_secs
        return ActiveTrader(
            wallet=entry.wallet,
            name=entry.name,
            pseudonym=entry.pseudonym,
            profit_usd=entry.amount,
            last_trade_ts=ts if active else None,
            last_trade_age_days=round(age_days, 2) if active and age_days is not None else None,
        )

    results = await asyncio.gather(*(check(e) for e in candidates))
    active = [r for r in results if r.is_active]
    active.sort(key=lambda r: r.profit_usd, reverse=True)

    log.info(
        "discovery.active_profitable",
        candidates=len(candidates),
        active=len(active),
        active_within_days=active_within_days,
    )
    return active[:result_limit]
