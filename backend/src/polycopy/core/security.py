"""Telegram login-widget verification and signed session tokens."""

import hashlib
import hmac
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer

from polycopy.core.config import get_settings

_SESSION_SALT = "polycopy.session"
_SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def verify_telegram_login(data: dict[str, str], bot_token: str, max_age: int = 86400) -> bool:
    """Validate a Telegram Login Widget payload.

    Per Telegram's spec: the secret key is SHA256(bot_token); the check string
    is every field except `hash`, sorted by key as `k=v` joined by newlines;
    the HMAC-SHA256 of that must equal `hash`. We also reject stale auth_date.
    """
    received_hash = data.get("hash")
    if not received_hash or not bot_token:
        return False

    check_string = "\n".join(
        f"{k}={data[k]}" for k in sorted(data) if k != "hash"
    )
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return False

    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        return False
    return (time.time() - auth_date) <= max_age


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().app_secret, salt=_SESSION_SALT)


def make_session_token(telegram_id: int) -> str:
    return _serializer().dumps({"tg": telegram_id})


def read_session_token(token: str, max_age: int = _SESSION_MAX_AGE) -> int | None:
    try:
        data = _serializer().loads(token, max_age=max_age)
    except BadSignature:
        return None
    tg = data.get("tg")
    return int(tg) if tg is not None else None
