"""Check prompt configuration for Tenant 3.

Usage:
    DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/check_tenant3_prompts.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not PROD_DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    sys.exit(1)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

TENANT_ID = 3


async def check_prompts():
    """Check prompt bundles for Tenant 3."""
    print("=" * 60)
    print("TENANT 3 PROMPT CONFIGURATION")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # Get prompt bundles
        result = await db.execute(text("""
            SELECT id, name, channel, status, is_active, version
            FROM prompt_bundles
            WHERE tenant_id = :tid
            ORDER BY channel, id DESC
        """), {"tid": TENANT_ID})

        rows = result.fetchall()
        print(f"\nPrompt bundles for Tenant {TENANT_ID}:")
        for row in rows:
            id, name, channel, status, is_active, version = row
            active_marker = " [ACTIVE]" if is_active else ""
            print(f"  {id}: {name}")
            print(f"      Channel: {channel}, Status: {status}, Version: {version}{active_marker}")

        # Check for web/chat specific prompt
        web_result = await db.execute(text("""
            SELECT pb.id, pb.name, ps.section_key, LEFT(ps.content, 500) as content_preview
            FROM prompt_bundles pb
            JOIN prompt_sections ps ON ps.bundle_id = pb.id
            WHERE pb.tenant_id = :tid
            AND pb.channel = 'web'
            AND pb.is_active = true
            ORDER BY ps.order
        """), {"tid": TENANT_ID})

        web_rows = web_result.fetchall()
        if web_rows:
            print(f"\n\nActive WEB prompt sections:")
            for row in web_rows:
                id, name, section_key, preview = row
                print(f"\n  Section: {section_key}")
                print(f"  Preview: {preview[:200]}...")
        else:
            print("\n\nNo active WEB prompt found!")
            print("The chatbot may be using a fallback or shared prompt.")


if __name__ == "__main__":
    asyncio.run(check_prompts())
