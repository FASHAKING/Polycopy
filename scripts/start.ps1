# Polycopy one-command bootstrap + launch (Windows PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1            # setup then api + bot + worker + web
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoWeb     # ...backend only
#
# Idempotent: creates the virtualenv, installs deps, runs the setup wizard the
# first time (no .env yet), then starts everything. Re-running just relaunches.
param([switch]$NoWeb)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")

# 1. Python virtualenv
if (-not (Test-Path ".venv")) {
  Write-Host "[start] creating virtualenv..."
  python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1

# 2. Backend deps (skip if already importable)
python -c "import polycopy" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[start] installing backend..."
  pip install -e ".[dev]"
}

# 3. Web deps (only if wanted, npm present, and not already installed)
$web = Join-Path $Root "web"
if (-not $NoWeb -and (Get-Command npm -ErrorAction SilentlyContinue) `
    -and (Test-Path $web) -and -not (Test-Path (Join-Path $web "node_modules"))) {
  Write-Host "[start] installing web dashboard..."
  Push-Location $web; npm install; Pop-Location
}

# 4. First-run config (interactive) if no .env yet
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
  Write-Host "[start] no .env found - running setup wizard..."
  polycopy-setup
}

# 5. Launch everything
Write-Host "[start] launching polycopy..."
if ($NoWeb) { polycopy-run } else { polycopy-run --web }
