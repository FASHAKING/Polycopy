#!/usr/bin/env bash
# Polycopy one-command bootstrap + launch (Linux / macOS).
#
#   bash scripts/start.sh            # setup (first run) then api + bot + worker + web
#   bash scripts/start.sh --no-web   # …backend only
#
# Idempotent: creates the virtualenv, installs deps, runs the setup wizard the
# first time (no .env yet), then starts everything. Re-running just relaunches.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT/backend"

PYTHON="${PYTHON:-python3}"

# 1. Python virtualenv
if [ ! -d .venv ]; then
  echo "[start] creating virtualenv…"
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Backend deps (skip if already importable)
if ! python -c "import polycopy" >/dev/null 2>&1; then
  echo "[start] installing backend…"
  pip install -e ".[dev]"
fi

WANT_WEB=1
for arg in "$@"; do
  [ "$arg" = "--no-web" ] && WANT_WEB=0
done

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
