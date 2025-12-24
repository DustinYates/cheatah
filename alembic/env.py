"""Alembic environment configuration."""

import json
import time
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.persistence.database import Base
from app.persistence.models import *  # noqa: F401, F403
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

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from environment (Alembic uses sync driver)
import os
original_url = os.environ.get("DATABASE_URL", settings.database_url)

# Convert postgres:// to postgresql:// and ensure sync driver for Alembic
if original_url.startswith("postgres://"):
    sync_url = original_url.replace("postgres://", "postgresql://", 1)
elif "+asyncpg" in original_url.lower():
    sync_url = original_url.replace("+asyncpg", "")
else:
    sync_url = original_url

# Escape % signs for ConfigParser (double them) - needed because %21 in password
sync_url = sync_url.replace("%", "%%")

# #region agent log
# Never log secrets/credentials; redact any userinfo/password from URLs.
try:
    from urllib.parse import urlsplit

    _u = urlsplit(sync_url.replace("%%", "%"))
    _host = _u.hostname or ""
    _port = f":{_u.port}" if _u.port else ""
    _db = (_u.path or "")[:64]
    _safe_url = f"{_u.scheme}://{_host}{_port}{_db}"
except Exception:
    _safe_url = "<redacted>"
_debug_log("alembic/env.py:25", "Alembic setting database URL", {"sync_url_redacted": _safe_url})
# #endregion

config.set_main_option("sqlalchemy.url", sync_url)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # #region agent log
    _debug_log("alembic/env.py:67", "run_migrations_online called", {})
    # #endregion
    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        # #region agent log
        _debug_log("alembic/env.py:76", "Engine created successfully", {})
        # #endregion

        with connectable.connect() as connection:
            # #region agent log
            _debug_log("alembic/env.py:79", "Database connection established", {})
            # #endregion
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
                # #region agent log
                _debug_log("alembic/env.py:85", "Migrations completed successfully", {})
                # #endregion
    except Exception as e:
        # #region agent log
        _debug_log("alembic/env.py:89", "Migration error", {"error_type": type(e).__name__, "error_message": str(e)})
        # #endregion
        raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

