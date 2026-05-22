"""Wrapper around py-clob-client for placing orders on behalf of a user.

Built out in Phase 2. Kept as a stub here so Phase 1 imports cleanly.
"""

from dataclasses import dataclass


@dataclass
class OrderRequest:
    market_id: str
    outcome: str  # YES / NO
    side: str  # BUY / SELL
    price: float
    size: float


@dataclass
class OrderResult:
    order_id: str | None
    accepted: bool
    error: str | None = None


class ClobClient:
    """Per-user CLOB client. Phase 2 wires up py-clob-client + creds."""

    def __init__(self, proxy_address: str, api_key: str, api_secret: str, api_passphrase: str):
        self.proxy_address = proxy_address
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError("Phase 2")
