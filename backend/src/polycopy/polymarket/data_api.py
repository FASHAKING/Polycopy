"""Thin async client for Polymarket's public Data + Gamma APIs.

Phase 2 will flesh these out with real endpoints, retries, and typed responses.
This stub exists so the package imports cleanly and tests can monkey-patch it.
"""

from typing import Any

import httpx

from polycopy.core.config import get_settings


class PolymarketDataClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._data_base = settings.polymarket_data_api.rstrip("/")
        self._gamma_base = settings.polymarket_gamma_api.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_trades_for_wallet(
        self, wallet: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Recent trades by a wallet. Endpoint shape finalized in Phase 2."""
        raise NotImplementedError("Phase 2")

    async def get_leaderboard(self, window: str = "30d") -> list[dict[str, Any]]:
        """Top traders over a window. Endpoint shape finalized in Phase 2."""
        raise NotImplementedError("Phase 2")

    async def resolve_username(self, name: str) -> str | None:
        """Map a Polymarket display name to a wallet. Phase 2."""
        raise NotImplementedError("Phase 2")
