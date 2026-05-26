from polycopy.polymarket.clob import CredBundle, OrderRequest, clamp_price


def test_clamp_buy_pads_up_and_rounds():
    # BUY at 0.50 with 2% slippage -> 0.51
    assert clamp_price(0.50, "BUY", 200) == 0.51


def test_clamp_sell_pads_down():
    assert clamp_price(0.50, "SELL", 200) == 0.49


def test_clamp_stays_in_range():
    assert clamp_price(0.995, "BUY", 500) == 0.99
    assert clamp_price(0.005, "SELL", 500) == 0.01


def test_clob_client_lazy_no_network():
    # Constructing the client must not touch the network or import the SDK eagerly.
    c = ClobClientImportGuard()
    assert c is not None


class ClobClientImportGuard:
    """Building a ClobClient should be cheap and side-effect free."""

    def __init__(self):
        from polycopy.polymarket.clob import ClobClient

        self.inner = ClobClient(
            CredBundle(
                proxy_address="0xabc",
                private_key="0x" + "1" * 64,
                api_key="k",
                api_secret="s",
                api_passphrase="p",
            )
        )
        assert self.inner._client is None
        # Build a request object; no order is placed.
        self.req = OrderRequest(token_id="1", side="BUY", price=0.5, size=10)
