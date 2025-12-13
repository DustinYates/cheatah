"""Database connection and session management."""

import json
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.settings import settings

def _debug_log(location: str, message: str, data: dict, hypothesis_id: str = "A"):
    """Helper to safely write debug logs."""
    try:
        log_path = Path(".cursor/debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": location, "message": message, "data": data, "sessionId": "debug-session", "runId": "run1", "hypothesisId": hypothesis_id}) + "\n")
    except Exception:
        pass  # Silently fail if logging isn't possible

# #region agent log
_debug_log("database.py:9", "Creating async engine", {"database_url_prefix": settings.database_url[:50] + "..." if len(settings.database_url) > 50 else settings.database_url, "url_uses_asyncpg": "postgresql+asyncpg" in settings.database_url.lower()})
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
    _debug_log("database.py:32", "get_db called - creating session", {}, "B")
    # #endregion
    async with AsyncSessionLocal() as session:
        try:
            # #region agent log
            _debug_log("database.py:36", "Session created successfully", {}, "B")
            # #endregion
            yield session
        except Exception as e:
            # #region agent log
            _debug_log("database.py:42", "Database session error", {"error_type": type(e).__name__, "error_message": str(e)}, "B")
            # #endregion
            raise
        finally:
            await session.close()

