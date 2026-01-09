"""Create TenantVoiceConfig for tenant 3."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = PROD_DATABASE_URL

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.tenant_voice_config import TenantVoiceConfig


async def create_voice_config():
    """Create TenantVoiceConfig for tenant 3."""
    print("=" * 70)
    print("CREATE TENANT VOICE CONFIG FOR TENANT 3")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Check if tenant 1 has a voice config to use as template
        t1_stmt = select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == 1)
        t1_result = await db.execute(t1_stmt)
        t1_config = t1_result.scalar_one_or_none()

        # Check if tenant 3 already has one
        t3_stmt = select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == 3)
        t3_result = await db.execute(t3_stmt)
        t3_config = t3_result.scalar_one_or_none()

        if t3_config:
            print("✅ Tenant 3 already has a TenantVoiceConfig!")
            print(f"   ID: {t3_config.id}")
            print(f"   is_enabled: {t3_config.is_enabled}")
            print(f"   handoff_mode: {t3_config.handoff_mode}")
            return

        print("Creating TenantVoiceConfig for tenant 3...")

        if t1_config:
            print("Using tenant 1 config as template...")
            # Copy from tenant 1
            t3_config = TenantVoiceConfig(
                tenant_id=3,
                is_enabled=True,
                handoff_mode=t1_config.handoff_mode or "take_message",
                live_transfer_number=None,  # Tenant 3 specific
                default_greeting="Hello! Thank you for calling BSS Cypress-Spring. I'm an AI assistant here to help you. How can I assist you today?",
                disclosure_line=t1_config.disclosure_line or "This call may be recorded for quality and training purposes.",
                after_hours_message=t1_config.after_hours_message,
                escalation_rules=t1_config.escalation_rules,
            )
        else:
            print("Creating default voice config...")
            # Create default config
            t3_config = TenantVoiceConfig(
                tenant_id=3,
                is_enabled=True,
                handoff_mode="take_message",
                default_greeting="Hello! Thank you for calling BSS Cypress-Spring. I'm an AI assistant here to help you. How can I assist you today?",
                disclosure_line="This call may be recorded for quality and training purposes.",
                after_hours_message="Thank you for calling. We're currently outside our business hours. Please leave a message after the tone, and we'll get back to you as soon as possible.",
            )

        db.add(t3_config)
        await db.commit()
        await db.refresh(t3_config)

        print()
        print("✅ Created TenantVoiceConfig for tenant 3!")
        print(f"   ID: {t3_config.id}")
        print(f"   is_enabled: {t3_config.is_enabled}")
        print(f"   handoff_mode: {t3_config.handoff_mode}")
        print(f"   default_greeting: {t3_config.default_greeting[:50] if t3_config.default_greeting else 'N/A'}...")

        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_voice_config())
