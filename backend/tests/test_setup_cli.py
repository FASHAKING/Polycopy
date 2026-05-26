from pathlib import Path

from cryptography.fernet import Fernet

from polycopy.setup_cli import (
    find_project_root,
    generate_fernet_key,
    generate_secret,
    render_env,
)


def test_generated_fernet_key_is_valid():
    key = generate_fernet_key()
    # Must be usable by Fernet (round-trips).
    f = Fernet(key.encode())
    assert f.decrypt(f.encrypt(b"x")) == b"x"


def test_generated_secret_is_long_and_unique():
    a, b = generate_secret(), generate_secret()
    assert a != b
    assert len(a) >= 40


def test_render_env_includes_all_keys():
    values = {"TELEGRAM_BOT_TOKEN": "123:abc", "FERNET_KEY": "k", "APP_SECRET": "s"}
    out = render_env(values)
    assert "TELEGRAM_BOT_TOKEN=123:abc" in out
    assert "FERNET_KEY=k" in out
    assert "DATABASE_URL=" in out  # present even if defaulted/blank


def test_find_project_root(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "backend" / "src").mkdir(parents=True)
    (root / ".env.example").write_text("x")
    found = find_project_root(root / "backend" / "src")
    assert found == root
