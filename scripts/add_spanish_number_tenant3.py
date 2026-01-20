#!/usr/bin/env python3
"""Add Spanish phone number to tenant 3 configuration."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.persistence.database import async_session_factory
from app.persistence.models.tenant_sms_config import TenantSmsConfig


TENANT_ID = 3
SPANISH_PHONE_NUMBER = "+12817679141"  # Spanish AI line


async def add_spanish_number():
    """Add Spanish phone number to tenant 3's voice_phone_number field."""
    async with async_session_factory() as db:
        # Get current config
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == TENANT_ID)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            print(f"ERROR: No SMS config found for tenant {TENANT_ID}")
            return

        print(f"Current config for tenant {TENANT_ID}:")
        print(f"  telnyx_phone_number: {config.telnyx_phone_number}")
        print(f"  voice_phone_number: {config.voice_phone_number}")

        # Update voice_phone_number with Spanish number
        config.voice_phone_number = SPANISH_PHONE_NUMBER
        await db.commit()
        await db.refresh(config)

        print(f"\nUpdated config:")
        print(f"  telnyx_phone_number: {config.telnyx_phone_number}")
        print(f"  voice_phone_number: {config.voice_phone_number}")
        print(f"\nSpanish number {SPANISH_PHONE_NUMBER} added successfully!")


if __name__ == "__main__":
    asyncio.run(add_spanish_number())
