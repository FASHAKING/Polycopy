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

Non-custodial: each user supplies their own Polymarket CLOB API credentials. The bot never holds private keys; API secrets are encrypted at rest with a Fernet key.

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

Phase 1 — scaffolding. See commit history for progress against the plan.
