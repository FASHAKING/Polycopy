"""One-command runner: `polycopy-run` starts api + bot + worker together.

Spawns each backend service as a child process (so their event loops don't
fight), streams their logs, and shuts them all down together on Ctrl-C / SIGTERM
or if any one of them exits.

By default only the Python backend runs. Pass ``--web`` to also launch the
Next.js dashboard (``npm run dev``) so the whole stack comes up in one command:

    polycopy-run --web
"""

import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# name -> module run via `python -m <module>`
SERVICES: dict[str, str] = {
    "api": "polycopy.api",
    "bot": "polycopy.bot",
    "worker": "polycopy.workers",
}

_GRACE_SECONDS = 10

# run_cli.py = <repo>/backend/src/polycopy/run_cli.py → repo root is 3 levels up.
WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def service_commands(python: str | None = None) -> dict[str, list[str]]:
    py = python or sys.executable
    return {name: [py, "-m", module] for name, module in SERVICES.items()}


def web_command(web_dir: Path = WEB_DIR) -> tuple[list[str], Path] | None:
    """Return (command, cwd) for the web dev server, or None if unavailable."""
    npm = shutil.which("npm")
    if npm is None or not web_dir.is_dir():
        return None
    return [npm, "run", "dev"], web_dir


def _terminate_all(procs: dict[str, subprocess.Popen]) -> None:
    for p in procs.values():
        if p.poll() is None:
            p.terminate()
    deadline = time.time() + _GRACE_SECONDS
    for p in procs.values():
        try:
            p.wait(timeout=max(0.0, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    include_web = "--web" in sys.argv[1:]

    specs: list[tuple[str, list[str], Path | None]] = [
        (name, cmd, None) for name, cmd in service_commands().items()
    ]

    if include_web:
        web = web_command()
        if web is None:
            print(
                "[polycopy-run] --web requested but npm or the web/ directory "
                "was not found; starting backend only",
                flush=True,
            )
        else:
            cmd, cwd = web
            specs.append(("web", cmd, cwd))

    procs: dict[str, subprocess.Popen] = {}
    for name, cmd, cwd in specs:
        print(f"[polycopy-run] starting {name}", flush=True)
        procs[name] = subprocess.Popen(cmd, cwd=cwd)

    stop = {"requested": False}

    def _request_stop(_signum, _frame) -> None:
        stop["requested"] = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    exit_code = 0
    try:
        while not stop["requested"]:
            for name, p in procs.items():
                ret = p.poll()
                if ret is not None:
                    print(
                        f"[polycopy-run] {name} exited (code {ret}); stopping the rest",
                        flush=True,
                    )
                    exit_code = ret or 1
                    stop["requested"] = True
                    break
            time.sleep(0.5)
    finally:
        print("[polycopy-run] shutting down…", flush=True)
        _terminate_all(procs)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
