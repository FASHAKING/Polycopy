# Security model

Polycopy is **custodial**: for users who create a wallet through the bot, the
bot holds that wallet's signing key. This document explains how keys are
protected and what operators must do to run it safely.

## What secrets exist

| Secret | Where | Protection |
|---|---|---|
| User signing keys (created or linked wallets) | `polymarket_credentials.private_key_enc` | Fernet-encrypted at rest |
| Polymarket API secret / passphrase | same table, `*_enc` columns | Fernet-encrypted at rest |
| `FERNET_KEY` | env only | Never in the DB or logs; encrypts the above |
| `APP_SECRET` | env only | Signs dashboard session tokens |
| `TELEGRAM_BOT_TOKEN` | env only | Bot auth |

Plaintext private keys exist only transiently in memory when signing an order
or deriving API creds. They are never written to the DB unencrypted, never
returned by the API, and never logged.

## Operator responsibilities

- **Protect `FERNET_KEY`.** It decrypts every stored key. Store it in a secrets
  manager, not in the repo. If it leaks, rotate it and re-encrypt (all stored
  credentials must be re-entered, since old ciphertext can't be read with a new
  key).
- **Back it up.** If you lose `FERNET_KEY`, every stored credential is
  unrecoverable and users must re-link.
- **Use strong, unique `APP_SECRET`.** `polycopy-setup` generates one.
- **Restrict `CORS_ORIGINS`** to your dashboard's domain in production
  (`*` is dev-only).
- **Encrypt the database at rest** and lock down network access to it.
- **Run over TLS.** Telegram login + bearer tokens must not traverse plaintext.

## Built-in safeguards

- `APP_ENV=prod` logs a warning on startup for insecure defaults (missing
  `FERNET_KEY`, default `APP_SECRET`, wildcard CORS) — see
  `Settings.check_production_secrets`.
- The `/link` flow deletes the message containing a pasted private key
  immediately after reading it.
- Decryption failures raise a clear error (wrong/rotated `FERNET_KEY`) rather
  than silently producing garbage.
- Paper-trading mode (`PAPER_TRADING` / `/paper`) lets you validate the full
  pipeline with no key ever used to place a real order.

## Reducing custodial risk

- Prefer **linking an existing Polymarket account** over creating one when the
  user wants to retain key control.
- Encourage users to fund created wallets only with capital they intend to
  trade.
- Per-user risk caps (`/risk maxtrade`, `/risk daycap`) bound blast radius.

## Reporting

Found an issue? Open a private report to the maintainers before public
disclosure.
