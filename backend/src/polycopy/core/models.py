from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polycopy.core.db import Base


def _now() -> datetime:
    return datetime.utcnow()


class User(Base):
    """A Telegram user of the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Risk knobs (per-user defaults; overridable per follow)
    # "multiplier": copy leader_size * default_size_pct.
    # "proportional": match the leader's % of portfolio against your own.
    sizing_mode: Mapped[str] = mapped_column(String(16), default="multiplier")
    default_size_pct: Mapped[float] = mapped_column(Float, default=1.0)  # multiplier of leader size
    max_slippage_bps: Mapped[int] = mapped_column(BigInteger, default=200)  # 2%
    max_notional_per_trade_usd: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = disabled
    daily_spend_cap_usd: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = disabled
    # Standing-risk caps (BUYs only; 0 = disabled).
    max_open_exposure_usd: Mapped[float] = mapped_column(Float, default=0.0)  # total $ at risk
    max_open_positions: Mapped[int] = mapped_column(BigInteger, default=0)  # concurrent positions
    # Extreme-odds filter: skip BUYs outside [min_price, max_price]. Defaults = off.
    min_price: Mapped[float] = mapped_column(Float, default=0.0)
    max_price: Mapped[float] = mapped_column(Float, default=1.0)
    auto_scout_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-user dry run: simulate copies without placing real orders.
    paper_trading: Mapped[bool] = mapped_column(Boolean, default=False)
    # Imaginary money for the paper account. `paper_starting_balance` is the
    # baseline the user set (0 = not configured -> unlimited, no accounting);
    # `paper_balance` is the running simulated cash.
    paper_starting_balance: Mapped[float] = mapped_column(Float, default=0.0)
    paper_balance: Mapped[float] = mapped_column(Float, default=0.0)
    # When the paper account was last funded/reset; realized stats count only
    # closed trades after this so a reset starts the scoreboard fresh.
    paper_funded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    credentials: Mapped["PolymarketCredential | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    follows: Mapped[list["Follow"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    copied_trades: Mapped[list["CopiedTrade"]] = relationship(back_populates="user")


class PolymarketCredential(Base):
    """User-supplied Polymarket CLOB API credentials. Secrets encrypted at rest."""

    __tablename__ = "polymarket_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    proxy_address: Mapped[str] = mapped_column(String(64))  # the user's Polymarket (funder) address
    api_key: Mapped[str] = mapped_column(String(128))
    api_secret_enc: Mapped[str] = mapped_column(String(512))  # Fernet-encrypted
    api_passphrase_enc: Mapped[str] = mapped_column(String(512))
    # Signing key for the EOA that controls the proxy wallet. Funds never leave the
    # user's own Polymarket account; we only use this to sign their orders. Encrypted
    # at rest with FERNET_KEY. This is the one secret we must hold for non-custodial copy.
    private_key_enc: Mapped[str] = mapped_column(String(512))
    signature_type: Mapped[int] = mapped_column(default=2)  # 0=EOA(created), 1/2=proxy(linked)
    origin: Mapped[str] = mapped_column(String(16), default="linked")  # created | linked
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[User] = relationship(back_populates="credentials")


class Trader(Base):
    """A Polymarket trader being watched/considered for copy."""

    __tablename__ = "traders"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Rolling stats (refreshed by the scout)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    roi: Mapped[float | None] = mapped_column(Float, nullable=True)
    trades_count: Mapped[int] = mapped_column(default=0)
    volume_usd: Mapped[float] = mapped_column(Float, default=0.0)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Follow(Base):
    """A user's choice to copy a specific trader."""

    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("user_id", "trader_id", name="uq_follow_user_trader"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"), index=True)

    size_pct_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_slippage_bps_override: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sizing_mode_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | auto
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[User] = relationship(back_populates="follows")
    trader: Mapped[Trader] = relationship()


class CopiedTrade(Base):
    """A trade mirrored from a leader into a user's account."""

    __tablename__ = "copied_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"), index=True)

    market_id: Mapped[str] = mapped_column(String(128), index=True)
    market_question: Mapped[str | None] = mapped_column(String(512), nullable=True)
    market_slug: Mapped[str | None] = mapped_column(String(256), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))  # YES / NO
    side: Mapped[str] = mapped_column(String(8))  # BUY / SELL

    leader_tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    leader_price: Mapped[float] = mapped_column(Float)
    leader_size: Mapped[float] = mapped_column(Float)

    our_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    our_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    our_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # pending | submitted | filled | rejected | skipped

    skip_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    user: Mapped[User] = relationship(back_populates="copied_trades")
    trader: Mapped[Trader] = relationship()


class PaperPosition(Base):
    """A simulated open position held in a user's paper-trading account."""

    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("user_id", "token_id", name="uq_paper_user_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_id: Mapped[str] = mapped_column(String(128), index=True)
    condition_id: Mapped[str] = mapped_column(String(128))
    market_question: Mapped[str | None] = mapped_column(String(512), nullable=True)
    market_slug: Mapped[str | None] = mapped_column(String(256), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))
    shares: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WatcherCursor(Base):
    """Last-seen trade marker per trader so the watcher doesn't re-process."""

    __tablename__ = "watcher_cursors"

    trader_id: Mapped[int] = mapped_column(ForeignKey("traders.id"), primary_key=True)
    last_trade_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_trade_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
