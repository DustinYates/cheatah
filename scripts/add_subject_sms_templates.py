"""Add subject-specific SMS templates for tenant 3 (BSS Cypress-Spring).

This script adds followup_subject_templates to the tenant's SMS config,
allowing different SMS messages based on the email subject line that triggered the lead.
"""

import asyncio
import json
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Subject-specific SMS templates
SUBJECT_TEMPLATES = {
    "Get In Touch": (
        "Hi, {first_name}. Thank you for reaching out to British Swim School. "
        "I can answer any questions you have about our swim program including "
        "selecting a level, selecting a location, pricing, etc… "
        "Let me know how I can best assist you today."
    ),
    "Email Capture from Booking Page": (
        "Hi, {first_name}. You are just one step away from finishing the swim "
        "registration at British Swim School. I can help answer any questions "
        "you have so that we can be sure you get that spot."
    ),
}


async def add_subject_templates():
    """Add subject-specific SMS templates for tenant 3."""
    print("=" * 70)
    print("ADD SUBJECT-SPECIFIC SMS TEMPLATES FOR TENANT 3")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Get current config for tenant 3
        result = await db.execute(
            text("SELECT id, tenant_id, settings FROM tenant_sms_configs WHERE tenant_id = 3")
        )
        row = result.fetchone()

        if not row:
            print("ERROR: No SMS config found for tenant 3")
            return

        config_id, tenant_id, current_settings = row
        print(f"Found SMS config: id={config_id}, tenant_id={tenant_id}")

        # Parse current settings
        if current_settings is None:
            settings = {}
        elif isinstance(current_settings, str):
            settings = json.loads(current_settings)
        else:
            settings = current_settings

        print("\nCurrent settings:")
        print(json.dumps(settings, indent=2))

        # Add the subject templates
        settings["followup_subject_templates"] = SUBJECT_TEMPLATES

        print("\nNew settings (with subject templates):")
        print(json.dumps(settings, indent=2))

        # Confirm
        response = input("\nApply these changes? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

        # Update the database
        await db.execute(
            text("UPDATE tenant_sms_configs SET settings = :settings WHERE id = :id"),
            {"settings": json.dumps(settings), "id": config_id},
        )
        await db.commit()

        print("\n✅ Subject-specific SMS templates added successfully!")
        print("\nTemplates configured:")
        for subject, template in SUBJECT_TEMPLATES.items():
            print(f"\n  Subject: '{subject}'")
            print(f"  Message: {template[:80]}...")


if __name__ == "__main__":
    asyncio.run(add_subject_templates())
