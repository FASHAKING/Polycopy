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
| `/paper on\|off` | Dry-run: simulate copies without placing real orders |
| `/notify on\|off` | Trade alerts when a trader you follow trades |

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

## Startup guide

Two ways to run Polycopy:

- **From source** — a Python virtualenv for the backend plus (optionally) Node
  for the dashboard. Best for development and light VPS deployments. Guides below
  for **Windows (PowerShell)** and **Linux (VPS)**.
- **Docker** — one command brings up Postgres + api + bot + worker + web. See
  [Docker](#docker-any-os).

Either way, local dev defaults to a file-based SQLite database, so you don't
need Postgres to get started.

### Windows (PowerShell)

Prerequisites: [Python 3.11+](https://www.python.org/downloads/windows/) (tick
"Add python.exe to PATH" in the installer), [Git](https://git-scm.com/download/win),
and — for the dashboard — [Node 20+](https://nodejs.org/). Open **Windows
PowerShell** and run the one-liner:

```powershell
git clone https://github.com/FASHAKING/Polycopy.git
cd Polycopy
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

That script creates the virtualenv, installs the backend (and the dashboard if
`npm` is present), runs the interactive setup wizard the first time, then starts
api + bot + worker + web together. Add `-NoWeb` to skip the dashboard. Re-running
it just relaunches. Ctrl-C stops everything.

<details>
<summary>Prefer to run the steps by hand?</summary>

```powershell
cd Polycopy\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked, allow scripts for this user once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev]"
polycopy-setup                 # writes ..\.env (keep PAPER mode = Y for a safe first run)
cd ..\web ; npm install ; cd ..\backend   # optional: dashboard
polycopy-run --web             # or `polycopy-run` for backend only
```
</details>

### Linux (VPS)

Prerequisites: Python 3.11+ and (for the dashboard) Node 20+. On a fresh
Ubuntu/Debian box:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
# Optional, only if you want the dashboard:
#   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

Then clone and run the one-liner:

```bash
git clone https://github.com/FASHAKING/Polycopy.git
cd Polycopy
bash scripts/start.sh
```

That script creates the virtualenv, installs the backend (and the dashboard if
`npm` is present), runs the interactive setup wizard the first time, then starts
api + bot + worker + web together. Add `--no-web` to skip the dashboard.
Re-running it just relaunches. Ctrl-C stops everything.

To keep it running after you log out, run it inside `tmux`/`screen` or under a
process manager (`systemd`, `pm2`, `supervisor`). Quick `tmux` option:

```bash
tmux new -s polycopy
bash scripts/start.sh
# detach with Ctrl-b then d; reattach later with: tmux attach -t polycopy
```

<details>
<summary>Prefer to run the steps by hand?</summary>

```bash
cd Polycopy/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
polycopy-setup                 # writes ../.env (keep PAPER mode = Y for a safe first run)
( cd ../web && npm install )    # optional: dashboard
polycopy-run --web             # or `polycopy-run` for backend only
```
</details>

> **Note:** `--web` is skipped automatically if `npm` isn't on `PATH` or the
> `web/` directory is missing — the backend still starts.

### Docker (any OS)

Prerequisites: Docker + Docker Compose. From the repo root:

```bash
cp .env.example .env   # then edit .env (at minimum set TELEGRAM_BOT_TOKEN, FERNET_KEY)
docker compose up --build
```

This runs Postgres + api + bot + worker + web together. The dashboard is at
http://localhost:3000 and the API at http://localhost:8000.

## First run (in paper mode — recommended)

Paper mode runs the whole copy pipeline against live Polymarket data but places
**no real orders**, so you can confirm everything works with zero risk. A fresh
`polycopy-setup` defaults to paper mode on.

1. **Configure**: `polycopy-setup` → answer prompts → keep "Start in PAPER mode" = **Y**.
2. **Launch** (one command from `backend/`, or `docker compose up --build`):
   ```bash
   polycopy-run      # starts api + bot + worker together; Ctrl-C stops all
   ```
3. **In Telegram**: `/start` → `/email you@example.com` → `/wallet` (create or link).
4. **Confirm paper is on**: `/paper status` → should say *ON* (forced globally).
5. **Follow a live trader**: `/follow <username>` (try an active one), or `/auto on`.
6. **Watch it work**: when that trader trades, you'll get a
   "📝 Paper trade — would copy N shares" alert. The dashboard shows the copy
   under a **PAPER MODE** badge. No funds move.
7. **Go live** only once paper behaves as expected:
   - `/risk maxtrade 2` and `/risk daycap 5` (tiny caps for the first real trade)
   - fund/approve the wallet (or use a linked, already-approved account)
   - `/paper off`, then watch one real trade round-trip before lifting caps.

## Database migrations

The app auto-creates tables on startup for quick dev. For production, manage the
schema with Alembic instead:

```bash
cd backend
alembic upgrade head        # apply migrations
alembic revision --autogenerate -m "describe change"   # after editing models
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
