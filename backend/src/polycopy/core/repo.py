"""Data-access layer. Thin async functions over the ORM models so the bot,
API, and workers never hand-roll queries or touch encryption directly.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from polycopy.core import crypto
from polycopy.core.models import (
    CopiedTrade,
    Follow,
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


async def spent_today_usd(session: AsyncSession, user: User) -> float:
    """Sum notional (our_size * our_price) of trades submitted today (UTC)."""
    from sqlalchemy import func

    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    res = await session.execute(
        select(func.coalesce(func.sum(CopiedTrade.our_size * CopiedTrade.our_price), 0.0)).where(
            CopiedTrade.user_id == user.id,
            CopiedTrade.created_at >= start,
            CopiedTrade.status.in_(("submitted", "filled")),
        )
    )
    return float(res.scalar_one() or 0.0)


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
