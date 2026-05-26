"""Per-user CLOB client for placing mirrored orders on Polymarket.

Non-custodial: funds stay in the user's own Polymarket account. We hold only
the signing key (encrypted at rest) and use it to sign the user's orders.
py-clob-client signs orders client-side with that key; the L2 API creds
(key/secret/passphrase) authenticate the HTTP requests.
"""

from dataclasses import dataclass

from polycopy.core.config import get_settings
from polycopy.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class OrderRequest:
    token_id: str
    side: str  # BUY / SELL
    price: float  # limit price, 0..1
    size: float  # number of shares


@dataclass
class OrderResult:
    accepted: bool
    order_id: str | None = None
    status: str | None = None
    error: str | None = None


@dataclass
class CredBundle:
    proxy_address: str
    private_key: str
    api_key: str
    api_secret: str
    api_passphrase: str
    signature_type: int = 2


def clamp_price(price: float, side: str, max_slippage_bps: int) -> float:
    """Apply a slippage buffer so a BUY won't overpay / a SELL won't undersell.

    We post a marketable limit at the leader's price padded by the slippage
    allowance, then clamp into the valid (0, 1) range. Returns a price rounded
    to whole cents (Polymarket's default tick).
    """
    buf = max_slippage_bps / 10_000.0
    adj = price * (1 + buf) if side.upper() == "BUY" else price * (1 - buf)
    adj = min(max(adj, 0.01), 0.99)
    return round(adj, 2)


def derive_api_creds(
    private_key: str, proxy_address: str, signature_type: int = 2
) -> tuple[str, str, str]:
    """Derive L2 API credentials from a signing key via the CLOB API.

    Lets onboarding collect only the proxy address + private key instead of
    five separate secrets. Blocking (py-clob-client is sync); call in a thread
    executor. Returns (api_key, api_secret, api_passphrase).
    """
    from py_clob_client.client import ClobClient as SdkClobClient

    s = get_settings()
    sdk = SdkClobClient(
        host=s.polymarket_clob_api,
        chain_id=s.polygon_chain_id,
        key=private_key,
        signature_type=signature_type,
        funder=proxy_address,
    )
    creds = sdk.create_or_derive_api_creds()
    return creds.api_key, creds.api_secret, creds.api_passphrase


class ClobClient:
    def __init__(self, creds: CredBundle) -> None:
        self._creds = creds
        self._client = None  # lazily constructed; importing the SDK is heavy

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        from py_clob_client.client import ClobClient as SdkClobClient
        from py_clob_client.clob_types import ApiCreds

        s = get_settings()
        self._client = SdkClobClient(
            host=s.polymarket_clob_api,
            chain_id=s.polygon_chain_id,
            key=self._creds.private_key,
            creds=ApiCreds(
                api_key=self._creds.api_key,
                api_secret=self._creds.api_secret,
                api_passphrase=self._creds.api_passphrase,
            ),
            signature_type=self._creds.signature_type,
            funder=self._creds.proxy_address,
        )
        return self._client

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Sign and post a limit order. Blocking (py-clob-client is sync);
        callers run this in a thread executor."""
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY, SELL

        sdk = self._ensure_client()
        side = BUY if order.side.upper() == "BUY" else SELL
        try:
            signed = sdk.create_order(
                OrderArgs(
                    token_id=order.token_id,
                    price=order.price,
                    size=order.size,
                    side=side,
                )
            )
            resp = sdk.post_order(signed)
        except Exception as exc:  # noqa: BLE001 - surface any SDK/network error to caller
            log.warning("clob.place_order_failed", error=str(exc), token=order.token_id)
            return OrderResult(accepted=False, error=str(exc))

        if not isinstance(resp, dict):
            return OrderResult(accepted=False, error=f"unexpected response: {resp!r}")
        order_id = resp.get("orderID") or resp.get("orderId")
        status = resp.get("status")
        success = bool(resp.get("success", order_id is not None))
        return OrderResult(accepted=success, order_id=order_id, status=status)
