"""Setup tenant 1 as The Best Chatbot swim school."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.prompt_repository import PromptRepository
from app.persistence.repositories.tenant_repository import TenantRepository
from app.domain.services.prompt_service import PromptService
from sqlalchemy import select, update


TENANT_ID = 1

SWIM_SCHOOL_PROMPT = {
    "name": "Swim School Customer Service",
    "version": "1.0.0",
    "sections": [
        {
            "section_key": "business_identity",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """BUSINESS IDENTITY:
You are the friendly customer service assistant for The Best Chatbot Swim School.

We provide swim lessons for all ages, from infants to adults. Our mission is to teach 
water safety and swimming skills in a fun, supportive environment.""",
            "order": 10,
        },
        {
            "section_key": "services",
            "scope": SectionScope.BUSINESS_INFO.value,
            "content": """SWIM PROGRAMS OFFERED:
- Parent & Tot (6 months - 3 years): Parent joins child in the water
- Preschool (3-5 years): Introduction to water safety and basic skills
- Youth Beginner (6-12 years): Learn to swim fundamentals
- Youth Advanced (6-12 years): Stroke refinement and endurance
- Teen/Adult Lessons: Never too late to learn!
- Private Lessons: One-on-one instruction available

CLASS FORMAT:
- Group classes: 4-6 students per instructor
- Private lessons: 1-on-1 or semi-private (2 students)
- Session length: 30 minutes for most classes""",
            "order": 11,
        },
        {
            "section_key": "pricing",
            "scope": SectionScope.PRICING.value,
            "content": """PRICING INFORMATION:
- Group Lessons: Contact us for current session pricing
- Private Lessons: Premium pricing for personalized instruction
- Sibling discounts available
- Monthly and session-based payment options

Note: Pricing varies by program and location. Please ask for specific rates.""",
            "order": 12,
        },
        {
            "section_key": "faq",
            "scope": SectionScope.FAQ.value,
            "content": """FREQUENTLY ASKED QUESTIONS:

Q: What should my child bring to lessons?
A: Swimsuit, towel, goggles (optional), and a positive attitude!

Q: What if my child is afraid of the water?
A: That's completely normal! Our instructors are trained to work with nervous swimmers.

Q: How long until my child can swim?
A: Every child progresses at their own pace. Most see improvement within 4-8 weeks.

Q: Can I watch the lessons?
A: Yes! We encourage parents to watch from our observation area.""",
            "order": 13,
        },
        {
            "section_key": "lead_capture",
            "scope": SectionScope.CUSTOM.value,
            "content": """LEAD CAPTURE GUIDANCE:
When a customer shows interest:
1. Ask about the swimmer's age and experience
2. Recommend an appropriate program
3. Politely ask for name and phone/email to send more info
4. Be helpful first - don't push for contact info aggressively.""",
            "order": 20,
        },
    ],
}


async def main():
    async with AsyncSessionLocal() as db:
        print("=" * 60)
        print("SWIM SCHOOL TENANT SETUP - Tenant ID 1")
        print("=" * 60)
        
        # Check tenant
        tenant_repo = TenantRepository(db)
        tenant = await tenant_repo.get_by_id(None, TENANT_ID)
        
        if tenant:
            print(f"\n✓ Tenant found: {tenant.name}")
        else:
            print(f"\n✗ Tenant {TENANT_ID} NOT FOUND - create it first")
            return
        
        # Check existing prompts
        prompt_repo = PromptRepository(db)
        prod_bundle = await prompt_repo.get_production_bundle(TENANT_ID)
        
        if prod_bundle:
            print(f"✓ Production bundle exists: {prod_bundle.name}")
            sections = await prompt_repo.get_sections(prod_bundle.id)
            print(f"  Sections: {len(sections)}")
        else:
            print("✗ No production bundle - creating one...")
            
            # Create bundle
            bundle = await prompt_repo.create(
                tenant_id=TENANT_ID,
                name=SWIM_SCHOOL_PROMPT["name"],
                version=SWIM_SCHOOL_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"  ✓ Created bundle (ID: {bundle.id})")
            
            # Create sections
            for section_data in SWIM_SCHOOL_PROMPT["sections"]:
                section = PromptSection(
                    bundle_id=bundle.id,
                    section_key=section_data["section_key"],
                    scope=section_data["scope"],
                    content=section_data["content"],
                    order=section_data["order"],
                )
                db.add(section)
                print(f"  ✓ Added: {section_data['section_key']}")
            
            await db.commit()
            
            # Publish
            bundle = await prompt_repo.publish_bundle(TENANT_ID, bundle.id)
            print(f"  ✓ Published to production")
            prod_bundle = bundle
        
        # Test composed prompt
        print("\n" + "-" * 60)
        print("Testing compose_prompt()...")
        svc = PromptService(db)
        composed = await svc.compose_prompt(TENANT_ID)
        
        print(f"Composed length: {len(composed)} chars")
        
        if "swim" in composed.lower():
            print("✓ SUCCESS - Swim school content found!")
        else:
            print("⚠ WARNING - No swim content found")
        
        print(f"\nPreview:\n{composed[:300]}...")


if __name__ == "__main__":
    asyncio.run(main())
