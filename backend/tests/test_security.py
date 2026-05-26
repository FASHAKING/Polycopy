import hashlib
import hmac
import time

from polycopy.core.security import (
    make_session_token,
    read_session_token,
    verify_telegram_login,
)

BOT_TOKEN = "123456:test-bot-token"


def _sign(data: dict, bot_token: str = BOT_TOKEN) -> dict:
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(bot_token.encode()).digest()
    data = dict(data)
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return data


def test_valid_telegram_login():
    payload = _sign({"id": "42", "username": "alice", "auth_date": str(int(time.time()))})
    assert verify_telegram_login(payload, BOT_TOKEN) is True


def test_tampered_payload_rejected():
    payload = _sign({"id": "42", "auth_date": str(int(time.time()))})
    payload["id"] = "99"  # changed after signing
    assert verify_telegram_login(payload, BOT_TOKEN) is False


def test_wrong_bot_token_rejected():
    payload = _sign({"id": "42", "auth_date": str(int(time.time()))})
    assert verify_telegram_login(payload, "999:other-token") is False


def test_stale_auth_date_rejected():
    payload = _sign({"id": "42", "auth_date": str(int(time.time()) - 100000)})
    assert verify_telegram_login(payload, BOT_TOKEN, max_age=86400) is False


def test_session_token_roundtrip():
    token = make_session_token(777)
    assert read_session_token(token) == 777


def test_session_token_tampered():
    token = make_session_token(777)
    assert read_session_token(token + "x") is None
