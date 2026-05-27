"""One-command runner: `polycopy-run` starts api + bot + worker together.

Spawns each backend service as a child process (so their event loops don't
fight), streams their logs, and shuts them all down together on Ctrl-C / SIGTERM
or if any one of them exits. The web dashboard (Node) runs separately.
"""

import signal
import subprocess
import sys
import time

# name -> module run via `python -m <module>`
SERVICES: dict[str, str] = {
    "api": "polycopy.api",
    "bot": "polycopy.bot",
    "worker": "polycopy.workers",
}

_GRACE_SECONDS = 10


def service_commands(python: str | None = None) -> dict[str, list[str]]:
    py = python or sys.executable
    return {name: [py, "-m", module] for name, module in SERVICES.items()}


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
    cmds = service_commands()
    procs: dict[str, subprocess.Popen] = {}
    for name, cmd in cmds.items():
        print(f"[polycopy-run] starting {name}", flush=True)
        procs[name] = subprocess.Popen(cmd)

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
