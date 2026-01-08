"""Database connection and session management."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.debug import debug_log
from app.settings import settings, get_async_database_url

# Get the async-compatible database URL
async_database_url = get_async_database_url()

# #region agent log
debug_log("database.py:9", "Creating async engine", {"database_url_prefix": async_database_url[:50] + "..." if len(async_database_url) > 50 else async_database_url, "url_uses_asyncpg": "postgresql+asyncpg" in async_database_url.lower()})
# #endregion

# Create async engine
engine = create_async_engine(
    async_database_url,
    echo=False,
    future=True,
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

