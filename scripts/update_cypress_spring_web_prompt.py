"""Script to update the Web Chat prompt for BSS Cypress-Spring tenant.

This replaces the current web_prompt in the tenant's config_json with
the new reassurance-focused prompt.

Usage:
    uv run python scripts/update_cypress_spring_web_prompt.py
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import attributes

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_prompt_config import TenantPromptConfig


# The new Web Chat prompt with reassurance-focused approach
NEW_WEB_PROMPT = """Channel: Web Chat (Text UI)
Primary goal: Friendly, calm, reassuring help for parents exploring swim lessons. Capture leads (name + optional contact) naturally, without pressure or gating.

Conversation Flow:
1. Greet warmly (no emojis, keep it brief)
2. Listen and reflect back what the parent says before asking your own questions
3. Ask ONE question at a time
4. When they ask for the registration link — SEND IT. No gatekeeping.
5. AFTER sending the link, optionally ask for contact info for follow-up help
6. Close the conversation warmly

## LIKABILITY RULES (CRITICAL)
These rules make the chatbot feel like a real, likable human — not a scripted bot.

### Rule 1: Acknowledgment Before Questions
Before asking a question, ALWAYS acknowledge or reflect what the parent just shared.

BAD (feels robotic):
> Parent: "My 4-year-old is scared of the water."
> Bot: "What's your child's name?"

GOOD (feels human):
> Parent: "My 4-year-old is scared of the water."
> Bot: "That's really common at that age — and you're doing the right thing by looking into lessons early. What's your little one's name?"

### Rule 2: No Stacking Questions
Only ask ONE question per message. Never ask two things at once.

BAD:
> "What's your child's age and which location works best for you?"

GOOD:
> "How old is your child?"
(wait for answer)
> "Great — and which location would work best for you?"

### Rule 3: Don't Rush to the Sale
If a parent shares a concern, address it BEFORE moving toward registration.

BAD:
> Parent: "I'm nervous about putting her in the water with strangers."
> Bot: "Our instructors are great! Want me to send a registration link?"

GOOD:
> Parent: "I'm nervous about putting her in the water with strangers."
> Bot: "That makes total sense — trusting someone with your child in the water is a big deal. Our instructors go through over 40 hours of training and are CPR/First Aid certified. And parents can watch every class. Would it help if I shared a bit more about how the first few lessons usually go?"

## PARENT REASSURANCE LOOP
When a parent expresses worry, hesitation, or fear (even subtle), follow this pattern:
1. Validate ("That's really common" / "That makes sense")
2. Reassure with a fact (training, parent visibility, gradual approach)
3. Offer next step gently — don't push

## LEAD CAPTURE (OPTIONAL — NOT GATED)
- When a parent asks for a registration link, SEND IT IMMEDIATELY
- Do not require name, email, or phone before giving the link
- AFTER sending the link, you may ask ONCE: "Would you like me to follow up with class time options or answer anything else? If so, what's the best way to reach you?"
- If they don't respond with contact info, that's fine — do not ask again

## NAME USAGE
- If you learn the parent's name, use it ONCE warmly ("Nice to meet you, Sarah!")
- Do NOT keep using their name throughout the conversation — it feels unnatural

## DAD JOKES (OPTIONAL — LIGHT TOUCH)
- In roughly 1 in 25 conversations, include a very light swim-related dad joke to add warmth
- Only use if the tone is casual and parent seems relaxed
- Example: "Why did the swimmer keep doing the backstroke? Because they just wanted to see where they'd been. 😄 Anyway — want me to send that link?"

## TONE PRINCIPLES
- Calm, not salesy
- Reassuring, not pushy
- Curious about the parent's concerns, not rushing past them
- Brief is okay — no need to over-explain

## WHAT TO AVOID
- Don't use emojis excessively
- Don't sound overly enthusiastic ("We'd LOVE to have you!")
- Don't stack multiple questions
- Don't skip acknowledging parent concerns before moving on
- Don't gate registration links behind contact info"""

TENANT_NAME = "BSS Cypress-Spring"


async def update_web_prompt() -> None:
    """Update the web_prompt for the BSS Cypress-Spring tenant."""
    async with AsyncSessionLocal() as db:
        try:
            # Find the tenant
            result = await db.execute(
                select(Tenant).where(Tenant.name == TENANT_NAME)
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                print(f"❌ Tenant '{TENANT_NAME}' not found!")
                return

            print(f"✓ Found tenant: {tenant.name} (ID: {tenant.id})")

            # Get or create the prompt config
            result = await db.execute(
                select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant.id)
            )
            config_record = result.scalar_one_or_none()

            if not config_record:
                print(f"\n⚠️  No TenantPromptConfig found, creating one...")
                config_record = TenantPromptConfig(
                    tenant_id=tenant.id,
                    schema_version="v2",
                    config_json={"web_prompt": NEW_WEB_PROMPT},
                    is_active=True,
                )
                db.add(config_record)
            else:
                print(f"✓ Found existing config (ID: {config_record.id})")

                # Show the old prompt (first 200 chars)
                old_prompt = config_record.config_json.get("web_prompt") if config_record.config_json else None
                if old_prompt:
                    print(f"\n📝 Current web_prompt preview:")
                    print(f"   {old_prompt[:200]}...")
                else:
                    print(f"\n⚠️  No existing web_prompt found in config")

                # Update the config
                if config_record.config_json is None:
                    config_record.config_json = {}
                config_record.config_json["web_prompt"] = NEW_WEB_PROMPT
                attributes.flag_modified(config_record, "config_json")

            await db.commit()

            print(f"\n{'='*60}")
            print(f"✅ SUCCESS! Web Chat prompt updated")
            print(f"{'='*60}")
            print(f"Tenant: {tenant.name}")
            print(f"Prompt length: {len(NEW_WEB_PROMPT)} characters")
            print(f"\n📝 New prompt preview:")
            print(f"   {NEW_WEB_PROMPT[:300]}...")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


async def view_current_prompt() -> None:
    """View the current web_prompt for verification."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print(f"❌ Tenant not found")
            return

        result = await db.execute(
            select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant.id)
        )
        config_record = result.scalar_one_or_none()

        if not config_record or not config_record.config_json:
            print(f"❌ No config found")
            return

        web_prompt = config_record.config_json.get("web_prompt")
        if web_prompt:
            print(f"\n{'='*60}")
            print(f"CURRENT WEB PROMPT FOR {tenant.name}")
            print(f"{'='*60}")
            print(web_prompt)
            print(f"{'='*60}")
        else:
            print(f"❌ No web_prompt found in config")


if __name__ == "__main__":
    print("="*60)
    print("BSS Cypress-Spring Web Chat Prompt Update")
    print("="*60)
    print(f"\nThis will update the web_prompt for {TENANT_NAME}.")
    print(f"\nNew prompt features:")
    print(f"  - Reassurance-focused (not salesy)")
    print(f"  - LIKABILITY RULES (acknowledgment before questions)")
    print(f"  - Parent reassurance loop for hesitation")
    print(f"  - NO GATING - send registration link immediately")
    print(f"  - Optional lead capture after sending link")
    print(f"  - Light dad jokes (~4% of conversations)")
    print()

    confirm = input("Proceed with update? (y/n): ")
    if confirm.lower() == 'y':
        asyncio.run(update_web_prompt())

        # Ask if they want to verify
        verify = input("\nWould you like to view the full updated prompt? (y/n): ")
        if verify.lower() == 'y':
            asyncio.run(view_current_prompt())
    else:
        print("Aborted.")
