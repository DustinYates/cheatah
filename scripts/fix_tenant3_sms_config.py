"""Diagnose and fix tenant 3 SMS configuration for registration link sending.

This script checks all the requirements for SMS registration links to work:
1. TenantSmsConfig exists for tenant 3
2. is_enabled = True (required for SMS provider to be created)
3. provider = "telnyx" with valid credentials
4. telnyx_api_key is set
5. telnyx_messaging_profile_id is set
6. telnyx_phone_number is set

Run with: python scripts/fix_tenant3_sms_config.py

For production, set DATABASE_URL environment variable first.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


def get_database_url() -> str:
    """Get database URL from environment or GCP secrets."""
    db_url = os.environ.get("DATABASE_URL", "")

    if not db_url:
        print("DATABASE_URL not set. Trying to fetch from GCP secrets...")
        try:
            import subprocess
            result = subprocess.run(
                ["gcloud", "secrets", "versions", "access", "latest",
                 "--secret=DATABASE_URL", "--project=chattercheetah"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                db_url = result.stdout.strip()
                print("Got DATABASE_URL from GCP secrets")
            else:
                print(f"Failed to get secret: {result.stderr}")
        except Exception as e:
            print(f"Could not fetch from GCP: {e}")

    if not db_url:
        print("ERROR: No DATABASE_URL available!")
        sys.exit(1)

    # Convert to async URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return db_url


async def diagnose_and_fix():
    """Diagnose and fix tenant 3 SMS configuration."""
    print("=" * 70)
    print("TENANT 3 SMS CONFIGURATION DIAGNOSTIC & FIX")
    print("=" * 70)
    print()

    db_url = get_database_url()
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Import models after setting up engine
    from app.persistence.models.tenant_sms_config import TenantSmsConfig
    from app.persistence.models.tenant import Tenant

    async with AsyncSessionLocal() as db:
        # Step 1: Check tenant 3 exists
        print("STEP 1: Checking Tenant 3 Exists")
        print("-" * 70)

        tenant_stmt = select(Tenant).where(Tenant.id == 3)
        tenant_result = await db.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            print("ERROR: Tenant 3 does not exist!")
            return

        print(f"  Tenant ID: {tenant.id}")
        print(f"  Name: {tenant.name}")
        print(f"  Subdomain: {tenant.subdomain}")
        print(f"  Active: {tenant.is_active}")
        print()

        # Step 2: Check TenantSmsConfig for tenant 3
        print("STEP 2: Checking TenantSmsConfig for Tenant 3")
        print("-" * 70)

        config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        issues = []

        if not config:
            print("  ERROR: No TenantSmsConfig found for tenant 3!")
            issues.append("no_config")
        else:
            print(f"  Config ID: {config.id}")
            print(f"  Provider: {config.provider}")
            print()

            # Check is_enabled (CRITICAL for SMS)
            print("  SMS Settings:")
            status = "OK" if config.is_enabled else "DISABLED"
            print(f"    is_enabled: {config.is_enabled} [{status}]")
            if not config.is_enabled:
                issues.append("sms_disabled")

            # Check voice_enabled
            status = "OK" if config.voice_enabled else "DISABLED"
            print(f"    voice_enabled: {config.voice_enabled} [{status}]")
            if not config.voice_enabled:
                issues.append("voice_disabled")

            print()
            print("  Telnyx Configuration:")

            # Check Telnyx API key
            has_api_key = bool(config.telnyx_api_key)
            status = "SET" if has_api_key else "MISSING"
            print(f"    telnyx_api_key: {status}")
            if not has_api_key and config.provider == "telnyx":
                issues.append("missing_api_key")

            # Check messaging profile ID
            has_profile = bool(config.telnyx_messaging_profile_id)
            status = config.telnyx_messaging_profile_id if has_profile else "NOT SET"
            print(f"    telnyx_messaging_profile_id: {status}")
            if not has_profile and config.provider == "telnyx":
                issues.append("missing_messaging_profile")

            # Check phone numbers
            print(f"    telnyx_phone_number: {config.telnyx_phone_number or 'NOT SET'}")
            print(f"    voice_phone_number: {config.voice_phone_number or 'NOT SET'}")

            if not config.telnyx_phone_number and config.provider == "telnyx":
                issues.append("missing_phone_number")

            # Check Telnyx connection ID (for voice)
            print(f"    telnyx_connection_id: {config.telnyx_connection_id or 'NOT SET'}")

        print()

        # Step 3: Summary and fix options
        print("STEP 3: Diagnosis Summary")
        print("-" * 70)

        if not issues:
            print("  All checks PASSED! Tenant 3 SMS config looks correct.")
            print()
            print("  If registration links still aren't sending, check:")
            print("    1. Server logs for '[FALLBACK]' or 'No SMS provider' messages")
            print("    2. Redis deduplication may be blocking (check for 'already sent' logs)")
            print("    3. The conversation ID may not be resolving for SMS events")
            return

        print(f"  Found {len(issues)} issue(s):")
        for issue in issues:
            if issue == "no_config":
                print("    - No TenantSmsConfig record exists")
            elif issue == "sms_disabled":
                print("    - is_enabled=False (SMS provider won't be created!)")
            elif issue == "voice_disabled":
                print("    - voice_enabled=False")
            elif issue == "missing_api_key":
                print("    - telnyx_api_key is missing (required for Telnyx provider)")
            elif issue == "missing_messaging_profile":
                print("    - telnyx_messaging_profile_id is missing")
            elif issue == "missing_phone_number":
                print("    - telnyx_phone_number is missing")

        print()

        # Step 4: Offer to fix
        print("STEP 4: Fix Options")
        print("-" * 70)

        if "no_config" in issues:
            print("  Cannot auto-fix: No config exists. Need to create one manually")
            print("  or copy from tenant 1. Run fix_tenant3_voice_prod.py first.")
            return

        # Check tenant 1 for reference values
        t1_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 1)
        t1_result = await db.execute(t1_stmt)
        t1_config = t1_result.scalar_one_or_none()

        fixable_issues = []

        if "sms_disabled" in issues:
            fixable_issues.append(("is_enabled", True, config.is_enabled))

        if "voice_disabled" in issues:
            fixable_issues.append(("voice_enabled", True, config.voice_enabled))

        if "missing_api_key" in issues and t1_config and t1_config.telnyx_api_key:
            fixable_issues.append(("telnyx_api_key", "[copy from tenant 1]", "MISSING"))

        if "missing_messaging_profile" in issues and t1_config and t1_config.telnyx_messaging_profile_id:
            fixable_issues.append(("telnyx_messaging_profile_id", t1_config.telnyx_messaging_profile_id, "MISSING"))

        if "missing_phone_number" in issues and t1_config and t1_config.telnyx_phone_number:
            fixable_issues.append(("telnyx_phone_number", t1_config.telnyx_phone_number, "MISSING"))

        if not fixable_issues:
            print("  No auto-fixable issues (missing source data from tenant 1)")
            return

        print("  Proposed fixes:")
        for field, new_val, old_val in fixable_issues:
            print(f"    {field}: {old_val} -> {new_val}")

        print()
        response = input("  Apply these fixes? [y/N]: ").strip().lower()

        if response != "y":
            print("  Aborted. No changes made.")
            return

        # Apply fixes
        print()
        print("STEP 5: Applying Fixes")
        print("-" * 70)

        changes = []

        if "sms_disabled" in issues:
            config.is_enabled = True
            changes.append("is_enabled: False -> True")

        if "voice_disabled" in issues:
            config.voice_enabled = True
            changes.append("voice_enabled: False -> True")

        if "missing_api_key" in issues and t1_config and t1_config.telnyx_api_key:
            config.telnyx_api_key = t1_config.telnyx_api_key
            changes.append("telnyx_api_key: copied from tenant 1")

        if "missing_messaging_profile" in issues and t1_config and t1_config.telnyx_messaging_profile_id:
            config.telnyx_messaging_profile_id = t1_config.telnyx_messaging_profile_id
            changes.append(f"telnyx_messaging_profile_id: {t1_config.telnyx_messaging_profile_id}")

        if "missing_phone_number" in issues and t1_config and t1_config.telnyx_phone_number:
            config.telnyx_phone_number = t1_config.telnyx_phone_number
            changes.append(f"telnyx_phone_number: {t1_config.telnyx_phone_number}")

        await db.commit()

        print("  Changes applied:")
        for change in changes:
            print(f"    {change}")

        print()
        print("  Verifying...")

        # Verify
        await db.refresh(config)
        print(f"    is_enabled: {config.is_enabled}")
        print(f"    voice_enabled: {config.voice_enabled}")
        print(f"    telnyx_api_key: {'SET' if config.telnyx_api_key else 'MISSING'}")
        print(f"    telnyx_messaging_profile_id: {config.telnyx_messaging_profile_id or 'NOT SET'}")
        print(f"    telnyx_phone_number: {config.telnyx_phone_number or 'NOT SET'}")

        print()
        print("=" * 70)
        print("FIX COMPLETE!")
        print()
        print("Next steps:")
        print("  1. Test by sending a text to the voice agent asking to register")
        print("  2. Check server logs for '[FALLBACK] SENDING SMS REGISTRATION LINK'")
        print("  3. If still failing, check for conversation ID resolution issues")
        print("=" * 70)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(diagnose_and_fix())
