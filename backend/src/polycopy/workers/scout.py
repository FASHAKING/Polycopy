"""Auto-scout: find profitable, active traders whose realized win rate sits in a
target band, persist their stats, and (for opted-in users) manage auto-follows.

Win rate must come from resolved history (activity feed), not open positions.
Traders too active to accumulate enough settled markets within the fetch cap are
excluded — we never auto-follow a trader whose win rate we can't verify.
"""

import asyncio
from dataclasses import dataclass

from polycopy.core import repo
from polycopy.core.db import SessionLocal
from polycopy.core.logging import get_logger
from polycopy.core.models import User
from polycopy.polymarket.data_api import LeaderPeriod, PolymarketDataClient
from polycopy.polymarket.discovery import find_active_profitable_traders
from polycopy.polymarket.stats import TraderStats, compute_realized_stats

log = get_logger(__name__)


@dataclass
class ScoutConfig:
    min_win_rate: float = 0.60
    max_win_rate: float = 0.80
    min_settled: int = 20  # require this many resolved markets to trust the rate
    min_roi: float = 0.0  # net-positive realized ROI
    active_within_days: int = 7
    leaderboard_period: LeaderPeriod = "month"
    candidate_limit: int = 60
    max_activity_events: int = 3000
    max_auto_follows: int = 5  # per opted-in user
    concurrency: int = 5


@dataclass
class ScoredTrader:
    wallet: str
    name: str | None
    profit_usd: float
    stats: TraderStats


async def _score_trader(
    data: PolymarketDataClient, wallet: str, max_events: int
) -> TraderStats:
    activities = await data.get_activity_paged(wallet, max_events=max_events)
    return compute_realized_stats(activities)


async def find_band_traders(
    data: PolymarketDataClient, cfg: ScoutConfig
) -> list[ScoredTrader]:
    """Return active, profitable traders whose realized win rate is in band."""
    active = await find_active_profitable_traders(
        data,
        period=cfg.leaderboard_period,
        active_within_days=cfg.active_within_days,
        candidate_limit=cfg.candidate_limit,
        result_limit=cfg.candidate_limit,
    )

    sem = asyncio.Semaphore(cfg.concurrency)

    async def score(entry) -> ScoredTrader:
        async with sem:
            stats = await _score_trader(data, entry.wallet, cfg.max_activity_events)
        return ScoredTrader(
            wallet=entry.wallet, name=entry.name, profit_usd=entry.profit_usd, stats=stats
        )

    scored = await asyncio.gather(*(score(e) for e in active))

    qualified = [
        s
        for s in scored
        if s.stats.win_rate is not None
        and s.stats.trades_count >= cfg.min_settled
        and cfg.min_win_rate <= s.stats.win_rate <= cfg.max_win_rate
        and (s.stats.roi is None or s.stats.roi >= cfg.min_roi)
    ]
    qualified.sort(key=lambda s: (s.stats.win_rate or 0, s.profit_usd), reverse=True)

    log.info(
        "scout.band",
        scored=len(scored),
        qualified=len(qualified),
        band=f"{cfg.min_win_rate:.0%}-{cfg.max_win_rate:.0%}",
    )
    return qualified


async def _persist_and_autofollow(scored: list[ScoredTrader], cfg: ScoutConfig) -> None:
    async with SessionLocal() as session:
        # Persist trader stats for the dashboard.
        traders = []
        for s in scored:
            trader = await repo.get_or_create_trader(
                session, wallet=s.wallet, display_name=s.name
            )
            await repo.update_trader_stats(
                session,
                trader,
                win_rate=s.stats.win_rate,
                roi=s.stats.roi,
                trades_count=s.stats.trades_count,
                volume_usd=s.stats.volume_usd,
            )
            traders.append(trader)
        await session.commit()

        # Auto-follow for opted-in users.
        from sqlalchemy import select

        res = await session.execute(select(User).where(User.auto_scout_enabled.is_(True)))
        users = list(res.scalars().all())

        for user in users:
            if not await repo.has_credentials(session, user):
                continue
            current = await repo.list_active_follows(session, user)
            auto_count = sum(1 for f, _ in current if f.source == "auto")
            followed_ids = {t.id for _, t in current}
            for trader in traders:
                if auto_count >= cfg.max_auto_follows:
                    break
                if trader.id in followed_ids:
                    continue
                await repo.add_follow(session, user, trader, source="auto")
                auto_count += 1
        await session.commit()


async def scout_once(cfg: ScoutConfig | None = None) -> list[ScoredTrader]:
    cfg = cfg or ScoutConfig()
    async with PolymarketDataClient() as data:
        scored = await find_band_traders(data, cfg)
    if scored:
        await _persist_and_autofollow(scored, cfg)
    return scored
