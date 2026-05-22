from fastapi.testclient import TestClient

from polycopy.api.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_models_import() -> None:
    # Importing should register all tables with Base.metadata.
    from polycopy.core import db, models

    table_names = set(db.Base.metadata.tables.keys())
    expected = {
        "users",
        "polymarket_credentials",
        "traders",
        "follows",
        "copied_trades",
        "watcher_cursors",
    }
    assert expected.issubset(table_names), table_names

    # silence unused-import linters
    assert models.User.__tablename__ == "users"
