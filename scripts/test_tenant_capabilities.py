"""Test SMS and Email capabilities for tenants 1 and 3."""

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

from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_email_config import TenantEmailConfig, EmailConversation
from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

# Test phone number - update this to your test number
TEST_PHONE_NUMBER = os.getenv("TEST_PHONE", "+12818364029")  # Default test number


async def test_capabilities():
    """Test SMS and email capabilities for both tenants."""
    print("=" * 70)
    print("TENANT CAPABILITIES TEST - SMS & EMAIL")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        for tenant_id in [1, 3]:
            # Get tenant info
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            if not tenant:
                print(f"\n❌ Tenant {tenant_id} not found!")
                continue

            print(f"\n{'='*70}")
            print(f"TENANT {tenant_id}: {tenant.name}")
            print(f"{'='*70}")

            # ============================================
            # SMS CAPABILITIES
            # ============================================
            print("\n📱 SMS CAPABILITIES")
            print("-" * 40)

            sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            if sms_config:
                print(f"  Provider: {sms_config.provider}")
                print(f"  SMS Enabled: {sms_config.is_enabled}")
                print(f"  Voice Enabled: {sms_config.voice_enabled}")
                print(f"  SMS Phone: {sms_config.telnyx_phone_number or sms_config.twilio_phone_number or 'NOT SET'}")
                print(f"  Voice Phone: {sms_config.voice_phone_number or 'NOT SET'}")
                print(f"  Connection ID: {sms_config.telnyx_connection_id or 'NOT SET'}")
                print(f"  Messaging Profile: {sms_config.telnyx_messaging_profile_id or 'NOT SET'}")
                print(f"  Has API Key: {bool(sms_config.telnyx_api_key or sms_config.twilio_auth_token)}")

                # Test SMS sending if enabled
                if sms_config.is_enabled and sms_config.provider == "telnyx":
                    if sms_config.telnyx_api_key and sms_config.telnyx_phone_number:
                        print(f"\n  🧪 Testing SMS send to {TEST_PHONE_NUMBER}...")
                        try:
                            provider = TelnyxSmsProvider(
                                api_key=sms_config.telnyx_api_key,
                                messaging_profile_id=sms_config.telnyx_messaging_profile_id,
                            )
                            result = await provider.send_sms(
                                to=TEST_PHONE_NUMBER,
                                from_=sms_config.telnyx_phone_number,
                                body=f"[TEST] SMS test from {tenant.name} (Tenant {tenant_id}). This is a test message.",
                            )
                            print(f"  ✅ SMS sent successfully!")
                            print(f"     Message ID: {result.message_id}")
                            print(f"     Status: {result.status}")
                        except Exception as e:
                            print(f"  ❌ SMS send failed: {e}")
                    else:
                        print(f"\n  ⚠️  Cannot test SMS - missing API key or phone number")
                else:
                    print(f"\n  ⚠️  SMS not enabled or not using Telnyx")
            else:
                print("  ❌ No SMS configuration found!")

            # ============================================
            # EMAIL CAPABILITIES
            # ============================================
            print("\n📧 EMAIL CAPABILITIES")
            print("-" * 40)

            email_stmt = select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
            email_result = await db.execute(email_stmt)
            email_config = email_result.scalar_one_or_none()

            if email_config:
                print(f"  Email Enabled: {email_config.is_enabled}")
                print(f"  Gmail Account: {email_config.gmail_email or 'NOT CONNECTED'}")
                print(f"  Has Refresh Token: {bool(email_config.gmail_refresh_token)}")
                print(f"  Has Access Token: {bool(email_config.gmail_access_token)}")
                print(f"  Token Expires: {email_config.gmail_token_expires_at or 'N/A'}")
                print(f"  Watch Expiration: {email_config.watch_expiration or 'N/A'}")
                print(f"  Last History ID: {email_config.last_history_id or 'N/A'}")
                print(f"  Business Hours Enabled: {email_config.business_hours_enabled}")
                print(f"  Auto-reply Outside Hours: {email_config.auto_reply_outside_hours}")

                # Check email conversation count
                conv_stmt = select(EmailConversation).where(EmailConversation.tenant_id == tenant_id)
                conv_result = await db.execute(conv_stmt)
                conversations = conv_result.scalars().all()
                print(f"\n  Email Conversations: {len(conversations)}")

                if conversations:
                    # Show last 3 email threads
                    print(f"  Recent email threads:")
                    for conv in sorted(conversations, key=lambda x: x.created_at, reverse=True)[:3]:
                        print(f"    • {conv.subject[:40]}... from {conv.from_email} ({conv.status})")

                # Test OAuth status
                if email_config.gmail_refresh_token:
                    print(f"\n  🧪 Gmail OAuth status:")
                    if email_config.gmail_access_token and email_config.gmail_token_expires_at:
                        from datetime import datetime
                        now = datetime.utcnow()
                        if email_config.gmail_token_expires_at > now:
                            print(f"  ✅ Access token valid until {email_config.gmail_token_expires_at}")
                        else:
                            print(f"  ⚠️  Access token expired, needs refresh")
                    else:
                        print(f"  ⚠️  No access token, needs OAuth refresh")
                else:
                    print(f"\n  ⚠️  Gmail not connected - OAuth flow required")
            else:
                print("  ❌ No email configuration found!")

        # ============================================
        # SUMMARY
        # ============================================
        print(f"\n{'='*70}")
        print("CAPABILITIES SUMMARY")
        print(f"{'='*70}")

        for tenant_id in [1, 3]:
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            sms_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            sms_result = await db.execute(sms_stmt)
            sms_config = sms_result.scalar_one_or_none()

            email_stmt = select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
            email_result = await db.execute(email_stmt)
            email_config = email_result.scalar_one_or_none()

            sms_ok = "✅" if sms_config and sms_config.is_enabled else "❌"
            voice_ok = "✅" if sms_config and sms_config.voice_enabled else "❌"
            email_ok = "✅" if email_config and email_config.is_enabled and email_config.gmail_refresh_token else "❌"

            print(f"\nTenant {tenant_id} ({tenant.name if tenant else 'Unknown'}):")
            print(f"  SMS: {sms_ok}  Voice: {voice_ok}  Email: {email_ok}")

        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_capabilities())
