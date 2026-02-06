#!/usr/bin/env python3
"""Enable dual bot feature for a tenant."""

import asyncio
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.persistence.database import async_session_factory
from app.persistence.models.tenant_widget_config import TenantWidgetConfig


DUAL_BOT_CONFIG = {
    "enabled": True,
    "secondaryPosition": "bottom-left",
    "secondaryIcon": {"type": "emoji", "emoji": "🤖"},
    "secondaryName": "Buddy Bot",
    "banterScript": [
        {"bot": "secondary", "text": "Hey! Another visitor! I hope they ask about our classes!", "delay": 2000},
        {"bot": "primary", "text": "Pfft... let them browse in peace.", "delay": 4000}
    ],
    "jokeResponses": [
        "I was just about to say that!",
        "Hey, I wanted to answer that one!",
        "Show off...",
        "Oh sure, steal my thunder.",
        "Fine, I'll just sit here looking cute."
    ]
}


async def enable_dual_bot(tenant_id: int):
    """Enable dual bot for a tenant."""
    async with async_session_factory() as db:
        # Get existing config
        stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            print(f"No widget config found for tenant {tenant_id}")
            return False

        # Update settings
        settings = config.settings or {}
        settings["dualBot"] = DUAL_BOT_CONFIG
        config.settings = settings

        await db.commit()
        print(f"Dual bot enabled for tenant {tenant_id}")
        print(f"Config: {DUAL_BOT_CONFIG}")
        return True


async def disable_dual_bot(tenant_id: int):
    """Disable dual bot for a tenant."""
    async with async_session_factory() as db:
        stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config or not config.settings:
            print(f"No widget config found for tenant {tenant_id}")
            return False

        settings = config.settings
        if "dualBot" in settings:
            settings["dualBot"]["enabled"] = False
            config.settings = settings
            await db.commit()
            print(f"Dual bot disabled for tenant {tenant_id}")
        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enable/disable dual bot feature")
    parser.add_argument("tenant_id", type=int, help="Tenant ID")
    parser.add_argument("--disable", action="store_true", help="Disable instead of enable")

    args = parser.parse_args()

    if args.disable:
        asyncio.run(disable_dual_bot(args.tenant_id))
    else:
        asyncio.run(enable_dual_bot(args.tenant_id))
