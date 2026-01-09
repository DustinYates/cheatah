"""Setup TenantVoiceConfig for tenant 1 and tenant 3.

This script creates or verifies TenantVoiceConfig records for voice functionality
and ensures voice_enabled=True in TenantSmsConfig for both tenants.

Usage:
    python scripts/setup_voice_configs.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Production database URL
PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = PROD_DATABASE_URL

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant


TENANT_CONFIGS = [
    {
        "tenant_id": 1,
        "name": "Dustin Yates",
        "greeting": "Hello! Thank you for calling. I'm an AI assistant here to help you. How can I assist you today?",
    },
    {
        "tenant_id": 3,
        "name": "BSS Cypress-Spring",
        "greeting": "Hello! Thank you for calling BSS Cypress-Spring. I'm an AI assistant here to help you. How can I assist you today?",
    },
]


async def setup_voice_configs():
    """Create TenantVoiceConfig records and verify voice is enabled."""
    print("=" * 70)
    print("VOICE CONFIGURATION SETUP")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        for config in TENANT_CONFIGS:
            tenant_id = config["tenant_id"]
            tenant_name = config["name"]

            print(f"\n--- Tenant {tenant_id}: {tenant_name} ---")

            # Verify tenant exists
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                print(f"  ERROR: Tenant {tenant_id} not found in database!")
                continue

            print(f"  Tenant found: {tenant.name}")

            # Check/create TenantVoiceConfig
            voice_stmt = select(TenantVoiceConfig).where(
                TenantVoiceConfig.tenant_id == tenant_id
            )
            voice_result = await db.execute(voice_stmt)
            voice_config = voice_result.scalar_one_or_none()

            if voice_config:
                print(f"  TenantVoiceConfig exists (ID: {voice_config.id})")
                print(f"    is_enabled: {voice_config.is_enabled}")
                print(f"    handoff_mode: {voice_config.handoff_mode}")
                if not voice_config.is_enabled:
                    voice_config.is_enabled = True
                    print(f"    -> Enabled voice config")
            else:
                voice_config = TenantVoiceConfig(
                    tenant_id=tenant_id,
                    is_enabled=True,
                    handoff_mode="take_message",
                    default_greeting=config["greeting"],
                    disclosure_line="This call may be recorded for quality and training purposes.",
                    after_hours_message="Thank you for calling. We're currently outside our business hours. Please leave a message after the tone, and we'll get back to you as soon as possible.",
                    escalation_rules={
                        "caller_asks_human": True,
                        "repeated_confusion": {"enabled": True, "threshold": 3},
                        "high_value_intent": {"enabled": False},
                        "low_confidence": {"enabled": False},
                    },
                )
                db.add(voice_config)
                print(f"  Created TenantVoiceConfig")
                print(f"    is_enabled: True")
                print(f"    handoff_mode: take_message")
                print(f"    greeting: {config['greeting'][:50]}...")

            # Check/update TenantSmsConfig.voice_enabled
            sms_stmt = select(TenantSmsConfig).where(
                TenantSmsConfig.tenant_id == tenant_id
            )
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            if sms_config:
                print(f"  TenantSmsConfig found (ID: {sms_config.id})")
                print(f"    voice_enabled: {sms_config.voice_enabled}")
                print(f"    telnyx_phone_number: {sms_config.telnyx_phone_number or 'NOT SET'}")

                if not sms_config.voice_enabled:
                    sms_config.voice_enabled = True
                    print(f"    -> Set voice_enabled = True")
            else:
                print(f"  WARNING: No TenantSmsConfig found for tenant {tenant_id}")

        await db.commit()

        print()
        print("=" * 70)
        print("VERIFICATION")
        print("=" * 70)

        # Verify final state
        for config in TENANT_CONFIGS:
            tenant_id = config["tenant_id"]

            voice_stmt = select(TenantVoiceConfig).where(
                TenantVoiceConfig.tenant_id == tenant_id
            )
            voice_result = await db.execute(voice_stmt)
            voice_config = voice_result.scalar_one_or_none()

            sms_stmt = select(TenantSmsConfig).where(
                TenantSmsConfig.tenant_id == tenant_id
            )
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            voice_ok = voice_config and voice_config.is_enabled
            sms_ok = sms_config and sms_config.voice_enabled

            status = "OK" if voice_ok and sms_ok else "INCOMPLETE"
            print(f"\nTenant {tenant_id}: {status}")
            print(f"  TenantVoiceConfig.is_enabled: {voice_config.is_enabled if voice_config else 'MISSING'}")
            print(f"  TenantSmsConfig.voice_enabled: {sms_config.voice_enabled if sms_config else 'MISSING'}")
            print(f"  Telnyx Phone: {sms_config.telnyx_phone_number if sms_config else 'N/A'}")

        print()
        print("=" * 70)
        print("DONE - Voice configs are ready!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Configure Telnyx AI Assistant in portal.telnyx.com")
        print("2. Set dynamic variables webhook URL:")
        print("   https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/dynamic-variables")
        print("3. Assign phone numbers to the AI Assistant")
        print("4. Test by calling the phone numbers")


if __name__ == "__main__":
    asyncio.run(setup_voice_configs())
