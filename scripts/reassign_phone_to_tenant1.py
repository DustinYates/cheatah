"""Reassign phone number +12816990999 to Tenant 1 (ConvoPro).

This script:
1. Copies Telnyx config (API key, messaging profile, connection ID) from Tenant 2 to Tenant 1
2. Updates Tenant 1's phone numbers to +12816990999
3. Copies Telnyx AI Agent ID to Tenant 1's voice config
4. Optionally clears Tenant 2's config

Usage:
    DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/reassign_phone_to_tenant1.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not PROD_DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Run with:")
    print('  DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/reassign_phone_to_tenant1.py')
    sys.exit(1)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.tenant import Tenant

PHONE_NUMBER = "+12816990999"
TELNYX_AGENT_ID = "assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d"


async def show_current_state(db):
    """Display current configuration for both tenants."""
    print("\n" + "=" * 70)
    print("CURRENT STATE")
    print("=" * 70)

    for tid in [1, 2]:
        tenant = await db.execute(select(Tenant).where(Tenant.id == tid))
        tenant = tenant.scalar_one_or_none()

        sms_cfg = await db.execute(select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tid))
        sms_cfg = sms_cfg.scalar_one_or_none()

        voice_cfg = await db.execute(select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == tid))
        voice_cfg = voice_cfg.scalar_one_or_none()

        print(f"\nTenant {tid}: {tenant.name if tenant else 'NOT FOUND'}")
        if sms_cfg:
            print(f"  SMS Config:")
            print(f"    provider: {sms_cfg.provider}")
            print(f"    telnyx_phone_number: {sms_cfg.telnyx_phone_number}")
            print(f"    voice_phone_number: {sms_cfg.voice_phone_number}")
            print(f"    telnyx_api_key: {'[SET]' if sms_cfg.telnyx_api_key else '[NOT SET]'}")
            print(f"    telnyx_messaging_profile_id: {sms_cfg.telnyx_messaging_profile_id or '[NOT SET]'}")
            print(f"    telnyx_connection_id: {sms_cfg.telnyx_connection_id or '[NOT SET]'}")
        else:
            print(f"  SMS Config: NOT FOUND")

        if voice_cfg:
            print(f"  Voice Config:")
            print(f"    is_enabled: {voice_cfg.is_enabled}")
            print(f"    telnyx_agent_id: {voice_cfg.telnyx_agent_id or '[NOT SET]'}")
        else:
            print(f"  Voice Config: NOT FOUND")


async def reassign_phone():
    """Reassign phone number from Tenant 2 to Tenant 1."""
    print("=" * 70)
    print("REASSIGN +12816990999 TO TENANT 1 (ConvoPro)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        # Show current state
        await show_current_state(db)

        # Get Tenant 2's config (source)
        t2_sms = await db.execute(select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 2))
        t2_sms = t2_sms.scalar_one_or_none()

        t2_voice = await db.execute(select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == 2))
        t2_voice = t2_voice.scalar_one_or_none()

        if not t2_sms:
            print("\nERROR: Tenant 2 SMS config not found!")
            return

        # Get Tenant 1's config (destination)
        t1_sms = await db.execute(select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 1))
        t1_sms = t1_sms.scalar_one_or_none()

        t1_voice = await db.execute(select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == 1))
        t1_voice = t1_voice.scalar_one_or_none()

        print("\n" + "-" * 70)
        print("PLANNED CHANGES")
        print("-" * 70)
        print("\nTenant 1 (ConvoPro) will receive:")
        print(f"  telnyx_phone_number: {t1_sms.telnyx_phone_number if t1_sms else 'N/A'} -> {PHONE_NUMBER}")
        print(f"  voice_phone_number: {t1_sms.voice_phone_number if t1_sms else 'N/A'} -> {PHONE_NUMBER}")
        print(f"  telnyx_api_key: [COPY FROM TENANT 2]")
        print(f"  telnyx_messaging_profile_id: {t2_sms.telnyx_messaging_profile_id}")
        print(f"  telnyx_connection_id: {t2_sms.telnyx_connection_id}")
        print(f"  telnyx_agent_id: {TELNYX_AGENT_ID}")
        print(f"  provider: telnyx")
        print(f"  is_enabled: True")
        print(f"  voice_enabled: True")

        if "--yes" not in sys.argv:
            confirm = input("\nProceed with these changes? (yes/no): ")
            if confirm.lower() != "yes":
                print("Aborted.")
                return
        else:
            print("\n--yes flag provided, proceeding...")

        # Update Tenant 1 SMS config
        if not t1_sms:
            print("\nCreating SMS config for Tenant 1...")
            t1_sms = TenantSmsConfig(tenant_id=1)
            db.add(t1_sms)

        t1_sms.provider = "telnyx"
        t1_sms.is_enabled = True
        t1_sms.telnyx_phone_number = PHONE_NUMBER
        t1_sms.voice_phone_number = PHONE_NUMBER
        t1_sms.voice_enabled = True
        t1_sms.telnyx_api_key = t2_sms.telnyx_api_key
        t1_sms.telnyx_messaging_profile_id = t2_sms.telnyx_messaging_profile_id
        t1_sms.telnyx_connection_id = t2_sms.telnyx_connection_id
        print("Updated Tenant 1 SMS config")

        # Update Tenant 1 Voice config
        if not t1_voice:
            print("Creating Voice config for Tenant 1...")
            t1_voice = TenantVoiceConfig(tenant_id=1)
            db.add(t1_voice)

        t1_voice.is_enabled = True
        t1_voice.telnyx_agent_id = TELNYX_AGENT_ID
        print("Updated Tenant 1 Voice config")

        await db.commit()

        # Show final state
        print("\n" + "=" * 70)
        print("CHANGES COMPLETE")
        print("=" * 70)
        await show_current_state(db)

        print("\n" + "=" * 70)
        print("NEXT STEPS")
        print("=" * 70)
        print("1. Update CLAUDE.md to reflect the new phone assignment")
        print("2. In Telnyx Mission Control, verify the phone number routing")
        print("3. Test an inbound call to +1-281-699-0999")
        print("4. Enable call recording in the Telnyx AI Assistant settings")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(reassign_phone())
