"""Check and fix tenant 3 naming consistency across ALL tables."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = PROD_DATABASE_URL

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Import all models that might have tenant-related names
from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.prompt import PromptBundle

CORRECT_NAME = "BSS Cypress-Spring"
TENANT_ID = 3


async def check_and_fix():
    """Check all tenant 3 related records for naming consistency."""
    print("=" * 70)
    print("TENANT 3 NAMING CONSISTENCY CHECK")
    print("=" * 70)
    print(f"Correct name: '{CORRECT_NAME}'")
    print()

    async with AsyncSessionLocal() as db:
        fixes_made = []

        # 1. Check Tenant table
        print("1. Tenant table:")
        tenant_stmt = select(Tenant).where(Tenant.id == TENANT_ID)
        result = await db.execute(tenant_stmt)
        tenant = result.scalar_one_or_none()
        if tenant:
            if tenant.name != CORRECT_NAME:
                print(f"   ❌ name: '{tenant.name}' → '{CORRECT_NAME}'")
                tenant.name = CORRECT_NAME
                fixes_made.append("Tenant.name")
            else:
                print(f"   ✅ name: '{tenant.name}'")
        else:
            print("   ⚠️  Tenant 3 not found!")

        # 2. Check TenantBusinessProfile
        print("\n2. TenantBusinessProfile table:")
        profile_stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == TENANT_ID)
        result = await db.execute(profile_stmt)
        profile = result.scalar_one_or_none()
        if profile:
            if profile.business_name and profile.business_name != CORRECT_NAME:
                print(f"   ❌ business_name: '{profile.business_name}' → '{CORRECT_NAME}'")
                profile.business_name = CORRECT_NAME
                fixes_made.append("TenantBusinessProfile.business_name")
            elif profile.business_name:
                print(f"   ✅ business_name: '{profile.business_name}'")
            else:
                print(f"   ⚠️  business_name is NULL, setting to '{CORRECT_NAME}'")
                profile.business_name = CORRECT_NAME
                fixes_made.append("TenantBusinessProfile.business_name")
        else:
            print("   ⚠️  No business profile found for tenant 3")

        # 3. Check TenantVoiceConfig
        print("\n3. TenantVoiceConfig table:")
        voice_stmt = select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == TENANT_ID)
        result = await db.execute(voice_stmt)
        voice_config = result.scalar_one_or_none()
        if voice_config:
            print(f"   ✅ Found voice config (ID: {voice_config.id})")
            print(f"      is_enabled: {voice_config.is_enabled}")
            print(f"      handoff_mode: {voice_config.handoff_mode}")
        else:
            print("   ⚠️  No voice config found for tenant 3")

        # 4. Check PromptBundles
        print("\n4. PromptBundle table:")
        prompt_stmt = select(PromptBundle).where(PromptBundle.tenant_id == TENANT_ID)
        result = await db.execute(prompt_stmt)
        bundles = result.scalars().all()
        if bundles:
            for bundle in bundles:
                print(f"   • Bundle ID {bundle.id}: '{bundle.name}' (status: {bundle.status})")
                # Check if bundle name contains old/incorrect tenant name
                if "cypress" in bundle.name.lower() or "bss" in bundle.name.lower():
                    if bundle.name != f"{CORRECT_NAME} Prompt Bundle":
                        # Only fix if it's the main bundle, not custom named ones
                        pass
        else:
            print("   ⚠️  No prompt bundles found for tenant 3")

        # 5. List all tables with tenant_id column for reference
        print("\n5. Checking database tables with tenant_id...")
        tables_query = text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = 'tenant_id'
            AND table_schema = 'public'
            ORDER BY table_name
        """)
        result = await db.execute(tables_query)
        tables = result.fetchall()
        print(f"   Tables with tenant_id column:")
        for table_name, col in tables:
            # Count records for tenant 3
            count_query = text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = :tid")
            count_result = await db.execute(count_query, {"tid": TENANT_ID})
            count = count_result.scalar()
            if count > 0:
                print(f"   • {table_name}: {count} record(s)")

        # Commit fixes
        if fixes_made:
            await db.commit()
            print()
            print("=" * 70)
            print(f"✅ Fixed {len(fixes_made)} inconsistencies:")
            for fix in fixes_made:
                print(f"   • {fix}")
        else:
            print()
            print("=" * 70)
            print("✅ All tenant 3 names are consistent!")

        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(check_and_fix())
