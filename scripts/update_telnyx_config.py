"""Update Telnyx configuration and ensure tenant 3 naming consistency."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Production database - uses DATABASE_URL from environment or .env file
PROD_DATABASE_URL = os.environ.get("DATABASE_URL")
if not PROD_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable required")

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.persistence.models.tenant_voice_config import TenantVoiceConfig


# Telnyx Configuration - from environment variables
TELNYX_API_KEY = os.environ.get("TELNYX_API_KEY")
TELNYX_PUBLIC_KEY = os.environ.get("TELNYX_PUBLIC_KEY")
if not TELNYX_API_KEY:
    raise ValueError("TELNYX_API_KEY environment variable required")

TENANT_CONFIG = {
    1: {
        "name": "Demo Company",
        "connection_id": "40019b5f-b8cb-403e-9b58-78124ec26560",
        "voice_phone": "+12816990999",  # BSS_03 voice line
    },
    3: {
        "name": "BSS Cypress-Spring",
        "connection_id": "40019b95-2d35-4479-9483-4080ad07d86a",
        "messaging_profile_id": "40019b95-2d35-4479-9483-4080ad07d86a",
        "voice_phone": "+12816990999",
        "sms_phone": "+12816990999",
    },
}


async def update_config():
    """Update Telnyx configuration for all tenants."""
    print("=" * 70)
    print("PRODUCTION - UPDATE TELNYX CONFIGURATION")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Step 1: Update tenant 3 name consistency
        print("STEP 1: Ensuring Tenant 3 Name Consistency")
        print("-" * 70)

        # Update tenant table
        tenant3_stmt = select(Tenant).where(Tenant.id == 3)
        tenant3_result = await db.execute(tenant3_stmt)
        tenant3 = tenant3_result.scalar_one_or_none()

        if tenant3:
            old_name = tenant3.name
            tenant3.name = "BSS Cypress-Spring"
            print(f"  Tenant.name: '{old_name}' → 'BSS Cypress-Spring'")

        # Update business profile if exists
        profile_stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == 3)
        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

        if profile:
            if profile.business_name != "BSS Cypress-Spring":
                old_biz = profile.business_name
                profile.business_name = "BSS Cypress-Spring"
                print(f"  BusinessProfile.business_name: '{old_biz}' → 'BSS Cypress-Spring'")
        else:
            print("  (No business profile found for tenant 3)")

        print()
        print("STEP 2: Updating Telnyx Configuration")
        print("-" * 70)

        for tenant_id, config in TENANT_CONFIG.items():
            print(f"\nTenant {tenant_id} ({config['name']}):")

            # Get existing SMS config
            sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            if sms_config:
                changes = []

                # Update connection ID
                if sms_config.telnyx_connection_id != config["connection_id"]:
                    old_val = sms_config.telnyx_connection_id or "NULL"
                    sms_config.telnyx_connection_id = config["connection_id"]
                    changes.append(f"telnyx_connection_id: {old_val} → {config['connection_id']}")

                # Update voice phone number
                if sms_config.voice_phone_number != config["voice_phone"]:
                    old_val = sms_config.voice_phone_number or "NULL"
                    sms_config.voice_phone_number = config["voice_phone"]
                    changes.append(f"voice_phone_number: {old_val} → {config['voice_phone']}")

                # Ensure voice is enabled
                if not sms_config.voice_enabled:
                    sms_config.voice_enabled = True
                    changes.append("voice_enabled: False → True")

                # Update messaging profile for tenant 3
                if "messaging_profile_id" in config:
                    if sms_config.telnyx_messaging_profile_id != config["messaging_profile_id"]:
                        old_val = sms_config.telnyx_messaging_profile_id or "NULL"
                        sms_config.telnyx_messaging_profile_id = config["messaging_profile_id"]
                        changes.append(f"telnyx_messaging_profile_id: {old_val} → {config['messaging_profile_id']}")

                # Update SMS phone for tenant 3
                if "sms_phone" in config:
                    if sms_config.telnyx_phone_number != config["sms_phone"]:
                        old_val = sms_config.telnyx_phone_number or "NULL"
                        sms_config.telnyx_phone_number = config["sms_phone"]
                        changes.append(f"telnyx_phone_number: {old_val} → {config['sms_phone']}")

                if changes:
                    for change in changes:
                        print(f"  ✓ {change}")
                else:
                    print("  (No changes needed)")
            else:
                print(f"  ❌ No TenantSmsConfig found!")

        # Commit all changes
        await db.commit()
        print()
        print("✅ All changes committed to production!")

        # Step 3: Verification
        print()
        print("=" * 70)
        print("STEP 3: Verification")
        print("-" * 70)

        for tenant_id in [1, 3]:
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            print(f"\nTenant {tenant_id}:")
            if tenant:
                print(f"  Name: {tenant.name}")
            if sms_config:
                print(f"  Provider: {sms_config.provider}")
                print(f"  Voice Enabled: {sms_config.voice_enabled}")
                print(f"  Voice Phone: {sms_config.voice_phone_number or 'NOT SET'}")
                print(f"  Connection ID: {sms_config.telnyx_connection_id or 'NOT SET'}")
                print(f"  SMS Phone: {sms_config.telnyx_phone_number or 'NOT SET'}")
                print(f"  Messaging Profile: {sms_config.telnyx_messaging_profile_id or 'NOT SET'}")

        print()
        print("=" * 70)
        print("CONFIGURATION COMPLETE")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(update_config())
