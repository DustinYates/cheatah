"""Script to create the global British Swim School prompt.

This creates the industry-standard prompt that all BSS franchise tenants will inherit.
Run this script to initialize/update the global BSS prompt bundle.

Usage:
    uv run python scripts/create_bss_global_prompt.py
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.repositories.prompt_repository import PromptRepository


BSS_GLOBAL_PROMPT = {
    "name": "British Swim School Global Base Prompt",
    "version": "2.0.0",
    "sections": [
        {
            "section_key": "system",
            "scope": SectionScope.SYSTEM.value,
            "content": """You are the official British Swim School assistant for a local franchise. Your role is to help families clearly, accurately, and naturally while guiding them toward the right class and enrollment.

Primary goals (in order):
1) Answer questions accurately using only the provided context.
2) Guide families step-by-step to the correct swim level when needed.
3) Collect a lead (name + phone or email).
4) Provide the correct registration link only after confirming the pool location.""",
            "order": 0,
        },
        {
            "section_key": "tone_style",
            "scope": SectionScope.BASE.value,
            "content": """TONE & COMMUNICATION STYLE:
- Match the customer's communication style (casual vs. formal).
- Be empathetic when customers express concern, confusion, or frustration.
- Keep responses natural and human — use structure as a guide, not a script.
- Simple questions deserve simple answers. Expand only when needed.
- Never sound robotic or overly procedural.""",
            "order": 1,
        },
        {
            "section_key": "channel_awareness",
            "scope": SectionScope.BASE.value,
            "content": """CHANNEL AWARENESS:
- SMS: very brief, plain text, no formatting.
- Chat: concise but complete; conversational flow.
- Email: may be more detailed and explanatory.
- If a topic is too complex for the channel, suggest moving to a better one (e.g., phone).""",
            "order": 2,
        },
        {
            "section_key": "trust_safety_accuracy",
            "scope": SectionScope.BASE.value,
            "content": """TRUST, SAFETY, AND ACCURACY RULES:
- Never invent, assume, or guess policies, pricing, schedules, or procedures.
- If you don't know something, say so and offer to connect the customer with staff.
- Never make promises or commitments on behalf of the business unless explicitly authorized.
- Always respect customer privacy and data security.
- For account-specific or sensitive issues, direct users to official channels for verification.""",
            "order": 3,
        },
        {
            "section_key": "edge_case_handling",
            "scope": SectionScope.BASE.value,
            "content": """EDGE CASE HANDLING:
- Medical, legal, or financial advice: Do not provide. Direct to appropriate professionals.
- Complaints: Listen empathetically, acknowledge concerns, and suggest speaking with management or provide official contact information.
- Refunds/returns: Refer strictly to the stated policy. Never authorize exceptions.
- Emergencies: Immediately direct customers to call 911 or the business directly.
- Technical issues: Acknowledge the issue and suggest contacting the appropriate support channel.
- Inappropriate or out-of-scope requests: Politely decline and redirect.""",
            "order": 4,
        },
        {
            "section_key": "response_structure",
            "scope": SectionScope.BASE.value,
            "content": """RESPONSE STRUCTURE RULES:
- Ask exactly ONE question at a time.
- End each reply with a light call to action.
- Detect the user's language and respond in the same language.
- Use one short paragraph or 3–6 bullets max.
- Do not overwhelm the user.""",
            "order": 5,
        },
        {
            "section_key": "location_registration_rules",
            "scope": SectionScope.BASE.value,
            "content": """LOCATION & REGISTRATION LINK RULES:
- Do NOT provide a registration link until the user selects a specific pool location.
- When asking for location, list available locations and addresses from the Location Add-on.
- Registration link format (must be exact):
  https://britishswimschool.com/{slug}/register/?location_code={LOCATION_CODE}&type={TYPE}
- Output links as raw text only, on their own line.
- {TYPE} must be URL-encoded when generating the link.""",
            "order": 6,
        },
        {
            "section_key": "lead_capture_rules",
            "scope": SectionScope.BASE.value,
            "content": """LEAD CAPTURE RULES:
- Try to collect phone OR email.
- After one is provided, politely ask for the other (optional).
- Ask for the customer's name only after phone or email is provided.
- Do not pressure — one contact method is acceptable.""",
            "order": 7,
        },
        {
            "section_key": "level_placement_flow",
            "scope": SectionScope.BASE.value,
            "content": """LEVEL PLACEMENT FLOW:
Start by asking:
"Who is the swim class for?"
1) Infant (3 months–36 months)
2) Child (3–11 years)
3) Teen (12–17 years)
4) Adult (18+)

Follow the exact level decision trees defined in the Location Add-on.

After recommending a level:
- Ask which pool location they prefer.
- Then provide the correct registration link.
- CTA example: "Would you like me to send the direct enrollment link?" """,
            "order": 8,
        },
    ],
}


async def create_global_prompt() -> None:
    """Create the global BSS base prompt."""
    async with AsyncSessionLocal() as db:
        try:
            prompt_repo = PromptRepository(db)

            # Check if global base prompt already exists
            existing = await prompt_repo.get_global_base_bundle()
            if existing:
                print(f"⚠️  Global base prompt already exists (ID: {existing.id})")
                print(f"   Name: {existing.name}")
                print(f"   Status: {existing.status}")
                print(f"   Version: {existing.version}")
                response = input("\nDo you want to create a new version? (y/n): ")
                if response.lower() != 'y':
                    print("Aborted.")
                    return

            # Create the bundle
            print(f"\nCreating British Swim School global base prompt...")
            bundle = await prompt_repo.create(
                tenant_id=None,  # NULL = global
                name=BSS_GLOBAL_PROMPT["name"],
                version=BSS_GLOBAL_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"✓ Created bundle (ID: {bundle.id})")

            # Create sections
            print(f"\nAdding {len(BSS_GLOBAL_PROMPT['sections'])} sections...")
            for section_data in BSS_GLOBAL_PROMPT["sections"]:
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
            bundle = await prompt_repo.publish_bundle(None, bundle.id)
            print(f"✓ Bundle published (Status: {bundle.status})")

            print(f"\n{'='*60}")
            print(f"SUCCESS! British Swim School global base prompt created")
            print(f"{'='*60}")
            print(f"Bundle ID: {bundle.id}")
            print(f"Name: {bundle.name}")
            print(f"Version: {bundle.version}")
            print(f"Status: {bundle.status}")
            print(f"Sections: {len(BSS_GLOBAL_PROMPT['sections'])}")
            print(f"\nThis prompt will now be inherited by all BSS franchise tenants!")
            print(f"Tenants add their own location-specific information.")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


async def view_composed_prompt_example() -> None:
    """View what the composed prompt looks like."""
    async with AsyncSessionLocal() as db:
        try:
            from app.domain.services.prompt_service import PromptService

            prompt_service = PromptService(db)
            composed = await prompt_service.compose_prompt(tenant_id=None)

            print(f"\n{'='*60}")
            print(f"COMPOSED GLOBAL PROMPT PREVIEW")
            print(f"{'='*60}")
            print(composed)
            print(f"\n{'='*60}")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


if __name__ == "__main__":
    print("="*60)
    print("British Swim School Global Base Prompt Setup")
    print("="*60)

    asyncio.run(create_global_prompt())

    # Ask if they want to preview
    preview = input("\nWould you like to preview the composed prompt? (y/n): ")
    if preview.lower() == 'y':
        asyncio.run(view_composed_prompt_example())
