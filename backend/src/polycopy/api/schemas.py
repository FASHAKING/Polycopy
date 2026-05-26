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
    auto_scout_enabled: bool
    linked: bool


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
