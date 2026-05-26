from types import SimpleNamespace
from unittest.mock import AsyncMock

from polycopy.bot.handlers import wallet as wallet_h
from polycopy.core.wallet import AllowanceStatus


def _update():
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_user=SimpleNamespace(id=1, username="alice"),
    )


def _ctx():
    return SimpleNamespace(args=[], bot=SimpleNamespace())


async def test_approve_requires_wallet(monkeypatch):
    monkeypatch.setattr(wallet_h.repo, "get_user_by_telegram_id", AsyncMock(return_value=None))
    monkeypatch.setattr(wallet_h.repo, "get_credential_meta", AsyncMock(return_value=None))
    monkeypatch.setattr(wallet_h.repo, "get_credential_bundle", AsyncMock(return_value=None))

    upd = _update()
    await wallet_h.cmd_approve(upd, _ctx())
    assert "Set up a wallet" in upd.message.reply_text.call_args.args[0]


async def test_approve_skips_linked(monkeypatch):
    monkeypatch.setattr(wallet_h.repo, "get_user_by_telegram_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_meta",
        AsyncMock(return_value=SimpleNamespace(origin="linked", proxy_address="0x1")),
    )
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_bundle",
        AsyncMock(return_value=SimpleNamespace(private_key="0x" + "1" * 64)),
    )

    upd = _update()
    await wallet_h.cmd_approve(upd, _ctx())
    assert "linked accounts" in upd.message.reply_text.call_args.args[0]


async def test_approve_runs_allowances_for_created(monkeypatch):
    monkeypatch.setattr(wallet_h.repo, "get_user_by_telegram_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_meta",
        AsyncMock(return_value=SimpleNamespace(origin="created", proxy_address="0x1")),
    )
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_bundle",
        AsyncMock(return_value=SimpleNamespace(private_key="0x" + "1" * 64)),
    )
    monkeypatch.setattr(
        wallet_h,
        "ensure_trading_allowances",
        lambda key, rpc: AllowanceStatus(set_count=6, already_ok=0, tx_hashes=["0xabc"]),
    )

    upd = _update()
    await wallet_h.cmd_approve(upd, _ctx())
    msg = upd.message.reply_text.call_args.args[0]
    assert "Approvals set" in msg


async def test_approve_reports_gas_error(monkeypatch):
    monkeypatch.setattr(wallet_h.repo, "get_user_by_telegram_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_meta",
        AsyncMock(return_value=SimpleNamespace(origin="created", proxy_address="0x1")),
    )
    monkeypatch.setattr(
        wallet_h.repo,
        "get_credential_bundle",
        AsyncMock(return_value=SimpleNamespace(private_key="0x" + "1" * 64)),
    )
    monkeypatch.setattr(
        wallet_h,
        "ensure_trading_allowances",
        lambda key, rpc: AllowanceStatus(0, 0, [], error="insufficient funds for gas"),
    )

    upd = _update()
    await wallet_h.cmd_approve(upd, _ctx())
    msg = upd.message.reply_text.call_args.args[0]
    assert "POL for gas" in msg
