from eth_account import Account

from polycopy.core import repo
from polycopy.core.wallet import generate_wallet


def test_generate_wallet_valid_keypair():
    w = generate_wallet()
    assert w.address.startswith("0x") and len(w.address) == 42
    assert w.private_key.startswith("0x") and len(w.private_key) == 66
    # The key must actually control the address.
    assert Account.from_key(w.private_key).address == w.address


def test_generate_wallet_unique():
    assert generate_wallet().address != generate_wallet().address


async def test_custodial_credentials_stored(session):
    user = await repo.get_or_create_user(session, telegram_id=1)
    w = generate_wallet()
    await repo.set_credentials(
        session,
        user,
        proxy_address=w.address,
        private_key=w.private_key,
        api_key="k",
        api_secret="s",
        api_passphrase="p",
        signature_type=0,
        origin="created",
    )
    cred = await repo.get_credential_meta(session, user)
    assert cred.origin == "created"
    assert cred.signature_type == 0
    assert cred.proxy_address == w.address

    bundle = await repo.get_credential_bundle(session, user)
    assert bundle.private_key == w.private_key
    assert bundle.signature_type == 0


async def test_set_email_normalizes_and_persists(session):
    user = await repo.get_or_create_user(session, telegram_id=2)
    await repo.set_email(session, user, "  USER@Example.COM ")
    assert user.email == "user@example.com"
