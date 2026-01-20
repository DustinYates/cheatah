"""Database connection and session management."""

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import Pool

from app.core.debug import debug_log
from app.core.tenant_context import get_tenant_context
from app.settings import settings, get_async_database_url

# Get the async-compatible database URL
async_database_url = get_async_database_url()

# #region agent log
debug_log("database.py:9", "Creating async engine", {"database_url_prefix": async_database_url[:50] + "..." if len(async_database_url) > 50 else async_database_url, "url_uses_asyncpg": "postgresql+asyncpg" in async_database_url.lower()})
# #endregion

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


def _set_tenant_context_sync(dbapi_connection, connection_record):
    """Set the tenant context on the database connection for RLS.

    This is called synchronously when a connection is checked out from the pool.
    It sets the PostgreSQL session variable that RLS policies use.
    """
    if dbapi_connection is None:
        return  # Connection not available, skip RLS setup

    try:
        tenant_id = get_tenant_context()
        cursor = dbapi_connection.cursor()
        try:
            if tenant_id is not None:
                cursor.execute(f"SET app.current_tenant_id = '{tenant_id}'")
            else:
                # Reset to empty for global admin operations
                cursor.execute("SET app.current_tenant_id = ''")
        finally:
            cursor.close()
    except Exception:
        pass  # Silently ignore RLS errors to not break connection checkout


def _reset_tenant_context_sync(dbapi_connection, connection_record):
    """Reset tenant context when connection is returned to pool.

    This ensures connections don't leak tenant context to other requests.
    """
    if dbapi_connection is None:
        return  # Connection not available, skip reset

    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET app.current_tenant_id = ''")
        finally:
            cursor.close()
    except Exception:
        pass  # Silently ignore errors during checkin


# Register event listeners for RLS tenant context
# Only for PostgreSQL (asyncpg) connections
if "postgresql" in get_async_database_url().lower():
    @event.listens_for(Pool, "checkout")
    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        """Set tenant context when connection is checked out."""
        _set_tenant_context_sync(dbapi_connection, connection_record)

    @event.listens_for(Pool, "checkin")
    def on_checkin(dbapi_connection, connection_record):
        """Reset tenant context when connection is returned."""
        _reset_tenant_context_sync(dbapi_connection, connection_record)


async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    # #region agent log
    debug_log("database.py:32", "get_db called - creating session", {}, "B")
    # #endregion
    async with AsyncSessionLocal() as session:
        try:
            # #region agent log
            debug_log("database.py:36", "Session created successfully", {}, "B")
            # #endregion
            yield session
        except Exception as e:
            # #region agent log
            debug_log("database.py:42", "Database session error", {"error_type": type(e).__name__, "error_message": str(e)}, "B")
            # #endregion
            raise
        finally:
            await session.close()

