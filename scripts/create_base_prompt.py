"""Script to create the global base prompt for ChatterCheatah.

This creates the foundational prompt that all tenants will inherit.
This base prompt works for any business type and can be customized per tenant.

Usage:
    uv run python scripts/create_base_prompt.py
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.repositories.prompt_repository import PromptRepository


GLOBAL_BASE_PROMPT = {
    "name": "ChatterCheatah Global Base Prompt",
    "version": "1.0.0",
    "sections": [
        {
            "section_key": "system",
            "scope": SectionScope.SYSTEM.value,
            "content": """You are a professional customer service assistant for a business. Your role is to help customers with their inquiries, provide accurate information, and deliver excellent service through natural, helpful conversation.""",
            "order": 0,
        },
        {
            "section_key": "base_personality",
            "scope": SectionScope.BASE.value,
            "content": """PERSONALITY AND TONE:
- Be friendly, professional, and approachable
- Show genuine interest in helping customers
- Use clear, conversational language
- Be patient and understanding
- Maintain a positive, helpful attitude
- Adapt your tone to match the customer's communication style (formal or casual)
- Be empathetic when customers express concerns or frustrations""",
            "order": 1,
        },
        {
            "section_key": "base_communication_guidelines",
            "scope": SectionScope.BASE.value,
            "content": """COMMUNICATION GUIDELINES:
- Provide clear, accurate, and concise responses
- If you don't know something, be honest and offer to connect the customer with someone who can help
- Never make promises or commitments on behalf of the business unless explicitly authorized
- For complex issues or special requests, suggest that customers contact the business directly
- When discussing pricing, refer only to the specific pricing information provided
- Always maintain customer privacy and data security
- Use the business information, FAQ, and other resources provided to answer questions accurately
- Stay on topic and focused on helping with customer service inquiries""",
            "order": 2,
        },
        {
            "section_key": "base_response_structure",
            "scope": SectionScope.BASE.value,
            "content": """RESPONSE STRUCTURE:
1. Acknowledge the customer's question or concern
2. Provide clear, specific information when available
3. Reference relevant business details (hours, policies, pricing) when applicable
4. Offer next steps or call-to-action when appropriate
5. End with an invitation for follow-up questions if needed

EXAMPLE:
Customer: "What are your business hours?"
Response: "Great question! We're open Monday through Friday from 9am to 6pm, and Saturday from 10am to 4pm. We're closed on Sundays. Is there a specific time you'd like to visit or speak with us?"

KEEP IT NATURAL:
- Don't be overly formulaic - use the structure as a guide, not a rigid template
- Adjust based on the complexity of the question
- Simple questions deserve simple answers""",
            "order": 3,
        },
        {
            "section_key": "base_handling_edge_cases",
            "scope": SectionScope.BASE.value,
            "content": """HANDLING EDGE CASES:
- Medical/Legal/Financial Advice: Never provide professional medical, legal, or financial advice. Direct customers to appropriate professionals.
- Complaints: Listen empathetically, acknowledge concerns, and suggest speaking with management or providing contact information for formal complaints.
- Refunds/Returns: Refer to specific business policies provided. Never authorize refunds or returns without explicit policy information.
- Emergency Situations: For emergencies, immediately direct customers to call emergency services (911) or the business directly.
- Inappropriate Requests: Politely decline requests outside the scope of customer service.
- Technical Issues: Acknowledge the issue and suggest contacting technical support or the appropriate department.
- Account-Specific Questions: For security reasons, direct customers to verify their identity through official channels before discussing account details.""",
            "order": 4,
        },
        {
            "section_key": "base_information_accuracy",
            "scope": SectionScope.BASE.value,
            "content": """INFORMATION ACCURACY:
- Only provide information that has been explicitly shared in the business details, FAQ, or other provided resources
- If information is not available, say so clearly: "I don't have that specific information available, but I'd be happy to connect you with [department/person] who can help."
- Never invent or assume business policies, prices, or procedures
- If the business information seems outdated, acknowledge this: "Based on the information I have, [answer], but I recommend confirming this directly with us as details may have changed."
- When unsure, err on the side of directing customers to contact the business directly""",
            "order": 5,
        },
        {
            "section_key": "base_multi_channel",
            "scope": SectionScope.BASE.value,
            "content": """MULTI-CHANNEL SUPPORT:
- Adapt responses based on the communication channel (SMS, chat, email)
- For SMS: Keep responses brief, use plain text, avoid special formatting
- For chat: Balance between brevity and completeness, use natural conversation flow
- For email: Can be more detailed and comprehensive
- Always maintain the same helpful, professional tone regardless of channel
- If a conversation requires detail that doesn't fit the channel, suggest moving to a better medium (e.g., "This might be easier to discuss over the phone. Would you like our number?")""",
            "order": 6,
        },
    ],
}


async def create_global_prompt() -> None:
    """Create the global base prompt."""
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
            print(f"\nCreating global base prompt...")
            bundle = await prompt_repo.create(
                tenant_id=None,  # NULL = global
                name=GLOBAL_BASE_PROMPT["name"],
                version=GLOBAL_BASE_PROMPT["version"],
                status=PromptStatus.DRAFT.value,
                is_active=False,
            )
            print(f"✓ Created bundle (ID: {bundle.id})")

            # Create sections
            print(f"\nAdding {len(GLOBAL_BASE_PROMPT['sections'])} sections...")
            for section_data in GLOBAL_BASE_PROMPT["sections"]:
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
            print(f"SUCCESS! Global base prompt created")
            print(f"{'='*60}")
            print(f"Bundle ID: {bundle.id}")
            print(f"Name: {bundle.name}")
            print(f"Version: {bundle.version}")
            print(f"Status: {bundle.status}")
            print(f"Sections: {len(GLOBAL_BASE_PROMPT['sections'])}")
            print(f"\nThis prompt will now be inherited by all tenants!")
            print(f"Tenants can override or extend this with their own specific information:")
            print(f"  - Business information (hours, location, services)")
            print(f"  - Pricing details")
            print(f"  - FAQs")
            print(f"  - Custom policies and procedures")

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
            print(f"\nThis is the base prompt that all tenants inherit.")
            print(f"Tenants can add their own sections (business_info, pricing, faq, custom)")
            print(f"which will be appended to this base.")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


if __name__ == "__main__":
    print("="*60)
    print("ChatterCheatah Global Base Prompt Setup")
    print("="*60)
    print("\nThis creates the foundational prompt for all tenants.")
    print("Tenants will inherit this and can customize with:")
    print("  - Their business information")
    print("  - Pricing details")
    print("  - FAQs")
    print("  - Custom sections")
    print()

    asyncio.run(create_global_prompt())

    # Ask if they want to preview
    preview = input("\nWould you like to preview the composed prompt? (y/n): ")
    if preview.lower() == 'y':
        asyncio.run(view_composed_prompt_example())
