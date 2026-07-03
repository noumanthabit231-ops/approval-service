"""Test fixtures — in-memory SQLite per test module."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from approval_service.database import get_db
from approval_service.main import app
from approval_service.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def engine():
    """In-memory SQLite engine — recreate per test for isolation."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    """Session factory bound to the test engine."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db_session(engine, session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Single DB session for a test."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(engine, session_factory) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB override."""

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# Reusable auth headers
AUTH_HEADERS = {
    "X-User-Id": "usr_1",
    "X-User-Permissions": "approval:read,approval:create,approval:decide,approval:cancel",
}

READ_ONLY_HEADERS = {
    "X-User-Id": "usr_2",
    "X-User-Permissions": "approval:read",
}


def auth_headers(**overrides) -> dict:
    h = dict(AUTH_HEADERS)
    h.update(overrides)
    return h
