from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from polycopy.bot.handlers import link
from polycopy.bot.handlers.link import ASK_ADDRESS, ASK_KEY, link_address, link_key

GOOD_ADDR = "0x" + "a" * 40
GOOD_KEY = "b" * 64


def _update(text: str, chat_type: str = "private"):
    msg = SimpleNamespace(
        text=text,
        reply_text=AsyncMock(),
        delete=AsyncMock(),
    )
    return SimpleNamespace(
        message=msg,
        effective_chat=SimpleNamespace(id=999, type=chat_type),
        effective_user=SimpleNamespace(id=42, username="alice"),
    )


def _ctx():
    status_msg = SimpleNamespace(edit_text=AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock(return_value=status_msg))
    return SimpleNamespace(user_data={}, bot=bot)


async def test_link_address_rejects_garbage():
    upd, ctx = _update("not-an-address"), _ctx()
    state = await link_address(upd, ctx)
    assert state == ASK_ADDRESS
    assert "proxy_address" not in ctx.user_data


async def test_link_address_accepts_valid():
    upd, ctx = _update(GOOD_ADDR), _ctx()
    state = await link_address(upd, ctx)
    assert state == ASK_KEY
    assert ctx.user_data["proxy_address"] == GOOD_ADDR


async def test_link_key_deletes_message_and_rejects_bad_key():
    upd, ctx = _update("tooshort"), _ctx()
    ctx.user_data["proxy_address"] = GOOD_ADDR
    state = await link_key(upd, ctx)
    upd.message.delete.assert_awaited_once()  # key scrubbed from chat
    assert state == ASK_KEY


async def test_link_key_success_stores_creds(monkeypatch):
    upd, ctx = _update(GOOD_KEY), _ctx()
    ctx.user_data["proxy_address"] = GOOD_ADDR

    monkeypatch.setattr(link, "derive_api_creds", lambda *a, **k: ("ak", "as", "ap"))

    set_creds = AsyncMock()
    fake_user = SimpleNamespace(id=1)
    monkeypatch.setattr(link.repo, "get_or_create_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(link.repo, "set_credentials", set_creds)

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    monkeypatch.setattr(link, "db_session", fake_session)

    # Avoid real network for the balance readout.
    class FakeData:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_portfolio_value(self, _addr):
            return 123.45

    monkeypatch.setattr(link, "PolymarketDataClient", FakeData)

    from telegram.ext import ConversationHandler

    state = await link_key(upd, ctx)
    assert state == ConversationHandler.END
    set_creds.assert_awaited_once()
    _, kwargs = set_creds.call_args
    assert kwargs["api_key"] == "ak"
    assert kwargs["private_key"] == "0x" + GOOD_KEY
    assert ctx.user_data == {}  # cleared


def test_build_application_requires_token(monkeypatch):
    from polycopy.bot import app as botapp
    from polycopy.core.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(botapp, "get_settings", lambda: Settings(telegram_bot_token=""))
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        botapp.build_application()
