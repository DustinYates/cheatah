"""Fix tenant 3 phone services - diagnose and enable voice like tenant 1."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant


async def diagnose_and_fix():
    """Diagnose tenant voice configurations and fix tenant 3."""
    print("=" * 70)
    print("TENANT PHONE SERVICES DIAGNOSTIC & FIX")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Step 1: Query both tenants
        print("STEP 1: Querying tenant configurations...")
        print("-" * 70)

        for tenant_id in [1, 3]:
            # Get tenant info
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            # Get telephony config
            config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            config_result = await db.execute(config_stmt)
            config = config_result.scalar_one_or_none()

            print(f"\nTenant {tenant_id}:")
            if tenant:
                print(f"  Name: {tenant.name}")
                print(f"  Subdomain: {tenant.subdomain}")
                print(f"  Active: {tenant.is_active}")
            else:
                print(f"  ❌ Tenant not found!")
                continue

            if config:
                print(f"  TenantSmsConfig ID: {config.id}")
                print(f"  Provider: {config.provider}")
                print(f"  SMS Enabled: {config.is_enabled}")
                print(f"  Voice Enabled: {config.voice_enabled}")
                print(f"  Voice Phone Number: {config.voice_phone_number or 'NOT SET'}")

                # Check credentials (without exposing them)
                if config.provider == "twilio":
                    has_creds = bool(config.twilio_account_sid and config.twilio_auth_token)
                    print(f"  Has Twilio Credentials: {has_creds}")
                    print(f"  Twilio Phone: {config.twilio_phone_number or 'NOT SET'}")
                elif config.provider == "telnyx":
                    has_creds = bool(config.telnyx_api_key)
                    print(f"  Has Telnyx Credentials: {has_creds}")
                    print(f"  Telnyx Phone: {config.telnyx_phone_number or 'NOT SET'}")
            else:
                print(f"  ❌ No TenantSmsConfig found!")

        # Step 2: Get tenant 1 config as reference
        print()
        print("=" * 70)
        print("STEP 2: Fixing Tenant 3 Voice Configuration")
        print("-" * 70)

        # Get tenant 1 config
        t1_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 1)
        t1_result = await db.execute(t1_stmt)
        t1_config = t1_result.scalar_one_or_none()

        # Get tenant 3 config
        t3_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        t3_result = await db.execute(t3_stmt)
        t3_config = t3_result.scalar_one_or_none()

        if not t1_config:
            print("❌ Cannot proceed - tenant 1 has no telephony config!")
            return

        if not t1_config.voice_enabled:
            print("⚠️  Warning: Tenant 1 also doesn't have voice enabled!")
            return

        if t3_config:
            # Update existing config
            print(f"\nUpdating tenant 3 config (ID: {t3_config.id})...")

            changes = []

            if not t3_config.voice_enabled:
                t3_config.voice_enabled = True
                changes.append("voice_enabled: False → True")

            if not t3_config.voice_phone_number and t1_config.voice_phone_number:
                # Copy voice phone from tenant 1 (they may share, or admin should update)
                t3_config.voice_phone_number = t1_config.voice_phone_number
                changes.append(f"voice_phone_number: None → {t1_config.voice_phone_number}")

            # Ensure provider credentials match tenant 1's provider
            if t3_config.provider != t1_config.provider:
                t3_config.provider = t1_config.provider
                changes.append(f"provider: {t3_config.provider} → {t1_config.provider}")

            # Copy credentials from tenant 1 if tenant 3 is missing them
            if t1_config.provider == "twilio":
                if not t3_config.twilio_account_sid and t1_config.twilio_account_sid:
                    t3_config.twilio_account_sid = t1_config.twilio_account_sid
                    changes.append("twilio_account_sid: copied from tenant 1")
                if not t3_config.twilio_auth_token and t1_config.twilio_auth_token:
                    t3_config.twilio_auth_token = t1_config.twilio_auth_token
                    changes.append("twilio_auth_token: copied from tenant 1")
                if not t3_config.twilio_phone_number and t1_config.twilio_phone_number:
                    t3_config.twilio_phone_number = t1_config.twilio_phone_number
                    changes.append(f"twilio_phone_number: copied from tenant 1")
            elif t1_config.provider == "telnyx":
                if not t3_config.telnyx_api_key and t1_config.telnyx_api_key:
                    t3_config.telnyx_api_key = t1_config.telnyx_api_key
                    changes.append("telnyx_api_key: copied from tenant 1")
                if not t3_config.telnyx_connection_id and t1_config.telnyx_connection_id:
                    t3_config.telnyx_connection_id = t1_config.telnyx_connection_id
                    changes.append("telnyx_connection_id: copied from tenant 1")
                if not t3_config.telnyx_phone_number and t1_config.telnyx_phone_number:
                    t3_config.telnyx_phone_number = t1_config.telnyx_phone_number
                    changes.append("telnyx_phone_number: copied from tenant 1")

            if changes:
                print("\nChanges to apply:")
                for change in changes:
                    print(f"  • {change}")

                await db.commit()
                print("\n✅ Tenant 3 voice configuration updated!")
            else:
                print("\n✅ Tenant 3 already has correct voice configuration!")

        else:
            # Create new config for tenant 3 based on tenant 1
            print("\nCreating new TenantSmsConfig for tenant 3...")

            new_config = TenantSmsConfig(
                tenant_id=3,
                provider=t1_config.provider,
                is_enabled=t1_config.is_enabled,
                voice_enabled=True,  # Enable voice
                voice_phone_number=t1_config.voice_phone_number,
                # Copy Twilio credentials
                twilio_account_sid=t1_config.twilio_account_sid,
                twilio_auth_token=t1_config.twilio_auth_token,
                twilio_phone_number=t1_config.twilio_phone_number,
                # Copy Telnyx credentials
                telnyx_api_key=t1_config.telnyx_api_key,
                telnyx_messaging_profile_id=t1_config.telnyx_messaging_profile_id,
                telnyx_connection_id=t1_config.telnyx_connection_id,
                telnyx_phone_number=t1_config.telnyx_phone_number,
                # Copy business hours settings
                business_hours_enabled=t1_config.business_hours_enabled,
                timezone=t1_config.timezone,
                business_hours=t1_config.business_hours,
            )

            db.add(new_config)
            await db.commit()
            await db.refresh(new_config)

            print(f"✅ Created TenantSmsConfig for tenant 3 (ID: {new_config.id})")
            print(f"   Provider: {new_config.provider}")
            print(f"   Voice Enabled: {new_config.voice_enabled}")
            print(f"   Voice Phone: {new_config.voice_phone_number}")

        # Step 3: Verify the fix
        print()
        print("=" * 70)
        print("STEP 3: Verifying Fix")
        print("-" * 70)

        # Re-query tenant 3
        verify_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        verify_result = await db.execute(verify_stmt)
        verified_config = verify_result.scalar_one_or_none()

        if verified_config and verified_config.voice_enabled:
            print("\n✅ SUCCESS: Tenant 3 now has phone services enabled!")
            print(f"   Voice Enabled: {verified_config.voice_enabled}")
            print(f"   Voice Phone: {verified_config.voice_phone_number}")
            print(f"   Provider: {verified_config.provider}")
        else:
            print("\n❌ FAILED: Tenant 3 still doesn't have voice enabled!")

        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(diagnose_and_fix())
