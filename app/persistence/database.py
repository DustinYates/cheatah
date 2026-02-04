"""Database connection and session management."""

import logging

import sentry_sdk
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.tenant_context import get_tenant_context
from app.settings import get_async_database_url

logger = logging.getLogger(__name__)

# Get the async-compatible database URL
async_database_url = get_async_database_url()

# Create async engine with conservative pool settings for Supabase Pooler
# Note: Supabase Pooler in Session mode has strict limits (typically 10-15 connections)
engine = create_async_engine(
    async_database_url,
    echo=False,
    future=True,
    pool_size=1,  # Minimal pool for Supabase session mode limits
    max_overflow=1,  # Allow 1 extra connection under load (2 total max per instance)
    pool_recycle=180,  # Recycle connections every 3 minutes (faster turnover)
    pool_pre_ping=True,  # Verify connections are alive
    pool_timeout=10,  # Fail fast if no connection available in 10 seconds
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Alias for background tasks that need to create their own sessions
async_session_factory = AsyncSessionLocal

# Base class for models
Base = declarative_base()


async def _set_tenant_context_async(session: AsyncSession) -> None:
    """Set the tenant context on the database connection for RLS.

    This is called asynchronously when a session is created.
    It sets the PostgreSQL session variable that RLS policies use.
    """
    try:
        tenant_id = get_tenant_context()
        if tenant_id is not None:
            await session.execute(text(f"SET app.current_tenant_id = '{tenant_id}'"))
        else:
            # Reset to empty for global admin operations
            await session.execute(text("SET app.current_tenant_id = ''"))
    except Exception as e:
        # Log RLS setup errors - these are critical for tenant isolation security
        logger.error(f"RLS context setup failed: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        # Don't raise - allow session to proceed, but log the security concern


async def get_db() -> AsyncSession:
    """Dependency for getting database session with RLS tenant context."""
    async with AsyncSessionLocal() as session:
        try:
            # Set tenant context for RLS using proper async execution
            await _set_tenant_context_async(session)
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
            raise
        finally:
            # Reset tenant context when returning session
            try:
                await session.execute(text("SET app.current_tenant_id = ''"))
            except Exception:
                pass  # Ignore errors during cleanup
            await session.close()


async def get_db_no_rls() -> AsyncSession:
    """Dependency for getting database session WITHOUT RLS tenant context.

    Use this for cross-tenant operations like forums where access is controlled
    via group membership rather than tenant isolation.

    WARNING: Only use this for intentionally cross-tenant features.
    """
    async with AsyncSessionLocal() as session:
        try:
            # Explicitly clear tenant context to ensure no RLS filtering
            await session.execute(text("SET app.current_tenant_id = ''"))
            yield session
        except Exception as e:
            logger.error(f"Database session (no RLS) error: {e}", exc_info=True)
            raise
        finally:
            await session.close()

