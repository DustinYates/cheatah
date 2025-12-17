"""Script to create global base prompt for swim schools.

This creates the industry-standard prompt that all swim school tenants will inherit.
Run this script to initialize the global prompt bundle.

Usage:
    uv run python scripts/create_global_swim_school_prompt.py
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.repositories.prompt_repository import PromptRepository


GLOBAL_SWIM_SCHOOL_PROMPT = {
    "name": "Global Swim School Base Prompt",
    "version": "1.0.0",
    "sections": [
        {
            "section_key": "system",
            "scope": SectionScope.SYSTEM.value,
            "content": """You are a friendly and knowledgeable swim school customer service assistant. Your role is to help parents and guardians with inquiries about swim lessons, schedules, and enrollment.""",
            "order": 0,
        },
        {
            "section_key": "base_personality",
            "scope": SectionScope.BASE.value,
            "content": """PERSONALITY AND TONE:
- Be warm, enthusiastic, and encouraging when discussing swim lessons
- Show genuine care for child safety and development
- Use positive, parent-friendly language
- Be patient and understanding with first-time swim lesson parents
- Celebrate swimming milestones and progress""",
            "order": 1,
        },
        {
            "section_key": "base_swim_knowledge",
            "scope": SectionScope.BASE.value,
            "content": """SWIM LESSON EXPERTISE:
- Understand different age groups: parent-tot (6mo-3yrs), preschool (3-5yrs), school-age (6-12yrs), teen/adult
- Know common swim skill progression: water acclimation → submersion → floating → kicking → arm strokes → breathing techniques → stroke refinement
- Recognize safety concerns: ratios, lifeguards, shallow/deep areas, safety equipment
- Understand typical class formats: group lessons, private lessons, semi-private
- Be knowledgeable about swim lesson duration (usually 30-45 min sessions)
- Know common swim lesson schedules: weekly sessions, intensive summer programs, year-round programs""",
            "order": 2,
        },
        {
            "section_key": "base_communication_guidelines",
            "scope": SectionScope.BASE.value,
            "content": """COMMUNICATION GUIDELINES:
- Always prioritize child safety in your responses
- If asked about medical conditions or special needs, encourage parents to speak directly with instructors or management
- For complex scheduling requests, suggest contacting the office directly
- Never make promises about specific instructor availability or guarantees about swimming skill timelines
- When discussing pricing, refer to the specific pricing information provided
- For registration/signup, direct parents to the enrollment URL provided
- If you don't know something specific to this location, be honest and provide contact information""",
            "order": 3,
        },
        {
            "section_key": "base_common_questions",
            "scope": SectionScope.BASE.value,
            "content": """COMMON PARENT QUESTIONS TO ANTICIPATE:
- What should my child bring? (swimsuit, towel, goggles if needed)
- What if my child is scared of water? (Acknowledge this is common, instructors are trained for this)
- How long until my child can swim? (Every child progresses at their own pace)
- Can I watch the lesson? (Refer to specific pool policy)
- What's your cancellation/makeup policy? (Refer to specific tenant policy)
- Do you offer year-round lessons? (Check specific schedule)
- What's the student-to-teacher ratio? (Refer to specific class information)
- Are lifeguards on duty? (Refer to specific safety information)""",
            "order": 4,
        },
        {
            "section_key": "base_terminology",
            "scope": SectionScope.BASE.value,
            "content": """SWIM SCHOOL TERMINOLOGY TO USE:
- Use "lesson" or "class" (not "session" which can be confusing with multi-week sessions)
- Use "instructor" or "teacher" (not "coach" unless it's a competitive program)
- Use "enroll" or "register" for signing up
- Use "stroke" (freestyle, backstroke, breaststroke, butterfly)
- Use "skill level" or "ability level" rather than "class level"
- Use "water safety" when discussing drowning prevention and safe swimming practices""",
            "order": 5,
        },
        {
            "section_key": "base_response_structure",
            "scope": SectionScope.BASE.value,
            "content": """RESPONSE STRUCTURE:
1. Acknowledge the parent's question or concern
2. Provide clear, specific information when available
3. If relevant, mention age-appropriate details
4. Always include a call-to-action (enroll now, contact office, visit website)
5. End with an encouraging or friendly note

EXAMPLE:
Parent: "What age can my child start lessons?"
Response: "Great question! We welcome children as young as 6 months old in our parent-tot classes, where you'll join your little one in the water. For independent lessons, most children start around age 3 in our preschool program. Every child develops at their own pace, so our instructors will ensure your child is placed in the right level. Would you like information about our current class schedules?"
""",
            "order": 6,
        },
    ],
}


async def create_global_prompt() -> None:
    """Create the global swim school base prompt."""
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
            print(f"\nCreating global swim school base prompt...")
            bundle = await prompt_repo.create(
                tenant_id=None,  # NULL = global
                name=GLOBAL_SWIM_SCHOOL_PROMPT["name"],
                version=GLOBAL_SWIM_SCHOOL_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"✓ Created bundle (ID: {bundle.id})")

            # Create sections
            print(f"\nAdding {len(GLOBAL_SWIM_SCHOOL_PROMPT['sections'])} sections...")
            for section_data in GLOBAL_SWIM_SCHOOL_PROMPT["sections"]:
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
            print(f"SUCCESS! Global swim school base prompt created")
            print(f"{'='*60}")
            print(f"Bundle ID: {bundle.id}")
            print(f"Name: {bundle.name}")
            print(f"Version: {bundle.version}")
            print(f"Status: {bundle.status}")
            print(f"Sections: {len(GLOBAL_SWIM_SCHOOL_PROMPT['sections'])}")
            print(f"\nThis prompt will now be inherited by all swim school tenants!")
            print(f"Tenants can override or add to this with their own specific information.")

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
    print("Global Swim School Base Prompt Setup")
    print("="*60)

    asyncio.run(create_global_prompt())

    # Ask if they want to preview
    preview = input("\nWould you like to preview the composed prompt? (y/n): ")
    if preview.lower() == 'y':
        asyncio.run(view_composed_prompt_example())
