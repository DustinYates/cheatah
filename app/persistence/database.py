"""Database connection and session management."""

import json
import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.settings import settings

# #region agent log
with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
    f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "database.py:9", "message": "Creating async engine", "data": {"database_url_prefix": settings.database_url[:50] + "..." if len(settings.database_url) > 50 else settings.database_url, "url_uses_asyncpg": "postgresql+asyncpg" in settings.database_url.lower()}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
# #endregion

# Create async engine
engine = create_async_engine(
    settings.database_url,
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

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    # #region agent log
    with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
        f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "database.py:32", "message": "get_db called - creating session", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "B"}) + "\n")
    # #endregion
    async with AsyncSessionLocal() as session:
        try:
            # #region agent log
            with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
                f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "database.py:36", "message": "Session created successfully", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "B"}) + "\n")
            # #endregion
            yield session
        except Exception as e:
            # #region agent log
            with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
                f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "database.py:42", "message": "Database session error", "data": {"error_type": type(e).__name__, "error_message": str(e)}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "B"}) + "\n")
            # #endregion
            raise
        finally:
            await session.close()

