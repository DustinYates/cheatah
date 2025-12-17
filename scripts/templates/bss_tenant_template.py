"""
TEMPLATE: British Swim School Franchise Tenant Prompt

Copy this file and customize it for each new BSS franchise location.

Instructions:
1. Copy this file to: scripts/create_bss_<franchise_name>_prompt.py
2. Update FRANCHISE_CONFIG with your franchise details
3. Update TENANT_PROMPT with location-specific information
4. Run: uv run python scripts/create_bss_<franchise_name>_prompt.py

Prerequisites:
- Global BSS prompt must be created first (scripts/create_bss_global_prompt.py)
- Tenant must exist in the database
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.prompt_repository import PromptRepository
from sqlalchemy import select


# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES FOR YOUR FRANCHISE
# ============================================================================

FRANCHISE_CONFIG = {
    # Must match the tenant name in your database
    "tenant_name": "BSS Your-Franchise-Name",

    # URL slug for registration links (e.g., "cypress-spring", "north-dallas")
    "slug": "your-franchise-slug",

    # Contact information
    "phone": "XXX-XXX-XXXX",
    "email": "goswimYOURLOCATION@britishswimschool.com",
}


# ============================================================================
# POOL LOCATIONS - ADD ALL YOUR FRANCHISE LOCATIONS
# ============================================================================
# Format:
# {
#     "name": "Pool Facility Name",
#     "address": "Full Street Address, City, State ZIP",
#     "location_code": "CODE_FOR_URL",  # Used in registration link
# }

POOL_LOCATIONS = [
    {
        "name": "Example Fitness Location 1",
        "address": "123 Main St, City, TX 77000",
        "location_code": "EXLOC1",
    },
    {
        "name": "Example Fitness Location 2",
        "address": "456 Oak Ave, City, TX 77001",
        "location_code": "EXLOC2",
    },
    # Add more locations as needed...
]


# ============================================================================
# SWIM LEVELS - Customize if your franchise uses different level names
# ============================================================================

SWIM_LEVELS = [
    "Tadpole",
    "Swimboree",
    "Seahorse",
    "Starfish",
    "Minnow",
    "Turtle 1",
    "Turtle 2",
    "Shark 1",
    "Shark 2",
    "Young Adult 1",
    "Young Adult 2",
    "Young Adult 3",
    "Adult Level 1",
    "Adult Level 2",
    "Adult Level 3",
]


# ============================================================================
# PRICING - Update with your franchise pricing structure
# ============================================================================

PRICING_INFO = {
    "registration_fee_single": 60,  # One swimmer
    "registration_fee_family_max": 90,  # Family maximum
    "billing_day": 20,  # Day of month billing occurs
}


# ============================================================================
# POLICIES - Update with any franchise-specific policies
# ============================================================================

# Cancellation form URL (if using Google Forms or similar)
CANCELLATION_FORM_URL = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform?usp=sf_link"

MAKEUP_POLICY = {
    "max_makeups": 3,
    "expiry_days": 60,
    "advance_notice_required": True,
    "app_reporting": True,  # Must report via BSS app
}


# ============================================================================
# SPECIAL PROGRAMS - Update based on your franchise offerings
# ============================================================================

SPECIAL_PROGRAMS = {
    "adaptive_aquatics": True,
    "private_lessons": True,  # "selectively" offered
    "swim_team_name": "Barracudas",  # Non-competitive swim team
    "swim_team_competitive": False,
}


# ============================================================================
# BUILD THE PROMPT SECTIONS - Generally no need to modify below this line
# ============================================================================

def format_locations_text():
    """Format pool locations for the prompt."""
    lines = ["AVAILABLE POOL LOCATIONS:", "(Must confirm location before sending registration link)", ""]
    for i, loc in enumerate(POOL_LOCATIONS, 1):
        lines.append(f"{i}) {loc['name']}")
        lines.append(f"   Address: {loc['address']}")
        lines.append(f"   location_code: {loc['location_code']}")
        lines.append("")
    return "\n".join(lines).strip()


def format_levels_text():
    """Format swim levels for the prompt."""
    lines = ["SWIM LEVELS (Human-Readable Names):"]
    for level in SWIM_LEVELS:
        lines.append(f"- {level}")
    return "\n".join(lines)


def format_special_programs_text():
    """Format special programs for the prompt."""
    lines = ["SPECIAL PROGRAMS:"]
    if SPECIAL_PROGRAMS.get("adaptive_aquatics"):
        lines.append("- Adaptive aquatics and special needs supported (case-by-case).")
    if SPECIAL_PROGRAMS.get("private_lessons"):
        lines.append("- Private lessons offered selectively.")
    if SPECIAL_PROGRAMS.get("swim_team_name"):
        competitive = "" if SPECIAL_PROGRAMS.get("swim_team_competitive") else " (non-competitive)"
        lines.append(f"- Swim team: {SPECIAL_PROGRAMS['swim_team_name']}{competitive}.")
    return "\n".join(lines)


TENANT_PROMPT = {
    "name": f"BSS {FRANCHISE_CONFIG['tenant_name']} Franchise Prompt",
    "version": "1.0.0",
    "sections": [
        {
            "section_key": "franchise_identity",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": f"""FRANCHISE IDENTITY:
You are supporting the British Swim School {FRANCHISE_CONFIG['tenant_name'].replace('BSS ', '')} franchise.

Registration link slug: {FRANCHISE_CONFIG['slug']}""",
            "order": 10,
        },
        {
            "section_key": "pool_locations",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": format_locations_text(),
            "order": 11,
        },
        {
            "section_key": "swim_levels",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": format_levels_text(),
            "order": 12,
        },
        {
            "section_key": "pricing_billing",
            "scope": SectionScope.PRICING.value,
            "content": f"""PRICING & BILLING:
- Tuition is billed monthly and calculated per lesson.
- Pricing depends on:
  • number of swimmers
  • number of classes per week
- Discounts apply for siblings and multiple weekly classes.
- Months with 5 weeks include additional charges because billing is per lesson.
- Billing occurs automatically on the {PRICING_INFO['billing_day']}th for the following month.
- First month is prorated if starting mid-month.
- If starting after the {PRICING_INFO['billing_day']}th, billing includes prorated current month + full next month.

When quoting prices:
• Ask for swimmers + weekly frequency first.
• Provide only the final estimated monthly total unless more detail is requested.

REGISTRATION FEE:
- ${PRICING_INFO['registration_fee_single']} for one swimmer or ${PRICING_INFO['registration_fee_family_max']} max per family
- One-time fee due at registration""",
            "order": 13,
        },
        {
            "section_key": "policies",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": f"""POLICIES:
- No refunds.
- Cancellation requires 30 days' notice.
- Cancellation form:
  {CANCELLATION_FORM_URL}""",
            "order": 14,
        },
        {
            "section_key": "makeups",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": f"""MAKEUP POLICY:
- Absences must be reported in advance via the British Swim School app.
- Courtesy-based; availability not guaranteed.
- Expire {MAKEUP_POLICY['expiry_days']} days after the missed class.
- Valid only while actively enrolled.
- Forfeit if absent from a scheduled makeup.
- Maximum {MAKEUP_POLICY['max_makeups']} makeups in a {MAKEUP_POLICY['expiry_days']}-day period.""",
            "order": 15,
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
            "order": 16,
        },
        {
            "section_key": "special_programs",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": format_special_programs_text(),
            "order": 17,
        },
        {
            "section_key": "contact_info",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": f"""CONTACT INFORMATION:
Phone: {FRANCHISE_CONFIG['phone']}
Email: {FRANCHISE_CONFIG['email']}""",
            "order": 18,
        },
    ],
}


# ============================================================================
# SCRIPT EXECUTION - No need to modify
# ============================================================================

async def create_tenant_prompt() -> None:
    """Create the tenant-specific prompt."""
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
                print(f"   2. Update FRANCHISE_CONFIG['tenant_name'] to match existing tenant")
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
            print(f"\nCreating tenant prompt for {FRANCHISE_CONFIG['tenant_name']}...")
            bundle = await prompt_repo.create(
                tenant_id=tenant.id,
                name=TENANT_PROMPT["name"],
                version=TENANT_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"✓ Created bundle (ID: {bundle.id})")

            # Create sections
            print(f"\nAdding {len(TENANT_PROMPT['sections'])} sections...")
            for section_data in TENANT_PROMPT["sections"]:
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
            print(f"SUCCESS! Tenant prompt created")
            print(f"{'='*60}")
            print(f"Tenant: {tenant.name}")
            print(f"Bundle ID: {bundle.id}")
            print(f"Name: {bundle.name}")
            print(f"Version: {bundle.version}")
            print(f"Status: {bundle.status}")
            print(f"Sections: {len(TENANT_PROMPT['sections'])}")

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
            print(f"  - {tenant.name} specific sections")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


if __name__ == "__main__":
    print("="*60)
    print(f"BSS Franchise Tenant Prompt Setup")
    print("="*60)
    print(f"\nThis creates the location-specific prompt for {FRANCHISE_CONFIG['tenant_name']}.")
    print(f"It will extend the global BSS base prompt with location details.\n")

    asyncio.run(create_tenant_prompt())

    # Ask if they want to preview
    preview = input("\nWould you like to preview the full composed prompt? (y/n): ")
    if preview.lower() == 'y':
        asyncio.run(view_composed_prompt())
