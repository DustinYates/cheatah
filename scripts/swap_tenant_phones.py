"""Swap phone numbers between tenant 2 and tenant 3."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable required")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant


async def swap_phones():
    """Swap phone numbers between tenant 2 and tenant 3."""
    print("=" * 70)
    print("SWAP PHONE NUMBERS: Tenant 2 <-> Tenant 3")
    print("=" * 70)
    print()
    print("Target configuration:")
    print("  Tenant 2: +12816990999")
    print("  Tenant 3: +12817679141")
    print()

    async with AsyncSessionLocal() as db:
        # Get current configs
        stmt2 = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 2)
        result2 = await db.execute(stmt2)
        config2 = result2.scalar_one_or_none()

        stmt3 = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        result3 = await db.execute(stmt3)
        config3 = result3.scalar_one_or_none()

        # Get tenant names for display
        tenant2_stmt = select(Tenant).where(Tenant.id == 2)
        tenant2_result = await db.execute(tenant2_stmt)
        tenant2 = tenant2_result.scalar_one_or_none()

        tenant3_stmt = select(Tenant).where(Tenant.id == 3)
        tenant3_result = await db.execute(tenant3_stmt)
        tenant3 = tenant3_result.scalar_one_or_none()

        print("CURRENT STATE:")
        print("-" * 70)
        if config2:
            print(f"Tenant 2 ({tenant2.name if tenant2 else 'Unknown'}):")
            print(f"  telnyx_phone_number: {config2.telnyx_phone_number or 'NOT SET'}")
            print(f"  voice_phone_number:  {config2.voice_phone_number or 'NOT SET'}")
        else:
            print("Tenant 2: No SMS config found!")

        if config3:
            print(f"Tenant 3 ({tenant3.name if tenant3 else 'Unknown'}):")
            print(f"  telnyx_phone_number: {config3.telnyx_phone_number or 'NOT SET'}")
            print(f"  voice_phone_number:  {config3.voice_phone_number or 'NOT SET'}")
        else:
            print("Tenant 3: No SMS config found!")

        print()
        print("APPLYING CHANGES:")
        print("-" * 70)

        # Update Tenant 2 -> +12816990999
        if config2:
            old_telnyx = config2.telnyx_phone_number
            old_voice = config2.voice_phone_number
            config2.telnyx_phone_number = "+12816990999"
            config2.voice_phone_number = "+12816990999"
            print(f"Tenant 2:")
            print(f"  telnyx_phone_number: {old_telnyx} -> +12816990999")
            print(f"  voice_phone_number:  {old_voice} -> +12816990999")

        # Update Tenant 3 -> +12817679141
        if config3:
            old_telnyx = config3.telnyx_phone_number
            old_voice = config3.voice_phone_number
            config3.telnyx_phone_number = "+12817679141"
            config3.voice_phone_number = "+12817679141"
            print(f"Tenant 3:")
            print(f"  telnyx_phone_number: {old_telnyx} -> +12817679141")
            print(f"  voice_phone_number:  {old_voice} -> +12817679141")

        await db.commit()
        print()
        print("=" * 70)
        print("DONE - Phone numbers swapped!")
        print("=" * 70)

        # Verify
        print()
        print("VERIFICATION:")
        print("-" * 70)

        # Re-fetch to confirm
        result2 = await db.execute(stmt2)
        config2 = result2.scalar_one_or_none()
        result3 = await db.execute(stmt3)
        config3 = result3.scalar_one_or_none()

        if config2:
            print(f"Tenant 2: telnyx={config2.telnyx_phone_number}, voice={config2.voice_phone_number}")
        if config3:
            print(f"Tenant 3: telnyx={config3.telnyx_phone_number}, voice={config3.voice_phone_number}")


if __name__ == "__main__":
    asyncio.run(swap_phones())
