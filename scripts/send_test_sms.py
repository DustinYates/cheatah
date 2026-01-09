"""Send test SMS to specific number."""

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

from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

# Target number
TO_NUMBER = "+12816278851"
TENANT_ID = 3


async def send_sms():
    """Send test SMS from tenant 3."""
    print("=" * 70)
    print(f"SENDING TEST SMS TO {TO_NUMBER}")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Get tenant 3 config
        sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == TENANT_ID)
        sms_result = await db.execute(sms_stmt)
        sms_config = sms_result.scalar_one_or_none()

        if not sms_config:
            print("❌ No SMS config found for tenant 3!")
            return

        print(f"From: {sms_config.telnyx_phone_number}")
        print(f"To: {TO_NUMBER}")
        print()

        provider = TelnyxSmsProvider(
            api_key=sms_config.telnyx_api_key,
            messaging_profile_id=sms_config.telnyx_messaging_profile_id,
        )

        try:
            result = await provider.send_sms(
                to=TO_NUMBER,
                from_=sms_config.telnyx_phone_number,
                body="Hello! This is a test message from BSS Cypress-Spring. Reply STOP to opt out.",
            )
            print(f"✅ SMS sent successfully!")
            print(f"   Message ID: {result.message_id}")
            print(f"   Status: {result.status}")
        except Exception as e:
            print(f"❌ SMS send failed: {e}")

    print()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(send_sms())
