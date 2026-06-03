"""Pytest configuration and fixtures."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base, get_db
from app.persistence.models import *  # noqa: F401, F403
from app.settings import get_async_database_url


@pytest.fixture(autouse=True)
async def _dispose_global_engine():
    """Dispose the app's global async engine after every test.

    `app.persistence.database` creates a module-level engine with a connection
    pool. pytest-asyncio runs each test in its own event loop, so a pooled asyncpg
    connection opened in one test's loop and then reused by the next test raises
    "got Future attached to a different loop" (it surfaces as an RLS-setup error in
    the FastAPI DB middleware and fails whichever test happens to reuse it). The
    victim depends purely on collection order, so adding/removing test files made
    unrelated tests flip red. Disposing the pool in this test's loop, before the
    next test starts, forces fresh per-loop connections and keeps the suite
    order-independent. For fully-mocked tests the pool is empty and this is a no-op.
    """
    yield
    from app.persistence.database import engine

    try:
        await engine.dispose()
    except Exception:
        pass


@pytest.fixture
async def db_session():
    """Create a test database session using PostgreSQL with transaction rollback."""
    engine = create_async_engine(
        get_async_database_url(),
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        # Start a transaction that will be rolled back
        trans = await conn.begin()
        async_session = sessionmaker(
            bind=conn, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session() as session:
            yield session

        # Rollback to keep database clean between tests
        await trans.rollback()

    await engine.dispose()


@pytest.fixture
async def test_client(db_session):
    """Create a test FastAPI client."""
    from fastapi.testclient import TestClient
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()

