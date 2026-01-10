"""Create a dedicated voice prompt bundle for tenant 3 (BSS Cypress-Spring).

This creates a voice-optimized version of the BSS Cypress-Spring prompt that:
- Is written specifically for spoken conversation
- Doesn't need the transform_chat_to_voice wrapper
- Contains the correct Texas location info

Usage:
    DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/create_tenant3_voice_prompt.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Get production database URL
PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not PROD_DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Run with:")
    print('  DATABASE_URL=$(gcloud secrets versions access latest --secret=database-url) uv run python scripts/create_tenant3_voice_prompt.py')
    sys.exit(1)

# Create async engine directly for production
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.persistence.models.prompt import PromptBundle, PromptChannel, PromptSection, PromptStatus, SectionScope
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.prompt_repository import PromptRepository


TENANT_ID = 3
TENANT_NAME = "BSS Cypress-Spring"

# Voice-optimized prompt sections for BSS Cypress-Spring
VOICE_PROMPT_SECTIONS = [
    {
        "section_key": "voice_identity",
        "scope": SectionScope.SYSTEM.value,
        "content": """You are a friendly voice assistant for British Swim School Cypress-Spring in Texas.
You help families learn about swim lessons and guide them toward enrollment.

CRITICAL LOCATION INFO:
You serve the Cypress and Spring areas in TEXAS, USA - NOT the UK.
British Swim School is the brand name, but this franchise is in Houston, Texas.""",
        "order": 0,
    },
    {
        "section_key": "voice_rules",
        "scope": SectionScope.BASE.value,
        "content": """VOICE CONVERSATION RULES:

How to Speak:
- Sound warm, friendly, and natural - like a helpful friend
- Keep responses short - two to four sentences max
- Ask only ONE question per turn
- Use contractions naturally: "we're", "you'll", "that's"
- Vary your phrasing - don't repeat the same words

CRITICAL - Only State Facts You Know:
- ONLY share information from the BUSINESS FACTS section below
- NEVER invent prices, schedules, or policies
- If unsure, say: "I don't have that specific detail, but I can take your info and have someone follow up."
- Better to admit you don't know than guess wrong

What NOT to Do:
- NEVER read URLs, email addresses, or links aloud
- NEVER use bullet points or numbered lists in speech
- NEVER say "at symbol" or spell out special characters
- For links or detailed info: "I can text that to you. What's the best number?"

Lead Capture:
- Ask for their name and email naturally during conversation
- Do NOT ask for phone number - you already have it from caller ID
- Don't make it feel like filling out a form""",
        "order": 1,
    },
    {
        "section_key": "voice_pool_locations",
        "scope": SectionScope.BUSINESS_INFO.value,
        "content": """POOL LOCATIONS (Houston, Texas area):

When asked about locations, describe them naturally:

LA Fitness Langham Creek - at 17800 FM 529 in Houston

LA Fitness Cypress - at 12304 Barker Cypress Road in Cypress

24 Hour Fitness Spring Energy - at 1000 Lake Plaza Drive in Spring

All pools are indoor and heated to about 84 to 86 degrees.""",
        "order": 2,
    },
    {
        "section_key": "voice_swim_levels",
        "scope": SectionScope.BUSINESS_INFO.value,
        "content": """SWIM LEVELS:

For babies and toddlers: Tadpole and Swimboree
For beginners: Seahorse and Starfish
For developing swimmers: Minnow, Turtle 1, and Turtle 2
For more advanced: Shark 1 and Shark 2
For teens and adults: Young Adult and Adult levels

When asked about levels, offer to help figure out the right one based on the swimmer's age and experience.""",
        "order": 3,
    },
    {
        "section_key": "voice_pricing",
        "scope": SectionScope.PRICING.value,
        "content": """PRICING INFO:

Monthly tuition depends on:
- Number of swimmers in the family
- How many classes per week

There are discounts for siblings and for taking multiple classes per week.

Registration fee: Sixty dollars for one swimmer, or ninety dollars max per family.

Billing happens on the twentieth of each month for the following month.

If someone asks for an exact price, offer to get their details so you can provide a personalized quote.""",
        "order": 4,
    },
    {
        "section_key": "voice_policies",
        "scope": SectionScope.BUSINESS_INFO.value,
        "content": """POLICIES:

Cancellation: Requires thirty days notice. No refunds.

Makeups: Must report absences in advance through the British Swim School app. Makeups expire after sixty days and max three in a sixty-day period.

Classes are thirty minutes long. Pools are indoor and heated.""",
        "order": 5,
    },
    {
        "section_key": "voice_contact",
        "scope": SectionScope.BUSINESS_INFO.value,
        "content": """CONTACT INFO:

Phone: 281-601-4588
Email: goswimcypressspring at britishswimschool dot com

If they need to reach someone directly, give the phone number slowly and clearly.""",
        "order": 6,
    },
    {
        "section_key": "voice_conversation_flow",
        "scope": SectionScope.BASE.value,
        "content": """CONVERSATION FLOW:

Start by understanding who the lessons are for:
- Baby or toddler (three months to three years)
- Child (three to eleven years)
- Teen (twelve to seventeen)
- Adult (eighteen plus)

Then ask about their swimming experience to suggest the right level.

Before giving registration info, always confirm which pool location works best for them.

End calls warmly. If they say goodbye, thank them and confirm any next steps.""",
        "order": 7,
    },
]


async def create_voice_prompt():
    """Create the voice-specific prompt bundle for tenant 3."""
    print("=" * 70)
    print(f"CREATE VOICE PROMPT FOR {TENANT_NAME}")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        # Verify tenant exists
        tenant_stmt = select(Tenant).where(Tenant.id == TENANT_ID)
        tenant_result = await db.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            print(f"ERROR: Tenant {TENANT_ID} not found!")
            return

        print(f"Found tenant: {tenant.name} (ID: {tenant.id})")

        prompt_repo = PromptRepository(db)

        # Check if voice prompt already exists
        existing = await prompt_repo.get_production_bundle(TENANT_ID, PromptChannel.VOICE.value)
        if existing:
            print(f"\nVoice prompt already exists (ID: {existing.id})")
            print(f"   Name: {existing.name}")
            print(f"   Status: {existing.status}")
            response = input("\nDo you want to create a new version? (y/n): ")
            if response.lower() != "y":
                print("Aborted.")
                return

        # Create the voice bundle
        print(f"\nCreating voice prompt bundle...")
        bundle = PromptBundle(
            tenant_id=TENANT_ID,
            name=f"{TENANT_NAME} Voice Prompt",
            version="1.0.0",
            channel=PromptChannel.VOICE.value,
            status=PromptStatus.DRAFT.value,
            is_active=False,
        )
        db.add(bundle)
        await db.commit()
        await db.refresh(bundle)
        print(f"Created bundle (ID: {bundle.id})")

        # Create sections
        print(f"\nAdding {len(VOICE_PROMPT_SECTIONS)} voice sections...")
        for section_data in VOICE_PROMPT_SECTIONS:
            section = PromptSection(
                bundle_id=bundle.id,
                section_key=section_data["section_key"],
                scope=section_data["scope"],
                content=section_data["content"],
                order=section_data["order"],
            )
            db.add(section)
            print(f"  Added: {section_data['section_key']}")

        await db.commit()
        print("All sections saved")

        # Publish to production
        print(f"\nPublishing bundle to production...")
        bundle = await prompt_repo.publish_bundle(TENANT_ID, bundle.id)
        print(f"Bundle published (Status: {bundle.status})")

        print()
        print("=" * 70)
        print("SUCCESS!")
        print("=" * 70)
        print(f"Tenant: {TENANT_NAME}")
        print(f"Bundle ID: {bundle.id}")
        print(f"Channel: {bundle.channel}")
        print(f"Status: {bundle.status}")
        print(f"Sections: {len(VOICE_PROMPT_SECTIONS)}")
        print()
        print("The next voice call to tenant 3 will use this dedicated voice prompt.")
        print("=" * 70)


async def preview_voice_prompt():
    """Preview the composed voice prompt for tenant 3."""
    async with AsyncSessionLocal() as db:
        from app.domain.services.prompt_service import PromptService

        prompt_service = PromptService(db)

        # Check if dedicated voice prompt exists
        has_dedicated = await prompt_service.has_dedicated_voice_prompt(TENANT_ID)
        print(f"\nHas dedicated voice prompt: {has_dedicated}")

        voice_prompt = await prompt_service.compose_prompt_voice(TENANT_ID)

        if voice_prompt:
            print(f"\n{'=' * 70}")
            print("COMPOSED VOICE PROMPT")
            print(f"{'=' * 70}")
            print(voice_prompt)
            print(f"\n{'=' * 70}")
            print(f"Total length: {len(voice_prompt)} characters")
        else:
            print("No voice prompt found!")


if __name__ == "__main__":
    print("=" * 70)
    print("BSS Cypress-Spring Voice Prompt Setup")
    print("=" * 70)
    print()
    print("This creates a dedicated voice prompt for phone calls.")
    print("It will be used instead of transforming the chat prompt.")
    print()

    asyncio.run(create_voice_prompt())

    preview = input("\nWould you like to preview the composed prompt? (y/n): ")
    if preview.lower() == "y":
        asyncio.run(preview_voice_prompt())
