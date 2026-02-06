"""Update widget greeting message for Tenant 1.

Usage:
    DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/update_widget_greeting.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not PROD_DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Run with:")
    print('  DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/update_widget_greeting.py')
    sys.exit(1)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_widget_config import TenantWidgetConfig

TENANT_ID = 1
NEW_GREETING = "How can I help you?"


async def update_greeting():
    """Update the widget greeting for Tenant 1."""
    print("=" * 60)
    print("UPDATE WIDGET GREETING FOR TENANT 1")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == TENANT_ID)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            print(f"ERROR: No widget config found for tenant {TENANT_ID}")
            return

        settings = config.settings or {}
        behavior = settings.get("behavior", {})

        print(f"\nCurrent autoOpenMessage: {behavior.get('autoOpenMessage', '[NOT SET]')}")
        print(f"New autoOpenMessage: {NEW_GREETING}")

        # Update the greeting
        if "behavior" not in settings:
            settings["behavior"] = {}

        settings["behavior"]["autoOpenMessage"] = NEW_GREETING
        settings["behavior"]["autoOpenMessageEnabled"] = True

        config.settings = settings
        await db.commit()

        print("\nUpdated successfully!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(update_greeting())
