"""Script to create the tenant-specific prompt for BSS Cypress-Spring franchise.

This creates the location-specific prompt that extends the global BSS base prompt.
Run this script after creating the tenant and the global BSS prompt.

Usage:
    uv run python scripts/create_bss_cypress_spring_prompt.py
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.prompt_repository import PromptRepository
from sqlalchemy import select


# Configuration - Update this for each franchise
FRANCHISE_CONFIG = {
    "tenant_name": "BSS Cypress-Spring",  # Must match existing tenant name
    "slug": "cypress-spring",
}

CYPRESS_SPRING_PROMPT = {
    "name": "BSS Cypress-Spring Franchise Prompt",
    "version": "1.1.0",
    "sections": [
        {
            "section_key": "franchise_identity",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": f"""FRANCHISE IDENTITY:
You are supporting the British Swim School Cypress-Spring franchise.

Registration link slug: {FRANCHISE_CONFIG['slug']}""",
            "order": 10,
        },
        {
            "section_key": "pool_locations",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """AVAILABLE POOL LOCATIONS:
(Must confirm location before sending registration link)

1) LA Fitness Cypress
   Address: 12304 Barker Cypress Rd, Cypress, TX 77429
   location_code: LAFCypress

2) LA Fitness Langham Creek
   Address: 17800 Farm to Market Rd 529, Houston, TX 77095
   location_code: LALANG

3) 24 HR Fitness Spring Energy
   Address: 1000 Lake Plaza Dr, Spring, TX 77389
   location_code: 24Spring""",
            "order": 11,
        },
        {
            "section_key": "location_hours",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """LOCATION HOURS - CRITICAL: NEVER make up or guess class times. Only use the hours listed below.

LOCATION 1: LA Fitness - Cypress (12304 Barker Cypress Rd, Cypress, TX 77429)
Pool Hours (Class Time Windows):
- Monday: 3:30 PM - 8:00 PM
- Tuesday: CLOSED
- Wednesday: 3:30 PM - 8:00 PM
- Thursday: CLOSED
- Friday: CLOSED
- Saturday: 9:00 AM - 4:00 PM
- Sunday: CLOSED
Office Hours:
- Monday - Friday: 9:00 AM - 5:00 PM
- Saturday: CLOSED
- Sunday: CLOSED

LOCATION 2: LA Fitness - Langham Creek (17800 Farm to Market Rd 529, Houston, TX 77095)
Pool Hours (Class Time Windows):
- Monday: CLOSED
- Tuesday: 3:30 PM - 8:00 PM
- Wednesday: CLOSED
- Thursday: 3:30 PM - 8:00 PM
- Friday: CLOSED
- Saturday: 10:30 AM - 3:00 PM
- Sunday: 9:00 AM - 2:00 PM
Office Hours:
- Monday - Friday: 9:00 AM - 5:00 PM
- Saturday: 10:30 AM - 3:00 PM
- Sunday: 9:00 AM - 2:00 PM

LOCATION 3: 24 HR Fitness - Spring Energy (1000 Lake Plaza Dr, Spring, TX 77389)
Pool Hours (Class Time Windows):
- Monday: 3:30 PM - 8:00 PM
- Tuesday: CLOSED
- Wednesday: 3:30 PM - 8:00 PM
- Thursday: 3:30 PM - 8:00 PM
- Friday: CLOSED
- Saturday: 9:00 AM - 2:00 PM
- Sunday: CLOSED
Office Hours:
- Monday - Friday: 9:00 AM - 5:00 PM
- Saturday: CLOSED
- Sunday: CLOSED

IMPORTANT: If a customer asks about class times on a day marked CLOSED, inform them that location is not available that day and suggest an alternative location that IS open.""",
            "order": 12,
        },
        {
            "section_key": "swim_levels",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """SWIM LEVELS (Human-Readable Names):
- Tadpole
- Swimboree
- Seahorse
- Starfish
- Minnow
- Turtle 1
- Turtle 2
- Shark 1
- Shark 2
- Young Adult 1
- Young Adult 2
- Young Adult 3
- Adult Level 1
- Adult Level 2
- Adult Level 3""",
            "order": 13,
        },
        {
            "section_key": "pricing_billing",
            "scope": SectionScope.PRICING.value,
            "content": """PRICING & BILLING:
- Tuition is billed monthly and calculated per lesson.
- Pricing depends on:
  • number of swimmers
  • number of classes per week
- Discounts apply for siblings and multiple weekly classes.
- Months with 5 weeks include additional charges because billing is per lesson.
- Billing occurs automatically on the 20th for the following month.
- First month is prorated if starting mid-month.
- If starting after the 20th, billing includes prorated current month + full next month.

When quoting prices:
• Ask for swimmers + weekly frequency first.
• Provide only the final estimated monthly total unless more detail is requested.

REGISTRATION FEE:
- $60 for one swimmer or $90 max per family
- One-time fee due at registration""",
            "order": 14,
        },
        {
            "section_key": "policies",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """POLICIES:
- No refunds.
- Cancellation requires 30 days' notice.
- Cancellation form:
  https://docs.google.com/forms/d/e/1FAIpQLSfJSzk32Bs5anwvboN5i30X2-g0FpuIYszT0QhR8zdxokCX_g/viewform?usp=sf_link""",
            "order": 15,
        },
        {
            "section_key": "makeups",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """MAKEUP POLICY:
- Absences must be reported in advance via the British Swim School app.
- Courtesy-based; availability not guaranteed.
- Expire 60 days after the missed class.
- Valid only while actively enrolled.
- Forfeit if absent from a scheduled makeup.
- Maximum 3 makeups in a 60-day period.""",
            "order": 16,
        },
        {
            "section_key": "program_details",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """GENERAL PROGRAM DETAILS:
- No free trials; families may observe a lesson before enrolling.
- Class length: 30 minutes.
- Pools are indoor and heated (84–86°F).
- Instructor training: 40+ hours, CPR/First Aid/AED certified.
- Diapers: Two swim diapers required for non–potty-trained children.

STUDENT-TO-TEACHER RATIOS:
• Acclimation/survival: 4:1
• Tadpole: 6:1 (parent in water)
• Stroke development: 6:1
• Adult Level 1: 3:1; other adult levels: 4:1""",
            "order": 17,
        },
        {
            "section_key": "special_programs",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """SPECIAL PROGRAMS:
- Adaptive aquatics and special needs supported (case-by-case).
- Private lessons offered selectively.
- Swim team: Barracudas (non-competitive).""",
            "order": 18,
        },
        {
            "section_key": "contact_info",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """CONTACT INFORMATION:
Phone: 281-601-4588
Email: goswimcypressspring@britishswimschool.com""",
            "order": 19,
        },
    ],
}


async def create_tenant_prompt() -> None:
    """Create the tenant-specific prompt for Cypress-Spring."""
    async with AsyncSessionLocal() as db:
        try:
            # Find the tenant
            result = await db.execute(
                select(Tenant).where(Tenant.name == FRANCHISE_CONFIG["tenant_name"])
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                print(f"❌ Tenant '{FRANCHISE_CONFIG['tenant_name']}' not found!")
                print(f"   Please create the tenant first.")
                print(f"\n   Available options:")
                print(f"   1. Create tenant via API")
                print(f"   2. Run: uv run python scripts/create_test_tenant.py")
                return

            print(f"✓ Found tenant: {tenant.name} (ID: {tenant.id})")

            prompt_repo = PromptRepository(db)

            # Check if tenant prompt already exists
            existing = await prompt_repo.get_production_bundle(tenant.id)
            if existing:
                print(f"\n⚠️  Tenant prompt already exists (ID: {existing.id})")
                print(f"   Name: {existing.name}")
                print(f"   Status: {existing.status}")
                print(f"   Version: {existing.version}")
                response = input("\nDo you want to create a new version? (y/n): ")
                if response.lower() != 'y':
                    print("Aborted.")
                    return

            # Create the bundle
            print(f"\nCreating Cypress-Spring tenant prompt...")
            bundle = await prompt_repo.create(
                tenant_id=tenant.id,
                name=CYPRESS_SPRING_PROMPT["name"],
                version=CYPRESS_SPRING_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"✓ Created bundle (ID: {bundle.id})")

            # Create sections
            print(f"\nAdding {len(CYPRESS_SPRING_PROMPT['sections'])} sections...")
            for section_data in CYPRESS_SPRING_PROMPT["sections"]:
                section = PromptSection(
                    bundle_id=bundle.id,
                    section_key=section_data["section_key"],
                    scope=section_data["scope"],
                    content=section_data["content"],
                    order=section_data["order"],
                )
                db.add(section)
                print(f"  ✓ Added section: {section_data['section_key']}")

            await db.commit()
            print(f"\n✓ All sections saved")

            # Publish to production
            print(f"\nPublishing bundle to production...")
            bundle = await prompt_repo.publish_bundle(tenant.id, bundle.id)
            print(f"✓ Bundle published (Status: {bundle.status})")

            print(f"\n{'='*60}")
            print(f"SUCCESS! Cypress-Spring tenant prompt created")
            print(f"{'='*60}")
            print(f"Tenant: {tenant.name}")
            print(f"Bundle ID: {bundle.id}")
            print(f"Name: {bundle.name}")
            print(f"Version: {bundle.version}")
            print(f"Status: {bundle.status}")
            print(f"Sections: {len(CYPRESS_SPRING_PROMPT['sections'])}")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


async def view_composed_prompt() -> None:
    """View the full composed prompt for this tenant."""
    async with AsyncSessionLocal() as db:
        try:
            # Find the tenant
            result = await db.execute(
                select(Tenant).where(Tenant.name == FRANCHISE_CONFIG["tenant_name"])
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                print(f"❌ Tenant not found")
                return

            from app.domain.services.prompt_service import PromptService

            prompt_service = PromptService(db)
            composed = await prompt_service.compose_prompt(tenant_id=tenant.id)

            print(f"\n{'='*60}")
            print(f"COMPOSED PROMPT FOR {tenant.name}")
            print(f"{'='*60}")
            print(composed)
            print(f"\n{'='*60}")
            print(f"\nThis includes:")
            print(f"  - Global BSS base prompt sections")
            print(f"  - Cypress-Spring specific sections")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


if __name__ == "__main__":
    print("="*60)
    print("BSS Cypress-Spring Franchise Prompt Setup")
    print("="*60)
    print(f"\nThis creates the location-specific prompt for {FRANCHISE_CONFIG['tenant_name']}.")
    print(f"It will extend the global BSS base prompt with location details.\n")

    asyncio.run(create_tenant_prompt())

    # Ask if they want to preview
    preview = input("\nWould you like to preview the full composed prompt? (y/n): ")
    if preview.lower() == 'y':
        asyncio.run(view_composed_prompt())
