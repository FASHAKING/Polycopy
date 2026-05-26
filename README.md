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

Non-custodial of funds: balances stay in each user's own Polymarket account. To
place orders the bot needs the user's signing key (Polymarket requires the order
to be signed by the funder's key); it's stored encrypted at rest with a Fernet
key and the L2 API creds are derived from it. Users are advised to use a
dedicated wallet funded only with trading capital.

## Bot commands

| Command | What it does |
|---|---|
| `/start`, `/help` | Register / show help |
| `/link` | Connect Polymarket (address + signing key; key message is auto-deleted) |
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
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, FERNET_KEY (see comment in .env.example)

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

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

Not yet wired (intentionally): Alembic migrations (currently `create_all` on
startup), realized-PnL backfill for copied trades, and order-fill reconciliation
(orders are placed as marketable limits and recorded as `submitted`).
