from datetime import datetime

from pydantic import BaseModel


class StatsOut(BaseModel):
    users: int
    traders_tracked: int
    active_follows: int
    copied_trades: int
    submitted: int
    filled: int
    skipped: int


class TraderOut(BaseModel):
    wallet: str
    display_name: str | None
    win_rate: float | None
    roi: float | None
    trades_count: int
    volume_usd: float
    last_scored_at: datetime | None


class FollowOut(BaseModel):
    wallet: str
    display_name: str | None
    source: str
    win_rate: float | None
    created_at: datetime


class CopiedTradeOut(BaseModel):
    market_question: str | None
    market_slug: str | None
    outcome: str
    side: str
    leader_price: float
    leader_size: float
    our_price: float | None
    our_size: float | None
    status: str
    skip_reason: str | None
    pnl_usd: float | None
    created_at: datetime


class MeOut(BaseModel):
    telegram_id: int
    telegram_username: str | None
    email: str | None
    auto_scout_enabled: bool
    paper_trading: bool
    paper_starting_balance: float
    paper_balance: float
    linked: bool
    wallet_origin: str | None
    wallet_address: str | None


class SettingsIn(BaseModel):
    """Partial update of a user's settings from the web dashboard."""

    paper_trading: bool | None = None
    paper_balance: float | None = None  # funds/resets the paper account
    auto_scout_enabled: bool | None = None
    notifications_enabled: bool | None = None
    sizing_mode: str | None = None
    default_size_pct: float | None = None
    max_slippage_bps: int | None = None
    max_notional_per_trade_usd: float | None = None
    daily_spend_cap_usd: float | None = None


class PaperPositionOut(BaseModel):
    market_question: str | None
    market_slug: str | None
    outcome: str
    shares: float
    avg_price: float
    cur_price: float
    value: float
    unrealized_pnl: float


class PaperPortfolioOut(BaseModel):
    enabled: bool
    starting_balance: float
    cash: float
    market_value: float
    portfolio_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    open_positions: int
    win_rate: float | None
    settled_markets: int
    positions: list[PaperPositionOut]


class TelegramLoginIn(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TokenOut(BaseModel):
    token: str
    telegram_id: int


class PnlOut(BaseModel):
    wallet_address: str | None
    portfolio_value: float
    unrealized_pnl: float
    realized_pnl: float
    win_rate: float | None
    settled_markets: int
    open_positions: int
    # copied-trade execution summary
    trades_filled: int
    trades_submitted: int
    trades_skipped: int
    trades_paper: int
