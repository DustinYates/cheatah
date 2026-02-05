"""Setup Telnyx SMS configuration for BSS Cypress-Spring tenant.

Usage:
    uv run python scripts/setup_bss_telnyx.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_sms_config import TenantSmsConfig


# Configuration for BSS Cypress-Spring
TELNYX_CONFIG = {
    "tenant_name": "BSS Cypress-Spring",
    "tenant_id": 3,  # Adjust if needed - check database for actual tenant ID
    "provider": "telnyx",
    "telnyx_messaging_profile_id": "40019b95-2d35-4479-9483-4080ad07d86a",
    "telnyx_phone_number": "+12817679141",  # Updated 2026-02-05
    "is_enabled": True,
    "voice_enabled": False,  # Set to True if voice is needed
}


async def setup_telnyx_config():
    """Set up Telnyx SMS configuration for the tenant."""
    async with AsyncSessionLocal() as db:
        try:
            # First, try to find tenant by name
            result = await db.execute(
                select(Tenant).where(Tenant.name.ilike(f"%{TELNYX_CONFIG['tenant_name']}%"))
            )
            tenant = result.scalar_one_or_none()

            # If not found by name, try by ID
            if not tenant:
                result = await db.execute(
                    select(Tenant).where(Tenant.id == TELNYX_CONFIG["tenant_id"])
                )
                tenant = result.scalar_one_or_none()

            if not tenant:
                print(f"❌ Tenant not found!")
                print(f"   Searched for name containing: '{TELNYX_CONFIG['tenant_name']}'")
                print(f"   And tenant_id: {TELNYX_CONFIG['tenant_id']}")

                # List all tenants to help identify the correct one
                result = await db.execute(select(Tenant))
                all_tenants = result.scalars().all()
                print(f"\n   Available tenants:")
                for t in all_tenants:
                    print(f"   - ID: {t.id}, Name: {t.name}, Subdomain: {t.subdomain}")
                return

            print(f"✓ Found tenant: {tenant.name} (ID: {tenant.id})")

            # Check for existing SMS config
            result = await db.execute(
                select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant.id)
            )
            existing_config = result.scalar_one_or_none()

            if existing_config:
                print(f"\n⚠️  SMS config already exists for this tenant")
                print(f"   Current provider: {existing_config.provider}")
                print(f"   Current phone: {existing_config.telnyx_phone_number or existing_config.twilio_phone_number}")
                print(f"   Is enabled: {existing_config.is_enabled}")

                response = input("\nUpdate existing config? (y/n): ")
                if response.lower() != 'y':
                    print("Aborted.")
                    return

                # Update existing config
                existing_config.provider = TELNYX_CONFIG["provider"]
                existing_config.telnyx_messaging_profile_id = TELNYX_CONFIG["telnyx_messaging_profile_id"]
                existing_config.telnyx_phone_number = TELNYX_CONFIG["telnyx_phone_number"]
                existing_config.is_enabled = TELNYX_CONFIG["is_enabled"]
                existing_config.voice_enabled = TELNYX_CONFIG["voice_enabled"]

                await db.commit()
                print(f"\n✓ Updated SMS config for {tenant.name}")
            else:
                # Create new config
                sms_config = TenantSmsConfig(
                    tenant_id=tenant.id,
                    provider=TELNYX_CONFIG["provider"],
                    telnyx_messaging_profile_id=TELNYX_CONFIG["telnyx_messaging_profile_id"],
                    telnyx_phone_number=TELNYX_CONFIG["telnyx_phone_number"],
                    is_enabled=TELNYX_CONFIG["is_enabled"],
                    voice_enabled=TELNYX_CONFIG["voice_enabled"],
                )
                db.add(sms_config)
                await db.commit()
                print(f"\n✓ Created SMS config for {tenant.name}")

            # Display final configuration
            print(f"\n{'='*60}")
            print(f"TELNYX CONFIGURATION COMPLETE")
            print(f"{'='*60}")
            print(f"Tenant: {tenant.name} (ID: {tenant.id})")
            print(f"Provider: {TELNYX_CONFIG['provider']}")
            print(f"Messaging Profile ID: {TELNYX_CONFIG['telnyx_messaging_profile_id']}")
            print(f"Phone Number: {TELNYX_CONFIG['telnyx_phone_number']}")
            print(f"SMS Enabled: {TELNYX_CONFIG['is_enabled']}")
            print(f"Voice Enabled: {TELNYX_CONFIG['voice_enabled']}")
            print(f"\nNote: If you need to set a Telnyx API key, do so via the admin API")
            print(f"POST /api/v1/admin/telephony/config with telnyx_api_key field")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    print("="*60)
    print("BSS Cypress-Spring - Telnyx SMS Setup")
    print("="*60)
    asyncio.run(setup_telnyx_config())
