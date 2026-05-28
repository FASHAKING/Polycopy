"""Reconcile submitted orders against the exchange to record actual fills.

Orders are posted as marketable limits and recorded as `submitted`. This job
polls each pending order's status via the user's CLOB client and advances it to
`filled` / `partial` / `canceled`, recording the matched size and fill price.
"""

import asyncio
from collections import defaultdict

from polycopy.core import repo
from polycopy.core.db import SessionLocal
from polycopy.core.logging import get_logger
from polycopy.core.models import CopiedTrade, User
from polycopy.polymarket.clob import ClobClient

log = get_logger(__name__)


async def reconcile_once() -> None:
    async with SessionLocal() as session:
        pending = await repo.list_pending_fills(session)
    if not pending:
        return

    by_user: dict[int, list[CopiedTrade]] = defaultdict(list)
    for t in pending:
        by_user[t.user_id].append(t)

    for user_id, trades in by_user.items():
        await _reconcile_user(user_id, trades)


async def _reconcile_user(user_id: int, trades: list[CopiedTrade]) -> None:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        creds = await repo.get_credential_bundle(session, user) if user else None
    if creds is None:
        return

    client = ClobClient(creds)
    for trade in trades:
        try:
            status = await asyncio.to_thread(client.get_order_status, trade.our_order_id)
        except Exception as exc:  # noqa: BLE001 - isolate per-order failures
            log.error("reconcile.failed", trade=trade.id, error=str(exc))
            continue

        resolved = status.resolved
        if resolved == "submitted":
            continue  # still open; check again next tick

        async with SessionLocal() as session:
            row = await session.get(CopiedTrade, trade.id)
            if row is None:
                continue
            row.status = resolved
            if status.size_matched > 0:
                row.our_size = round(status.size_matched, 2)
            if status.price:
                row.our_price = status.price
            await session.commit()
            notify = (
                resolved == "filled"
                and user is not None
                and getattr(user, "notifications_enabled", True)
            )
            fill_size, fill_price, question = row.our_size, row.our_price, row.market_question
            market_slug = row.market_slug
        log.info("reconcile.updated", trade=trade.id, status=resolved)

        if notify:
            from polycopy.core.notify import notify_user
            from polycopy.polymarket.urls import market_url

            label = (question or "your copied trade").strip()
            murl = market_url(market_slug)
            market_md = f"[{label}]({murl})" if murl else f"_{label}_"
            await notify_user(
                user.telegram_id,
                f"✅ *Filled*: {fill_size:g} shares @ ${fill_price:.2f}\n{market_md}",
            )
