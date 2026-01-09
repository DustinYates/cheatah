"""Check SMS delivery status."""

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

# Message IDs from the test
MESSAGE_IDS = {
    1: "40319b9e-fc1c-4c56-bbd2-f8f2fbc8e8af",
    3: "40319b9e-fc20-41c5-b792-9cff5c6ff4b4",
}


async def check_status():
    """Check SMS delivery status."""
    print("=" * 70)
    print("SMS DELIVERY STATUS CHECK")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        for tenant_id, message_id in MESSAGE_IDS.items():
            print(f"Tenant {tenant_id} - Message ID: {message_id}")
            print("-" * 50)

            # Get tenant config
            sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            if sms_config and sms_config.telnyx_api_key:
                provider = TelnyxSmsProvider(
                    api_key=sms_config.telnyx_api_key,
                    messaging_profile_id=sms_config.telnyx_messaging_profile_id,
                )

                try:
                    message = await provider.get_message(message_id)
                    if message:
                        print(f"  Status: {message.get('status', 'unknown')}")
                        print(f"  To: {message.get('to')}")
                        print(f"  From: {message.get('from')}")
                        print(f"  Created: {message.get('created_at')}")

                        status = message.get('status', '').lower()
                        if status == 'delivered':
                            print(f"  ✅ MESSAGE DELIVERED!")
                        elif status == 'sent':
                            print(f"  📤 Message sent, awaiting delivery confirmation")
                        elif status == 'queued':
                            print(f"  ⏳ Message queued for sending")
                        elif status in ['failed', 'undelivered']:
                            print(f"  ❌ MESSAGE FAILED!")
                        else:
                            print(f"  📋 Status: {status}")
                    else:
                        print(f"  ⚠️ Could not retrieve message details")
                except Exception as e:
                    print(f"  ❌ Error checking status: {e}")
            else:
                print(f"  ❌ No API key found")

            print()

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(check_status())
