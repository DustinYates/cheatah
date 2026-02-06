"""Update widget to Blue Bot theme for Tenant 1.

Usage:
    DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/update_widget_blue_bot.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not PROD_DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Run with:")
    print('  DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/update_widget_blue_bot.py')
    sys.exit(1)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_widget_config import TenantWidgetConfig

TENANT_ID = 1


async def update_to_blue_bot():
    """Update the widget to Blue Bot theme for Tenant 1."""
    print("=" * 60)
    print("UPDATE WIDGET TO BLUE BOT THEME - TENANT 1")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == TENANT_ID)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            print(f"ERROR: No widget config found for tenant {TENANT_ID}")
            return

        settings = config.settings or {}

        print("\nCurrent settings:")
        print(f"  Primary color: {settings.get('colors', {}).get('primary', '[NOT SET]')}")
        print(f"  Agent name: {settings.get('socialProof', {}).get('agentName', '[NOT SET]')}")
        print(f"  Welcome message: {settings.get('messages', {}).get('welcomeMessage', '[NOT SET]')}")

        # Update to Blue Bot theme
        if "colors" not in settings:
            settings["colors"] = {}
        settings["colors"]["primary"] = "#3b82f6"  # Blue color
        settings["colors"]["buttonText"] = "#ffffff"

        if "socialProof" not in settings:
            settings["socialProof"] = {}
        settings["socialProof"]["agentName"] = "Blue Bot"
        settings["socialProof"]["showAvatar"] = False

        if "messages" not in settings:
            settings["messages"] = {}
        settings["messages"]["welcomeMessage"] = "Blue Bot"
        settings["messages"]["headerTitle"] = "Blue Bot"

        if "behavior" not in settings:
            settings["behavior"] = {}
        settings["behavior"]["autoOpenMessage"] = "How can I help you?"
        settings["behavior"]["autoOpenMessageEnabled"] = True

        # Disable dual bot if enabled (we just want one blue bot)
        if "dualBot" not in settings:
            settings["dualBot"] = {}
        settings["dualBot"]["enabled"] = False

        config.settings = settings
        await db.commit()

        print("\nUpdated settings:")
        print(f"  Primary color: {settings['colors']['primary']} (blue)")
        print(f"  Agent name: {settings['socialProof']['agentName']}")
        print(f"  Header title: {settings['messages']['headerTitle']}")
        print(f"  Auto-open message: {settings['behavior']['autoOpenMessage']}")

        print("\nWidget updated to Blue Bot theme!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(update_to_blue_bot())
