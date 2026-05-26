# Polycopy

Polymarket copy-trading Telegram bot with a public web dashboard.

## What it does

- **Telegram bot** to register, link a Polymarket account, and copy specific traders by username/wallet.
- **Auto-scout** that surfaces and follows traders in a configurable win-rate band (default 60–80%) with a minimum sample size.
- **Web dashboard** at `/` showing public bot health + aggregate stats; logged-in users (via Telegram login widget) see their own copied trades and P&L.

## Architecture

```
.
├── backend/                     # One Python package, three entry points
│   └── src/polycopy/
│       ├── core/                # config, db, models, crypto
│       ├── polymarket/          # Data API + CLOB API clients
│       ├── api/                 # FastAPI app  (polycopy-api)
│       ├── bot/                 # Telegram bot (polycopy-bot)
│       └── workers/             # watcher + scout + mirror (polycopy-worker)
├── web/                         # Next.js dashboard
├── docker-compose.yml
└── .env.example
```

Custodial, multi-tenant: each Telegram user controls their own wallet. On
onboarding a user can either **create a new custodial wallet** (the bot generates
a Polygon keypair and holds the key, encrypted at rest with a Fernet key) or
**link an existing Polymarket account** (they supply their own signing key).
Either way the L2 API creds are derived from the key. Signup collects an email
as account identity; Telegram remains the controlling auth.

## Bot commands

| Command | What it does |
|---|---|
| `/start`, `/help` | Register / show help |
| `/email you@example.com` | Sign up / set your email |
| `/wallet` | Create a new custodial wallet or link an existing one; shows balance + deposit address |
| `/link` | Link an existing Polymarket account (address + signing key; key message is auto-deleted) |
| `/status` | Connection state + live portfolio value |
| `/unlink` | Remove stored credentials |
| `/follow <username\|wallet>` | Copy a trader (disambiguates multiple username matches) |
| `/unfollow <username\|wallet>`, `/list` | Manage who you copy |
| `/auto on\|off\|status` | Auto-follow profitable, active traders in a 60–80% win-rate band |
| `/risk` | View/set caps: `size`, `slippage`, `maxtrade`, `daycap` |

## How trader selection works

- **Manual:** `/follow` resolves a username to wallet(s) via Polymarket's profile
  search and mirrors that trader's new trades.
- **Auto-scout:** pulls the profit leaderboard, keeps traders active in the last
  7 days, then computes a **realized win rate** by reconstructing per-market net
  cashflow from the activity feed (buys vs. sells + redeems over settled
  markets). Qualifies traders in the 60–80% band with enough settled markets and
  non-negative ROI. Traders too active to verify are excluded.
- **Copy sizing & safety:** each order is scaled by your `size` multiplier,
  price-padded by `slippage`, then bounded by your per-trade and daily spend
  caps before placement.

## Deployment

Host-agnostic via Docker. `docker compose up --build` runs Postgres + API + bot +
worker + web. For a real deploy (Railway/Fly/VPS):

- Set secrets: `TELEGRAM_BOT_TOKEN`, `FERNET_KEY`, `APP_SECRET`, `DATABASE_URL`.
- Build the web image with `NEXT_PUBLIC_API_URL` set to the **browser-reachable**
  API URL and `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` set to your bot's username
  (these are inlined into the client bundle at build time).
- Run the three backend processes (`polycopy-api`, `polycopy-bot`,
  `polycopy-worker`) from the same image with different commands.

## Quickstart (local dev)

Prerequisites: Python 3.11+, Node 20+, Docker (optional).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Interactive setup — asks for the few required details and writes .env
# (auto-generates FERNET_KEY + APP_SECRET; works on Linux/macOS/Windows PowerShell)
polycopy-setup

# Run all three processes in separate terminals:
polycopy-api      # http://localhost:8000
polycopy-bot
polycopy-worker

# Web (separate terminal)
cd ../web
npm install
npm run dev       # http://localhost:3000
```

## Status

Core build complete (Phases 1–9): Polymarket clients, DB layer, Telegram bot
(link/follow/auto/risk), watcher + mirror engine, auto-scout with realized
win-rate scoring, risk caps, and the web dashboard. Test suite: `make test`.

Order-fill reconciliation: a worker polls each `submitted`/`partial` order via
the user's CLOB client and advances it to `filled` / `partial` / `canceled`,
recording the matched size and fill price. The dashboard's Performance section
shows portfolio value, unrealized + realized P&L, win rate, and execution
counts, computed live from the user's wallet.

Not yet wired (intentionally): Alembic migrations (currently `create_all` on
startup).

Needs live verification before real funds flow through **created** wallets: the
on-chain trading approvals in `core/wallet.py` (`ensure_trading_allowances`) set
USDC + CTF allowances for the Polymarket exchanges. They require POL (gas) in the
created wallet and have not been verified end-to-end on Polygon. Linking an
existing, already-approved Polymarket account avoids this path entirely.
