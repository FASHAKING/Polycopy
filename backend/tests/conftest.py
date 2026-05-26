import os

import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Ensure a valid Fernet key exists before any polycopy module imports settings.
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture
async def session():
    from polycopy.core.db import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Import models so metadata is populated before create_all.
        from polycopy.core import models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
