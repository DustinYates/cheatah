"""Fix sendable_assets configuration for tenant 3 (BSS Cypress-Spring).

Issue: sendable_assets.registration_link.enabled was False, blocking SMS sends.
The bot promises to text but the fulfillment service silently fails.
"""

import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Get database URL from environment or use default
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    print("Set it with: export DATABASE_URL=postgresql://...")
    sys.exit(1)

ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("?sslmode=", "?ssl=")

engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def fix_sendable_assets():
    """Fix the sendable_assets config for tenant 3."""
    print("=" * 70)
    print("FIX TENANT 3 SENDABLE_ASSETS CONFIGURATION")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Get current config
        result = await db.execute(
            text("SELECT id, config_json FROM tenant_prompt_configs WHERE tenant_id = 3")
        )
        row = result.fetchone()

        if not row:
            print("ERROR: No tenant_prompt_config found for tenant_id=3")
            return

        config_id, config_json = row
        print(f"Found config ID: {config_id}")

        # Parse config
        if isinstance(config_json, str):
            config = json.loads(config_json)
        else:
            config = config_json

        # Show current sendable_assets
        current_sa = config.get("sendable_assets", {})
        print("\nCurrent sendable_assets:")
        print(json.dumps(current_sa, indent=2))

        # Fix the config
        config["sendable_assets"] = {
            "registration_link": {
                "url": "https://britishswimschool.com/cypress-spring/register/",
                "enabled": True,
                "sms_template": "Hi {name}! Here's your British Swim School registration link: {url}"
            }
        }

        print("\nUpdated sendable_assets:")
        print(json.dumps(config["sendable_assets"], indent=2))

        # Confirm
        response = input("\nApply this fix? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

        # Update database
        await db.execute(
            text("UPDATE tenant_prompt_configs SET config_json = :config, updated_at = NOW() WHERE id = :id"),
            {"config": json.dumps(config), "id": config_id}
        )
        await db.commit()

        print("\n✅ Configuration updated successfully!")
        print("   SMS sending for registration links is now ENABLED.")


if __name__ == "__main__":
    asyncio.run(fix_sendable_assets())
