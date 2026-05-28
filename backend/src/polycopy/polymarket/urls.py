"""Public polymarket.com URLs for linking traders and markets from messages/UI."""

POLYMARKET_WEB = "https://polymarket.com"


def profile_url(wallet: str) -> str:
    return f"{POLYMARKET_WEB}/profile/{wallet}"


def market_url(slug: str | None) -> str | None:
    if not slug:
        return None
    return f"{POLYMARKET_WEB}/event/{slug}"
