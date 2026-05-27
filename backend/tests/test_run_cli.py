import sys

from polycopy.run_cli import SERVICES, service_commands


def test_service_commands_cover_all_services():
    cmds = service_commands()
    assert set(cmds) == {"api", "bot", "worker"}


def test_service_commands_use_python_m():
    cmds = service_commands(python="/usr/bin/python3")
    assert cmds["api"] == ["/usr/bin/python3", "-m", "polycopy.api"]
    assert cmds["worker"] == ["/usr/bin/python3", "-m", "polycopy.workers"]


def test_service_commands_default_to_current_interpreter():
    assert service_commands()["bot"][0] == sys.executable


def test_services_map_to_runnable_modules():
    # Each target must be an importable package with a __main__.
    import importlib

    for module in SERVICES.values():
        assert importlib.util.find_spec(f"{module}.__main__") is not None
