"""Data-access layer. Thin async functions over the ORM models so the bot,
API, and workers never hand-roll queries or touch encryption directly.
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import crypto
from polycopy.core.models import (
    AccountSnapshot,
    CopiedTrade,
    Follow,
    PaperPosition,
    PolymarketCredential,
    Trader,
    User,
    WatcherCursor,
)
from polycopy.polymarket.clob import CredBundle

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, username: str | None = None
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, telegram_username=username)
        session.add(user)
        await session.flush()
    elif username and user.telegram_username != username:
        user.telegram_username = username
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return res.scalar_one_or_none()


async def set_email(session: AsyncSession, user: User, email: str) -> None:
    user.email = email.strip().lower()
    await session.flush()


# ---------------------------------------------------------------------------
# Credentials (encrypted at rest)
# ---------------------------------------------------------------------------


async def set_credentials(
    session: AsyncSession,
    user: User,
    *,
    proxy_address: str,
    private_key: str,
    api_key: str,
    api_secret: str,
    api_passphrase: str,
    signature_type: int = 2,
    origin: str = "linked",
) -> PolymarketCredential:
    """Create or replace a user's Polymarket credentials. Secrets are
    Fernet-encrypted before they ever hit the database."""
    res = await session.execute(
        select(PolymarketCredential).where(PolymarketCredential.user_id == user.id)
    )
    cred = res.scalar_one_or_none()
    if cred is None:
        cred = PolymarketCredential(user_id=user.id)
        session.add(cred)

    cred.proxy_address = proxy_address
    cred.api_key = api_key
    cred.api_secret_enc = crypto.encrypt(api_secret)
    cred.api_passphrase_enc = crypto.encrypt(api_passphrase)
    cred.private_key_enc = crypto.encrypt(private_key)
    cred.signature_type = signature_type
    cred.origin = origin
    await session.flush()
    return cred


async def get_credential_meta(session: AsyncSession, user: User) -> PolymarketCredential | None:
    """Fetch the credential row (for non-secret fields like address/origin)."""
    res = await session.execute(
        select(PolymarketCredential).where(PolymarketCredential.user_id == user.id)
    )
    return res.scalar_one_or_none()


async def get_credential_bundle(session: AsyncSession, user: User) -> CredBundle | None:
    """Decrypt a user's credentials into a CredBundle for the CLOB client.
    Returns None if the user hasn't linked an account."""
    res = await session.execute(
        select(PolymarketCredential).where(PolymarketCredential.user_id == user.id)
    )
    cred = res.scalar_one_or_none()
    if cred is None:
        return None
    return CredBundle(
        proxy_address=cred.proxy_address,
        private_key=crypto.decrypt(cred.private_key_enc),
        api_key=cred.api_key,
        api_secret=crypto.decrypt(cred.api_secret_enc),
        api_passphrase=crypto.decrypt(cred.api_passphrase_enc),
        signature_type=cred.signature_type,
    )


async def has_credentials(session: AsyncSession, user: User) -> bool:
    res = await session.execute(
        select(PolymarketCredential.id).where(PolymarketCredential.user_id == user.id)
    )
    return res.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Traders
# ---------------------------------------------------------------------------


async def get_or_create_trader(
    session: AsyncSession, wallet: str, display_name: str | None = None
) -> Trader:
    wallet = wallet.lower()
    res = await session.execute(select(Trader).where(Trader.wallet == wallet))
    trader = res.scalar_one_or_none()
    if trader is None:
        trader = Trader(wallet=wallet, display_name=display_name)
        session.add(trader)
        await session.flush()
    elif display_name and not trader.display_name:
        trader.display_name = display_name
    return trader


async def update_trader_stats(
    session: AsyncSession,
    trader: Trader,
    *,
    win_rate: float | None,
    roi: float | None,
    trades_count: int,
    volume_usd: float,
) -> None:
    trader.win_rate = win_rate
    trader.roi = roi
    trader.trades_count = trades_count
    trader.volume_usd = volume_usd
    trader.last_scored_at = datetime.utcnow()
    await session.flush()


# ---------------------------------------------------------------------------
# Follows
# ---------------------------------------------------------------------------


async def add_follow(
    session: AsyncSession,
    user: User,
    trader: Trader,
    *,
    source: str = "manual",
    size_pct_override: float | None = None,
) -> Follow:
    res = await session.execute(
        select(Follow).where(Follow.user_id == user.id, Follow.trader_id == trader.id)
    )
    follow = res.scalar_one_or_none()
    if follow is None:
        follow = Follow(user_id=user.id, trader_id=trader.id, source=source)
        session.add(follow)
    follow.active = True
    follow.source = source
    if size_pct_override is not None:
        follow.size_pct_override = size_pct_override
    await session.flush()
    return follow


async def deactivate_follow(session: AsyncSession, user: User, trader: Trader) -> bool:
    res = await session.execute(
        select(Follow).where(Follow.user_id == user.id, Follow.trader_id == trader.id)
    )
    follow = res.scalar_one_or_none()
    if follow is None or not follow.active:
        return False
    follow.active = False
    await session.flush()
    return True


async def list_active_follows(session: AsyncSession, user: User) -> list[tuple[Follow, Trader]]:
    res = await session.execute(
        select(Follow, Trader)
        .join(Trader, Follow.trader_id == Trader.id)
        .where(Follow.user_id == user.id, Follow.active.is_(True))
        .order_by(Follow.created_at.desc())
    )
    return [(row[0], row[1]) for row in res.all()]


async def list_followers_of_trader(
    session: AsyncSession, trader: Trader
) -> list[tuple[Follow, User]]:
    """All users actively copying a trader — used by the watcher to fan out."""
    res = await session.execute(
        select(Follow, User)
        .join(User, Follow.user_id == User.id)
        .where(Follow.trader_id == trader.id, Follow.active.is_(True))
    )
    return [(row[0], row[1]) for row in res.all()]


async def list_watched_traders(session: AsyncSession) -> list[Trader]:
    """Distinct traders with at least one active follower (watcher's work list)."""
    res = await session.execute(
        select(Trader)
        .join(Follow, Follow.trader_id == Trader.id)
        .where(Follow.active.is_(True))
        .distinct()
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Copied trades
# ---------------------------------------------------------------------------


async def record_copied_trade(session: AsyncSession, **fields) -> CopiedTrade:
    trade = CopiedTrade(**fields)
    session.add(trade)
    await session.flush()
    return trade


async def spent_today_usd(
    session: AsyncSession, user: User, *, include_paper: bool = False
) -> float:
    """Sum notional (our_size * our_price) of trades that consumed budget today (UTC).

    In paper mode simulated fills (status "paper") spend the daily budget too, so
    pass include_paper=True to count them toward the daily spend cap.
    """
    from sqlalchemy import func

    statuses = ["submitted", "filled"]
    if include_paper:
        statuses.append("paper")
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    res = await session.execute(
        select(func.coalesce(func.sum(CopiedTrade.our_size * CopiedTrade.our_price), 0.0)).where(
            CopiedTrade.user_id == user.id,
            CopiedTrade.created_at >= start,
            CopiedTrade.status.in_(statuses),
        )
    )
    return float(res.scalar_one() or 0.0)


async def list_pending_fills(session: AsyncSession, limit: int = 200) -> list[CopiedTrade]:
    """Submitted/partial trades with an exchange order id awaiting reconciliation."""
    res = await session.execute(
        select(CopiedTrade)
        .where(
            CopiedTrade.status.in_(("submitted", "partial")),
            CopiedTrade.our_order_id.is_not(None),
        )
        .order_by(CopiedTrade.created_at.asc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def list_copied_trades(
    session: AsyncSession, user: User, limit: int = 50
) -> list[CopiedTrade]:
    res = await session.execute(
        select(CopiedTrade)
        .where(CopiedTrade.user_id == user.id)
        .order_by(CopiedTrade.created_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Paper trading (imaginary balance + simulated positions)
# ---------------------------------------------------------------------------

# A tiny share balance below which we treat a position as fully closed.
_PAPER_SHARES_EPS = 1e-6


class PaperFill:
    """Outcome of trying to apply a leader trade to a user's paper account."""

    def __init__(
        self, allowed: bool, *, reason: str | None = None, realized_pnl: float | None = None
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.realized_pnl = realized_pnl


async def set_paper_balance(session: AsyncSession, user: User, amount: float) -> None:
    """Fund (or reset) the paper account: set the baseline + cash and wipe positions."""
    user.paper_starting_balance = amount
    user.paper_balance = amount
    user.paper_funded_at = datetime.utcnow()
    await session.execute(
        delete(PaperPosition).where(PaperPosition.user_id == user.id)
    )
    await session.flush()


async def get_paper_positions(session: AsyncSession, user: User) -> list[PaperPosition]:
    res = await session.execute(
        select(PaperPosition)
        .where(PaperPosition.user_id == user.id, PaperPosition.shares > _PAPER_SHARES_EPS)
        .order_by(PaperPosition.updated_at.desc())
    )
    return list(res.scalars().all())


async def _get_paper_position(
    session: AsyncSession, user: User, token_id: str
) -> PaperPosition | None:
    res = await session.execute(
        select(PaperPosition).where(
            PaperPosition.user_id == user.id, PaperPosition.token_id == token_id
        )
    )
    return res.scalar_one_or_none()


async def apply_paper_fill(
    session: AsyncSession,
    user: User,
    *,
    token_id: str,
    condition_id: str,
    market_question: str | None,
    market_slug: str | None,
    outcome: str,
    side: str,
    size: float,
    price: float,
) -> PaperFill:
    """Debit/credit the imaginary balance and update the simulated position.

    No-op (always allowed) when no starting balance is configured, so paper
    mode keeps working as a pure dry-run until a user funds an account.
    """
    if user.paper_starting_balance <= 0:
        return PaperFill(True)

    pos = await _get_paper_position(session, user, token_id)
    if side.upper() == "BUY":
        cost = size * price
        if cost > user.paper_balance + _PAPER_SHARES_EPS:
            return PaperFill(
                False,
                reason=(
                    f"insufficient paper balance "
                    f"(need ${cost:,.2f}, have ${user.paper_balance:,.2f})"
                ),
            )
        user.paper_balance -= cost
        if pos is None:
            session.add(
                PaperPosition(
                    user_id=user.id,
                    token_id=token_id,
                    condition_id=condition_id,
                    market_question=market_question,
                    market_slug=market_slug,
                    outcome=outcome,
                    shares=size,
                    avg_price=price,
                )
            )
        else:
            total = pos.shares + size
            pos.avg_price = (pos.avg_price * pos.shares + price * size) / total
            pos.shares = total
            pos.updated_at = datetime.utcnow()
        await session.flush()
        return PaperFill(True)

    # SELL: close as much of the held position as we can.
    held = pos.shares if pos else 0.0
    sell = min(size, held)
    if sell <= _PAPER_SHARES_EPS:
        return PaperFill(False, reason="no paper position to close")
    proceeds = sell * price
    realized = sell * (price - pos.avg_price)
    user.paper_balance += proceeds
    pos.shares -= sell
    pos.updated_at = datetime.utcnow()
    if pos.shares <= _PAPER_SHARES_EPS:
        await session.delete(pos)
    await session.flush()
    return PaperFill(True, realized_pnl=round(realized, 2))


async def paper_realized_stats(
    session: AsyncSession, user: User
) -> tuple[float, float | None, int]:
    """(realized_pnl, win_rate, settled_count) over the user's closed paper trades.

    Counts only trades since the account was last funded so a reset starts fresh.
    """
    conditions = [
        CopiedTrade.user_id == user.id,
        CopiedTrade.status == "paper",
        CopiedTrade.pnl_usd.is_not(None),
    ]
    if user.paper_funded_at is not None:
        conditions.append(CopiedTrade.created_at >= user.paper_funded_at)
    res = await session.execute(select(CopiedTrade.pnl_usd).where(*conditions))
    pnls = [float(p) for (p,) in res.all()]
    if not pnls:
        return 0.0, None, 0
    wins = sum(1 for p in pnls if p > 0)
    return round(sum(pnls), 2), wins / len(pnls), len(pnls)


# ---------------------------------------------------------------------------
# Account snapshots (P&L history for the dashboard chart)
# ---------------------------------------------------------------------------


async def record_account_snapshot(
    session: AsyncSession,
    user: User,
    *,
    account: str,
    portfolio_value: float,
    pnl: float,
) -> AccountSnapshot:
    snap = AccountSnapshot(
        user_id=user.id, account=account, portfolio_value=portfolio_value, pnl=pnl
    )
    session.add(snap)
    await session.flush()
    return snap


async def get_account_snapshots(
    session: AsyncSession, user: User, *, account: str, since: datetime
) -> list[AccountSnapshot]:
    res = await session.execute(
        select(AccountSnapshot)
        .where(
            AccountSnapshot.user_id == user.id,
            AccountSnapshot.account == account,
            AccountSnapshot.created_at >= since,
        )
        .order_by(AccountSnapshot.created_at.asc())
    )
    return list(res.scalars().all())


async def paper_pnl_series(
    session: AsyncSession, user: User, *, since: datetime
) -> list[tuple[datetime, float]]:
    """Cumulative realized paper P&L within the window, one point per closed trade."""
    res = await session.execute(
        select(CopiedTrade.created_at, CopiedTrade.pnl_usd)
        .where(
            CopiedTrade.user_id == user.id,
            CopiedTrade.status == "paper",
            CopiedTrade.pnl_usd.is_not(None),
            CopiedTrade.created_at >= since,
        )
        .order_by(CopiedTrade.created_at.asc())
    )
    cumulative = 0.0
    points: list[tuple[datetime, float]] = []
    for created_at, pnl in res.all():
        cumulative += float(pnl)
        points.append((created_at, round(cumulative, 2)))
    return points


# ---------------------------------------------------------------------------
# Watcher cursors
# ---------------------------------------------------------------------------


async def get_cursor(session: AsyncSession, trader_id: int) -> WatcherCursor | None:
    res = await session.execute(
        select(WatcherCursor).where(WatcherCursor.trader_id == trader_id)
    )
    return res.scalar_one_or_none()


async def set_cursor(
    session: AsyncSession,
    trader_id: int,
    *,
    last_trade_ts: datetime | None,
    last_trade_hash: str | None,
) -> WatcherCursor:
    cursor = await get_cursor(session, trader_id)
    if cursor is None:
        cursor = WatcherCursor(trader_id=trader_id)
        session.add(cursor)
    cursor.last_trade_ts = last_trade_ts
    cursor.last_trade_hash = last_trade_hash
    await session.flush()
    return cursor
