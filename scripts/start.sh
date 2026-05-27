#!/usr/bin/env bash
# Polycopy one-command bootstrap + launch (Linux / macOS).
#
#   bash scripts/start.sh            # setup (first run) then api + bot + worker + web
#   bash scripts/start.sh --no-web   # …backend only
#   bash scripts/start.sh --dev      # …also install dev tools (ruff/mypy/pytest)
#
# Idempotent: creates the virtualenv, installs deps, runs the setup wizard the
# first time (no .env yet), then starts everything. Re-running just relaunches.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT/backend"

PYTHON="${PYTHON:-python3}"

WANT_WEB=1
WANT_DEV=0
for arg in "$@"; do
  case "$arg" in
    --no-web) WANT_WEB=0 ;;
    --dev) WANT_DEV=1 ;;
  esac
done

# 1. Python virtualenv
if [ ! -d .venv ]; then
  echo "[start] creating virtualenv…"
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Backend deps (skip if already importable). Runtime-only by default — a
#    server doesn't need ruff/mypy/pytest, and pulling them makes pip's resolver
#    churn. Pass --dev for the full toolchain.
if ! python -c "import polycopy" >/dev/null 2>&1; then
  echo "[start] upgrading pip…"
  python -m pip install --upgrade pip >/dev/null
  if [ "$WANT_DEV" = 1 ]; then
    echo "[start] installing backend (with dev tools)…"
    pip install -e ".[dev]"
  else
    echo "[start] installing backend…"
    pip install -e .
  fi
fi

# 3. Web deps (only if wanted, npm present, and not already installed)
if [ "$WANT_WEB" = 1 ] && command -v npm >/dev/null 2>&1 \
   && [ -d "$ROOT/web" ] && [ ! -d "$ROOT/web/node_modules" ]; then
  echo "[start] installing web dashboard…"
  ( cd "$ROOT/web" && npm install )
fi

# 4. First-run config (interactive) if no .env yet
if [ ! -f "$ROOT/.env" ]; then
  echo "[start] no .env found — running setup wizard…"
  polycopy-setup
fi

# 5. Launch everything
echo "[start] launching polycopy…"
if [ "$WANT_WEB" = 1 ]; then
  exec polycopy-run --web
else
  exec polycopy-run
fi
