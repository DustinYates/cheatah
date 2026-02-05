"""Quick read-only check of tenant 3 SMS configuration.

Run with: python scripts/check_tenant3_sms_config.py

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
        try:
            import subprocess
            result = subprocess.run(
                ["gcloud", "secrets", "versions", "access", "latest",
                 "--secret=DATABASE_URL", "--project=chattercheetah"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                db_url = result.stdout.strip()
        except Exception:
            pass

    if not db_url:
        print("ERROR: No DATABASE_URL available!")
        sys.exit(1)

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return db_url


async def check_config():
    """Check tenant 3 SMS configuration (read-only)."""
    print("=" * 60)
    print("TENANT 3 SMS CONFIG CHECK (READ-ONLY)")
    print("=" * 60)
    print()

    db_url = get_database_url()
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.persistence.models.tenant_sms_config import TenantSmsConfig
    from app.persistence.models.tenant import Tenant

    async with AsyncSessionLocal() as db:
        # Get tenant 3
        tenant_stmt = select(Tenant).where(Tenant.id == 3)
        tenant_result = await db.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            print("ERROR: Tenant 3 not found!")
            return

        print(f"Tenant: {tenant.name} (ID: {tenant.id})")
        print()

        # Get SMS config
        config_stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == 3)
        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            print("ERROR: No TenantSmsConfig for tenant 3!")
            print()
            print("Run: python scripts/fix_tenant3_sms_config.py")
            return

        # Display status with pass/fail indicators
        print("SMS Configuration:")
        print("-" * 60)

        # Critical checks for SMS registration links to work
        checks = []

        # 1. is_enabled
        status = "PASS" if config.is_enabled else "FAIL"
        checks.append(config.is_enabled)
        print(f"  [{status}] is_enabled = {config.is_enabled}")
        if not config.is_enabled:
            print("         ^ SMS provider will return None!")

        # 2. provider
        print(f"  [INFO] provider = {config.provider}")

        # 3. API key
        has_key = bool(config.telnyx_api_key)
        status = "PASS" if has_key else "FAIL"
        checks.append(has_key)
        print(f"  [{status}] telnyx_api_key = {'SET' if has_key else 'MISSING'}")

        # 4. Messaging profile
        has_profile = bool(config.telnyx_messaging_profile_id)
        status = "PASS" if has_profile else "WARN"
        print(f"  [{status}] telnyx_messaging_profile_id = {config.telnyx_messaging_profile_id or 'NOT SET'}")

        # 5. Phone number
        has_phone = bool(config.telnyx_phone_number)
        status = "PASS" if has_phone else "WARN"
        print(f"  [{status}] telnyx_phone_number = {config.telnyx_phone_number or 'NOT SET'}")

        # 6. Voice enabled
        status = "PASS" if config.voice_enabled else "WARN"
        print(f"  [{status}] voice_enabled = {config.voice_enabled}")

        # 7. Voice phone
        print(f"  [INFO] voice_phone_number = {config.voice_phone_number or 'NOT SET'}")

        print()
        print("=" * 60)

        # Summary
        critical_pass = all(checks)
        if critical_pass:
            print("RESULT: All critical checks PASSED")
            print()
            print("If SMS still not sending, check server logs for:")
            print("  - '[SMS-MESSAGES] No conversation ID available'")
            print("  - '[SMS-DEBUG] is_registration_request=False'")
            print("  - '[SMS] Skipping - already sent'")
        else:
            print("RESULT: Critical checks FAILED")
            print()
            print("Run: python scripts/fix_tenant3_sms_config.py")

        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_config())
