"""Async client for Polymarket's public Data, Gamma, and Leaderboard APIs.

All endpoints here are public and unauthenticated. Response shapes were captured
from the live APIs (May 2026); see tests/fixtures for recorded samples.
"""

from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from polycopy.core.config import get_settings
from polycopy.core.logging import get_logger

log = get_logger(__name__)

LeaderMetric = Literal["profit", "volume"]
LeaderPeriod = Literal["day", "week", "month", "all"]


class Trade(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wallet: str = Field(alias="proxyWallet")
    side: str  # BUY / SELL
    token_id: str = Field(alias="asset")
    condition_id: str = Field(alias="conditionId")
    size: float
    price: float
    timestamp: int
    title: str | None = None
    slug: str | None = None
    event_slug: str | None = Field(default=None, alias="eventSlug")
    outcome: str | None = None
    outcome_index: int | None = Field(default=None, alias="outcomeIndex")
    name: str | None = None
    pseudonym: str | None = None
    tx_hash: str | None = Field(default=None, alias="transactionHash")


class Position(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wallet: str = Field(alias="proxyWallet")
    token_id: str = Field(alias="asset")
    condition_id: str = Field(alias="conditionId")
    size: float
    avg_price: float = Field(alias="avgPrice")
    initial_value: float = Field(default=0.0, alias="initialValue")
    current_value: float = Field(default=0.0, alias="currentValue")
    cash_pnl: float = Field(default=0.0, alias="cashPnl")
    percent_pnl: float = Field(default=0.0, alias="percentPnl")
    realized_pnl: float = Field(default=0.0, alias="realizedPnl")
    cur_price: float = Field(default=0.0, alias="curPrice")
    redeemable: bool = False
    title: str | None = None
    outcome: str | None = None
    end_date: str | None = Field(default=None, alias="endDate")


class Activity(BaseModel):
    """An account activity event: TRADE, REDEEM, SPLIT, MERGE, etc.

    REDEEM events carry the USDC realized when a resolved position is claimed —
    the basis for historical win/loss accounting (used by the scout in Phase 6).
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wallet: str = Field(alias="proxyWallet")
    timestamp: int
    type: str
    condition_id: str = Field(alias="conditionId")
    size: float = 0.0
    usdc_size: float = Field(default=0.0, alias="usdcSize")
    price: float = 0.0
    side: str | None = None
    outcome_index: int | None = Field(default=None, alias="outcomeIndex")
    title: str | None = None
    tx_hash: str | None = Field(default=None, alias="transactionHash")


class LeaderEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wallet: str = Field(alias="proxyWallet")
    amount: float  # profit or volume in USD depending on metric queried
    name: str | None = None
    pseudonym: str | None = None


class ProfileMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wallet: str = Field(alias="proxyWallet")
    name: str | None = None
    pseudonym: str | None = None
    bio: str | None = None
    username_public: bool = Field(default=False, alias="displayUsernamePublic")


_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class PolymarketDataClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._data = s.polymarket_data_api.rstrip("/")
        self._gamma = s.polymarket_gamma_api.rstrip("/")
        self._lb = s.polymarket_lb_api.rstrip("/")
        self._clob = s.polymarket_clob_api.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=15.0, headers={"User-Agent": "polycopy/0.1"}
        )

    async def __aenter__(self) -> "PolymarketDataClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._client.get(url, params=params)
        # Retry on 5xx / 429; surface 4xx immediately.
        if resp.status_code >= 500 or resp.status_code == 429:
            resp.raise_for_status()
        if resp.status_code >= 400:
            log.warning("polymarket.http_error", url=url, status=resp.status_code)
            return None
        return resp.json()

    async def get_trades_for_wallet(self, wallet: str, limit: int = 50) -> list[Trade]:
        data = await self._get(
            f"{self._data}/trades", {"user": wallet, "limit": limit}
        )
        return [Trade.model_validate(t) for t in (data or [])]

    async def get_recent_trades(self, limit: int = 100) -> list[Trade]:
        data = await self._get(f"{self._data}/trades", {"limit": limit})
        return [Trade.model_validate(t) for t in (data or [])]

    async def get_positions(self, wallet: str, limit: int = 500) -> list[Position]:
        data = await self._get(
            f"{self._data}/positions", {"user": wallet, "limit": limit}
        )
        return [Position.model_validate(p) for p in (data or [])]

    async def get_activity(
        self,
        wallet: str,
        limit: int = 200,
        activity_type: str | None = None,
        offset: int = 0,
    ) -> list[Activity]:
        params: dict[str, Any] = {"user": wallet, "limit": limit}
        if offset:
            params["offset"] = offset
        if activity_type:
            params["type"] = activity_type
        data = await self._get(f"{self._data}/activity", params)
        return [Activity.model_validate(a) for a in (data or [])]

    async def get_activity_paged(
        self, wallet: str, max_events: int = 3000, page_size: int = 500
    ) -> list[Activity]:
        """Page through a wallet's activity up to `max_events` (newest-first)."""
        out: list[Activity] = []
        offset = 0
        while len(out) < max_events:
            batch = await self.get_activity(wallet, limit=page_size, offset=offset)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return out[:max_events]

    async def get_midpoint(self, token_id: str) -> float | None:
        """Current mid price (0..1) for an outcome token via the public CLOB API."""
        data = await self._get(f"{self._clob}/midpoint", {"token_id": token_id})
        if isinstance(data, dict) and data.get("mid") is not None:
            try:
                return float(data["mid"])
            except (TypeError, ValueError):
                return None
        return None

    async def get_prices(self, token_ids: list[str]) -> dict[str, float]:
        """Fetch mid prices for several tokens concurrently; skips any that fail."""
        import asyncio

        unique = list(dict.fromkeys(token_ids))
        results = await asyncio.gather(*(self.get_midpoint(t) for t in unique))
        return {t: p for t, p in zip(unique, results, strict=True) if p is not None}

    async def get_portfolio_value(self, wallet: str) -> float:
        data = await self._get(f"{self._data}/value", {"user": wallet})
        if isinstance(data, list) and data:
            return float(data[0].get("value", 0.0))
        return 0.0

    async def get_leaderboard(
        self, metric: LeaderMetric = "profit", period: LeaderPeriod = "month", limit: int = 100
    ) -> list[LeaderEntry]:
        # The profit endpoint keys on `period`; the volume endpoint keys on `window`.
        param = "period" if metric == "profit" else "window"
        value = period if metric == "profit" else ("all" if period == "all" else period)
        data = await self._get(f"{self._lb}/{metric}", {param: value, "limit": limit})
        return [LeaderEntry.model_validate(e) for e in (data or [])]

    async def resolve_username(self, name: str, limit: int = 5) -> list[ProfileMatch]:
        """Return profile matches for a display name (may be more than one)."""
        data = await self._get(
            f"{self._gamma}/public-search",
            {"q": name, "search_profiles": "true", "limit_per_type": limit},
        )
        profiles = (data or {}).get("profiles", []) if isinstance(data, dict) else []
        return [ProfileMatch.model_validate(p) for p in profiles]
