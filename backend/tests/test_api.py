import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polycopy.api.app import create_app
from polycopy.core.db import Base, get_session
from polycopy.core.security import make_session_token


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        from polycopy.core import models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with maker() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c._maker = maker  # expose for seeding
        yield c
    await engine.dispose()


async def test_stats_empty(client):
    r = await client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["users"] == 0
    assert body["active_follows"] == 0


async def test_me_requires_auth(client):
    r = await client.get("/api/me")
    assert r.status_code == 401


async def test_me_with_token(client):
    from polycopy.core import repo

    async with client._maker() as s:
        await repo.get_or_create_user(s, telegram_id=555, username="bob")
        await s.commit()

    token = make_session_token(555)
    r = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["telegram_id"] == 555
    assert body["linked"] is False


async def test_top_traders(client):
    from polycopy.core import repo

    async with client._maker() as s:
        t = await repo.get_or_create_trader(s, wallet="0xtop", display_name="Topper")
        await repo.update_trader_stats(
            s, t, win_rate=0.7, roi=1.2, trades_count=40, volume_usd=5000
        )
        await s.commit()

    r = await client.get("/api/traders/top")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Topper"
    assert rows[0]["win_rate"] == 0.7
