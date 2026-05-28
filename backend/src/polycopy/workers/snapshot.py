"""Record point-in-time account values so the dashboard can chart P&L over time.

Runs on an interval. For every user we snapshot the paper account (if funded)
and the real account (if credentials are linked). The chart reads these back
per account and time range.
"""

from sqlalchemy import select

from polycopy.core import repo
from polycopy.core.db import SessionLocal
from polycopy.core.logging import get_logger
from polycopy.core.models import User
from polycopy.core.portfolio import paper_portfolio, real_portfolio

log = get_logger(__name__)


async def snapshot_once() -> None:
    async with SessionLocal() as session:
        user_ids = list((await session.execute(select(User.id))).scalars().all())

    for user_id in user_ids:
        # One session per user so a single failure is isolated.
        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            if user is None:
                continue
            try:
                if user.paper_starting_balance > 0:
                    pf = await paper_portfolio(session, user)
                    await repo.record_account_snapshot(
                        session, user, account="paper",
                        portfolio_value=pf.portfolio_value, pnl=pf.total_pnl,
                    )
                if await repo.has_credentials(session, user):
                    rp = await real_portfolio(session, user)
                    await repo.record_account_snapshot(
                        session, user, account="real",
                        portfolio_value=rp.portfolio_value,
                        pnl=round(rp.realized_pnl + rp.unrealized_pnl, 2),
                    )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - isolate per-user failures
                await session.rollback()
                log.error("snapshot.user_failed", user=user_id, error=str(exc))
