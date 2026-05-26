"""Custodial wallet generation and Polymarket trading approvals.

The bot can create a fresh Polygon EOA for a user (custodial: we hold the key,
encrypted). The user deposits USDC.e to the address; before the account can
trade, the on-chain allowances below must be set, which costs POL (gas).

generate_wallet has no network/gas dependency and is fully tested. The
allowance helpers touch Polygon and need a funded wallet, so they're isolated
here and must be verified live before real deposits flow through created
wallets.
"""

from dataclasses import dataclass

from eth_account import Account

# Polymarket contracts on Polygon mainnet.
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

_SPENDERS = (CTF_EXCHANGE, NEG_RISK_EXCHANGE, NEG_RISK_ADAPTER)
_MAX_UINT = 2**256 - 1

_ERC20_ABI = [
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

_CTF_ABI = [
    {
        "name": "setApprovalForAll",
        "type": "function",
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "isApprovedForAll",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
]


@dataclass
class GeneratedWallet:
    address: str
    private_key: str  # 0x-prefixed hex


def generate_wallet() -> GeneratedWallet:
    """Create a brand-new Polygon EOA. Pure local crypto, no network."""
    acct = Account.create()
    key = acct.key.hex()
    if not key.startswith("0x"):
        key = "0x" + key
    return GeneratedWallet(address=acct.address, private_key=key)


@dataclass
class AllowanceStatus:
    set_count: int
    already_ok: int
    tx_hashes: list[str]
    error: str | None = None


def ensure_trading_allowances(private_key: str, rpc_url: str) -> AllowanceStatus:
    """Set the USDC + CTF approvals Polymarket needs, skipping any already set.

    Requires POL (gas) in the wallet. Unverified end-to-end — must be tested on
    Polygon with a funded wallet before created wallets handle real deposits.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    acct = Account.from_key(private_key)
    owner = acct.address

    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_E), abi=_ERC20_ABI)
    ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF), abi=_CTF_ABI)

    tx_hashes: list[str] = []
    set_count = already_ok = 0
    try:
        nonce = w3.eth.get_transaction_count(owner)
        gas_price = w3.eth.gas_price
        for spender in _SPENDERS:
            spender_cs = Web3.to_checksum_address(spender)
            if usdc.functions.allowance(owner, spender_cs).call() >= _MAX_UINT // 2:
                already_ok += 1
            else:
                tx = usdc.functions.approve(spender_cs, _MAX_UINT).build_transaction(
                    {"from": owner, "nonce": nonce, "gasPrice": gas_price}
                )
                signed = acct.sign_transaction(tx)
                tx_hashes.append(w3.eth.send_raw_transaction(signed.raw_transaction).hex())
                nonce += 1
                set_count += 1

            if ctf.functions.isApprovedForAll(owner, spender_cs).call():
                already_ok += 1
            else:
                tx = ctf.functions.setApprovalForAll(spender_cs, True).build_transaction(
                    {"from": owner, "nonce": nonce, "gasPrice": gas_price}
                )
                signed = acct.sign_transaction(tx)
                tx_hashes.append(w3.eth.send_raw_transaction(signed.raw_transaction).hex())
                nonce += 1
                set_count += 1
    except Exception as exc:  # noqa: BLE001 - surface gas/RPC issues to caller
        return AllowanceStatus(set_count, already_ok, tx_hashes, error=str(exc))

    return AllowanceStatus(set_count, already_ok, tx_hashes)
