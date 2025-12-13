"""Alembic environment configuration."""

import json
import time
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.persistence.database import Base
from app.persistence.models import *  # noqa: F401, F403
from app.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from settings
original_url = settings.database_url
# #region agent log
with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
    f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:25", "message": "Alembic setting database URL", "data": {"original_url_prefix": original_url[:50] + "..." if len(original_url) > 50 else original_url, "url_uses_asyncpg": "postgresql+asyncpg" in original_url.lower(), "is_async_driver": "+asyncpg" in original_url.lower() or "+psycopg" in original_url.lower()}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
# #endregion

# Convert async URL to sync for Alembic if needed
if "+asyncpg" in original_url.lower():
    sync_url = original_url.replace("+asyncpg", "")
    # #region agent log
    with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
        f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:31", "message": "Converting async URL to sync for Alembic", "data": {"sync_url_prefix": sync_url[:50] + "..." if len(sync_url) > 50 else sync_url}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
    # #endregion
    config.set_main_option("sqlalchemy.url", sync_url)
else:
    config.set_main_option("sqlalchemy.url", original_url)

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
    with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
        f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:67", "message": "run_migrations_online called", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
    # #endregion
    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        # #region agent log
        with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:76", "message": "Engine created successfully", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
        # #endregion

        with connectable.connect() as connection:
            # #region agent log
            with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
                f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:79", "message": "Database connection established", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
            # #endregion
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
                # #region agent log
                with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
                    f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:85", "message": "Migrations completed successfully", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
                # #endregion
    except Exception as e:
        # #region agent log
        with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "alembic/env.py:89", "message": "Migration error", "data": {"error_type": type(e).__name__, "error_message": str(e)}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
        # #endregion
        raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

