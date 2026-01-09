"""Fix tenant 3 phone services in PRODUCTION database."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DATABASE_URL for production
PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = PROD_DATABASE_URL

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Convert to async URL
ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Import models after setting up custom engine
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant


async def diagnose_and_fix():
    """Diagnose and fix tenant 3 voice configuration in PRODUCTION."""
    print("=" * 70)
    print("PRODUCTION DATABASE - TENANT PHONE SERVICES DIAGNOSTIC & FIX")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Step 1: List all tenants
        print("STEP 1: All Tenants in Production")
        print("-" * 70)

        tenants_stmt = select(Tenant).order_by(Tenant.id)
        tenants_result = await db.execute(tenants_stmt)
        tenants = tenants_result.scalars().all()

        configs_stmt = select(TenantSmsConfig)
        configs_result = await db.execute(configs_stmt)
        configs = {c.tenant_id: c for c in configs_result.scalars().all()}

        print(f"{'ID':<4} {'Name':<30} {'Subdomain':<20} {'Active':<8} {'Voice':<8} {'Provider':<10}")
        print("-" * 90)

        for tenant in tenants:
            config = configs.get(tenant.id)
            voice_enabled = config.voice_enabled if config else False
            provider = config.provider if config else "N/A"

            print(f"{tenant.id:<4} {tenant.name[:28]:<30} {tenant.subdomain[:18]:<20} {str(tenant.is_active):<8} {str(voice_enabled):<8} {provider:<10}")

        print()
        print(f"Total tenants: {len(tenants)}")

        # Step 2: Detailed config for tenants 1 and 3
        print()
        print("=" * 70)
        print("STEP 2: Detailed Telephony Config for Tenants 1 and 3")
        print("-" * 70)

        for tenant_id in [1, 3]:
            tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
            tenant_result = await db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()

            config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            config_result = await db.execute(config_stmt)
            config = config_result.scalar_one_or_none()

            print(f"\nTenant {tenant_id}:")
            if tenant:
                print(f"  Name: {tenant.name}")
                print(f"  Subdomain: {tenant.subdomain}")
                print(f"  Active: {tenant.is_active}")
            else:
                print(f"  ❌ TENANT NOT FOUND!")
                continue

            if config:
                print(f"  TenantSmsConfig ID: {config.id}")
                print(f"  Provider: {config.provider}")
                print(f"  SMS Enabled: {config.is_enabled}")
                print(f"  Voice Enabled: {config.voice_enabled}")
                print(f"  Voice Phone: {config.voice_phone_number or 'NOT SET'}")

                if config.provider == "twilio":
                    print(f"  Twilio SID: {config.twilio_account_sid[:8] + '...' if config.twilio_account_sid else 'NOT SET'}")
                    print(f"  Twilio Phone: {config.twilio_phone_number or 'NOT SET'}")
                    print(f"  Has Auth Token: {bool(config.twilio_auth_token)}")
                elif config.provider == "telnyx":
                    print(f"  Telnyx API Key: {config.telnyx_api_key[:8] + '...' if config.telnyx_api_key else 'NOT SET'}")
                    print(f"  Telnyx Connection ID: {config.telnyx_connection_id or 'NOT SET'}")
                    print(f"  Telnyx Phone: {config.telnyx_phone_number or 'NOT SET'}")
            else:
                print(f"  ❌ NO TELEPHONY CONFIG!")

        # Step 3: Fix tenant 3
        print()
        print("=" * 70)
        print("STEP 3: Fixing Tenant 3")
        print("-" * 70)

        t1_config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 1)
        t1_config_result = await db.execute(t1_config_stmt)
        t1_config = t1_config_result.scalar_one_or_none()

        t3_config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        t3_config_result = await db.execute(t3_config_stmt)
        t3_config = t3_config_result.scalar_one_or_none()

        # Check tenant 3 exists
        t3_stmt = select(Tenant).where(Tenant.id == 3)
        t3_result = await db.execute(t3_stmt)
        t3_tenant = t3_result.scalar_one_or_none()

        if not t3_tenant:
            print("❌ Tenant 3 does not exist in production!")
            return

        if not t1_config:
            print("❌ Tenant 1 has no telephony config to copy from!")
            return

        if not t1_config.voice_enabled:
            print("⚠️  Tenant 1 doesn't have voice enabled either!")
            print("   Enabling voice for BOTH tenants...")

            # Enable voice for tenant 1
            t1_config.voice_enabled = True
            print("   ✓ Enabled voice for tenant 1")

        if t3_config:
            # Update existing config
            print(f"\nUpdating tenant 3 config...")
            changes = []

            if not t3_config.voice_enabled:
                t3_config.voice_enabled = True
                changes.append("voice_enabled: False → True")

            if not t3_config.voice_phone_number and t1_config.voice_phone_number:
                t3_config.voice_phone_number = t1_config.voice_phone_number
                changes.append(f"voice_phone_number: → {t1_config.voice_phone_number}")

            # Copy provider settings if missing
            if t3_config.provider != t1_config.provider:
                t3_config.provider = t1_config.provider
                changes.append(f"provider: → {t1_config.provider}")

            if t1_config.provider == "twilio":
                if not t3_config.twilio_account_sid:
                    t3_config.twilio_account_sid = t1_config.twilio_account_sid
                    changes.append("twilio_account_sid: copied")
                if not t3_config.twilio_auth_token:
                    t3_config.twilio_auth_token = t1_config.twilio_auth_token
                    changes.append("twilio_auth_token: copied")
                if not t3_config.twilio_phone_number:
                    t3_config.twilio_phone_number = t1_config.twilio_phone_number
                    changes.append(f"twilio_phone_number: → {t1_config.twilio_phone_number}")
            elif t1_config.provider == "telnyx":
                if not t3_config.telnyx_api_key:
                    t3_config.telnyx_api_key = t1_config.telnyx_api_key
                    changes.append("telnyx_api_key: copied")
                if not t3_config.telnyx_connection_id:
                    t3_config.telnyx_connection_id = t1_config.telnyx_connection_id
                    changes.append("telnyx_connection_id: copied")
                if not t3_config.telnyx_phone_number:
                    t3_config.telnyx_phone_number = t1_config.telnyx_phone_number
                    changes.append(f"telnyx_phone_number: → {t1_config.telnyx_phone_number}")

            if changes:
                print("\nChanges applied:")
                for change in changes:
                    print(f"  • {change}")
            else:
                # Just enable voice
                t3_config.voice_enabled = True
                print("  • voice_enabled: True")

        else:
            # Create new config
            print("\nCreating new TenantSmsConfig for tenant 3...")

            t3_config = TenantSmsConfig(
                tenant_id=3,
                provider=t1_config.provider,
                is_enabled=t1_config.is_enabled,
                voice_enabled=True,
                voice_phone_number=t1_config.voice_phone_number,
                twilio_account_sid=t1_config.twilio_account_sid,
                twilio_auth_token=t1_config.twilio_auth_token,
                twilio_phone_number=t1_config.twilio_phone_number,
                telnyx_api_key=t1_config.telnyx_api_key,
                telnyx_messaging_profile_id=t1_config.telnyx_messaging_profile_id,
                telnyx_connection_id=t1_config.telnyx_connection_id,
                telnyx_phone_number=t1_config.telnyx_phone_number,
                business_hours_enabled=t1_config.business_hours_enabled,
                timezone=t1_config.timezone,
            )
            db.add(t3_config)
            print(f"  ✓ Created config with voice_enabled=True")

        await db.commit()
        print("\n✅ Changes committed to production database!")

        # Step 4: Verify
        print()
        print("=" * 70)
        print("STEP 4: Verification")
        print("-" * 70)

        for tenant_id in [1, 3]:
            verify_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            verify_result = await db.execute(verify_stmt)
            verified = verify_result.scalar_one_or_none()

            if verified:
                status = "✅" if verified.voice_enabled else "❌"
                print(f"Tenant {tenant_id}: {status} voice_enabled={verified.voice_enabled}, phone={verified.voice_phone_number or 'N/A'}")
            else:
                print(f"Tenant {tenant_id}: ❌ No config found")

        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(diagnose_and_fix())
