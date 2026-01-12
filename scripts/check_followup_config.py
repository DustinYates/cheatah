"""Check follow-up SMS configuration for a tenant."""

import asyncio
import logging
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Add parent directory to path
sys.path.insert(0, '/Users/dustinyates/Desktop/chattercheetah')

from app.settings import settings
from app.persistence.models.tenant_sms_config import TenantSmsConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_followup_config(tenant_id: int = 3):
    """Check follow-up configuration for tenant."""

    # Create async engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        # Get SMS config
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            print(f"❌ No SMS config found for tenant {tenant_id}")
            return

        print(f"\n{'='*60}")
        print(f"Follow-Up SMS Configuration for Tenant {tenant_id}")
        print(f"{'='*60}\n")

        print(f"✅ SMS Enabled: {config.is_enabled}")
        print(f"✅ Provider: {config.provider}")

        if config.provider == "telnyx":
            print(f"✅ Phone Number: {config.telnyx_phone_number or '❌ NOT SET'}")
        else:
            print(f"✅ Phone Number: {config.twilio_phone_number or '❌ NOT SET'}")

        print(f"\n{'─'*60}\n")

        if config.settings:
            followup_enabled = config.settings.get("followup_enabled", False)
            followup_sources = config.settings.get("followup_sources", ["voice_call", "sms", "email"])
            followup_delay = config.settings.get("followup_delay_minutes", 5)

            print(f"Follow-Up Enabled: {followup_enabled} {'✅' if followup_enabled else '❌ DISABLED'}")
            print(f"Follow-Up Sources: {followup_sources}")
            print(f"  - Email allowed: {'✅ Yes' if 'email' in followup_sources else '❌ No'}")
            print(f"  - SMS allowed: {'✅ Yes' if 'sms' in followup_sources else '❌ No'}")
            print(f"  - Voice allowed: {'✅ Yes' if 'voice_call' in followup_sources else '❌ No'}")
            print(f"Follow-Up Delay: {followup_delay} minutes")
        else:
            print("❌ No settings configured (settings field is NULL)")

        print(f"\n{'─'*60}\n")

        # Check environment variable
        worker_url = settings.cloud_tasks_worker_url
        print(f"CLOUD_TASKS_WORKER_URL: {worker_url or '❌ NOT SET'}")

        print(f"\n{'='*60}\n")

        # Summary
        issues = []
        if not config.is_enabled:
            issues.append("SMS is not enabled")
        if not config.settings:
            issues.append("Settings not configured")
        elif not config.settings.get("followup_enabled"):
            issues.append("Follow-up is not enabled in settings")
        elif 'email' not in config.settings.get("followup_sources", []):
            issues.append("Email is not in allowed follow-up sources")
        if not worker_url:
            issues.append("CLOUD_TASKS_WORKER_URL environment variable not set")
        if config.provider == "telnyx" and not config.telnyx_phone_number:
            issues.append("Telnyx phone number not configured")
        elif config.provider != "telnyx" and not config.twilio_phone_number:
            issues.append("Twilio phone number not configured")

        if issues:
            print("⚠️  ISSUES FOUND:\n")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")
            print()
        else:
            print("✅ Configuration looks good! Follow-up SMS should work for email leads.\n")

    await engine.dispose()


if __name__ == "__main__":
    tenant_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(check_followup_config(tenant_id))
