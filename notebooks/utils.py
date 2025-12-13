"""Shared utilities for notebooks."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import set_tenant_context
from app.persistence.database import AsyncSessionLocal


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for notebooks.

    Usage:
        async with get_db_session() as session:
            # Use session
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def setup_tenant_context(tenant_id: int | None) -> None:
    """Set tenant context for notebook operations.

    Args:
        tenant_id: Tenant ID to set in context
    """
    set_tenant_context(tenant_id)

