"""Pytest configuration and fixtures."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base, get_db
from app.persistence.models import *  # noqa: F401, F403
from app.settings import get_async_database_url


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

