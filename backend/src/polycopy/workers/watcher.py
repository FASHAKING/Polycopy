"""Poll watched traders for new trades and mirror them to their followers.

First observation of a trader only sets a watermark (we never back-fill
historical trades). Subsequent ticks copy trades newer than the cursor.
"""

from datetime import datetime

from polycopy.core import repo
from polycopy.core.db import SessionLocal
from polycopy.core.logging import get_logger
from polycopy.core.models import Trader, User
from polycopy.polymarket.data_api import PolymarketDataClient, Trade
from polycopy.workers.mirror import execute_mirror

log = get_logger(__name__)


def new_trades_since(
    trades: list[Trade], last_ts: datetime | None, last_hash: str | None
) -> list[Trade]:
    """Return trades newer than the cursor, oldest-first, ready to process.

    Trades arrive newest-first. We collect until we hit the known hash; as a
    guard against a stale/missing hash we also bound by timestamp.
    """
    if last_ts is None:
        return []
    cutoff = int(last_ts.timestamp())
    fresh: list[Trade] = []
    for t in trades:
        if last_hash and t.tx_hash == last_hash:
            break
        if t.timestamp < cutoff:
            break
        fresh.append(t)
    fresh.reverse()  # oldest-first preserves execution order
    return fresh


async def _process_trader(data: PolymarketDataClient, trader_id: int, wallet: str) -> None:
    trades = await data.get_trades_for_wallet(wallet, limit=50)
    if not trades:
        return
    newest = trades[0]

    async with SessionLocal() as session:
        cursor = await repo.get_cursor(session, trader_id)

        if cursor is None or cursor.last_trade_ts is None:
            # First time we see this trader: set the watermark, copy nothing.
            await repo.set_cursor(
                session,
                trader_id,
                last_trade_ts=datetime.utcfromtimestamp(newest.timestamp),
                last_trade_hash=newest.tx_hash,
            )
            await session.commit()
            log.info("watcher.watermark_set", trader=wallet)
            return

        fresh = new_trades_since(trades, cursor.last_trade_ts, cursor.last_trade_hash)
        # Advance the cursor up front so a mid-loop crash can't replay trades.
        await repo.set_cursor(
            session,
            trader_id,
            last_trade_ts=datetime.utcfromtimestamp(newest.timestamp),
            last_trade_hash=newest.tx_hash,
        )
        await session.commit()

    if not fresh:
        return
    log.info("watcher.new_trades", trader=wallet, count=len(fresh))

    for trade in fresh:
        await _fan_out(trade, trader_id)


async def _fan_out(trade: Trade, trader_id: int) -> None:
    async with SessionLocal() as session:
        trader = await session.get(Trader, trader_id)
        followers = await repo.list_followers_of_trader(session, trader)

    for follow, detached_user in followers:
        # One session per follower so a single failure is isolated.
        async with SessionLocal() as session:
            # Re-load the user into this session so mutations (e.g. paper
            # balance debits/credits) are tracked and committed; the object
            # from the fan-out session above is detached here.
            user = await session.get(User, detached_user.id)
            if user is None:
                continue
            creds = await repo.get_credential_bundle(session, user)
            if creds is None:
                continue
            trader = await session.get(Trader, trader_id)
            try:
                await execute_mirror(
                    session,
                    user=user,
                    trader=trader,
                    follow=follow,
                    trade=trade,
                    creds=creds,
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - isolate per-follower failures
                await session.rollback()
                log.error("watcher.mirror_failed", user=user.id, error=str(exc))


async def watch_once() -> None:
    async with SessionLocal() as session:
        traders = await repo.list_watched_traders(session)
    if not traders:
        return
    targets = [(t.id, t.wallet) for t in traders]

    async with PolymarketDataClient() as data:
        for trader_id, wallet in targets:
            try:
                await _process_trader(data, trader_id, wallet)
            except Exception as exc:  # noqa: BLE001 - one bad trader shouldn't stop the rest
                log.error("watcher.trader_failed", wallet=wallet, error=str(exc))
