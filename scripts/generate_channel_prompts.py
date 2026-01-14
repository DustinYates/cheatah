"""Generate channel-specific prompts from Core Brain.

This script implements the Core Prompt Brain architecture:
- Reads tenant's v2 config JSON (the "Core Brain" - business facts only)
- Generates 3 channel-specific prompts with appropriate delivery rules

Usage:
    python scripts/generate_channel_prompts.py [tenant_id]

Output:
    Three distinct prompts for Web Chat, Voice, and SMS that can be copy/pasted.
"""

import asyncio
import json
import sys
from datetime import datetime

from sqlalchemy import select

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_prompt_config import TenantPromptConfig


# =============================================================================
# CORE BRAIN ASSEMBLER (Channel-Agnostic Business Facts)
# =============================================================================

def assemble_core_brain(config: dict, tenant_name: str) -> str:
    """Assemble the Core Brain - deterministic business facts only.

    No delivery instructions. No channel-specific rules.
    Just the authoritative truth about the business.
    """
    sections = []

    # === BUSINESS IDENTITY ===
    display_name = config.get("display_name", tenant_name)
    contact = config.get("contact", {})
    sections.append(f"""## BUSINESS IDENTITY
- Name: {display_name}
- SMS Support: {"Enabled" if contact.get("sms_enabled") else "Disabled"}
- Email Support: {"Enabled" if contact.get("email_enabled") else "Disabled"}
- Support Phone: {contact.get("support_phone") or "Not specified"}
- Support Email: {contact.get("support_email") or "Not specified"}""")

    # === LOCATIONS ===
    locations = config.get("locations", [])
    if locations:
        loc_text = "## LOCATIONS\n"
        for loc in locations:
            loc_text += f"\n### {loc.get('name', 'Unknown')}"
            if loc.get("is_default"):
                loc_text += " (Default)"
            loc_text += f"\n- Code: {loc.get('code', 'N/A')}"
            loc_text += f"\n- Address: {loc.get('address', 'N/A')}"

            pool_hours = loc.get("pool_hours", {})
            if pool_hours:
                loc_text += "\n- Pool Hours:"
                for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    hours = pool_hours.get(day, "CLOSED")
                    loc_text += f"\n  - {day.capitalize()}: {hours}"

            office_hours = loc.get("office_hours", {})
            if office_hours:
                loc_text += "\n- Office Hours:"
                if office_hours.get("monday_friday"):
                    loc_text += f"\n  - Monday-Friday: {office_hours['monday_friday']}"
                if office_hours.get("saturday"):
                    loc_text += f"\n  - Saturday: {office_hours['saturday']}"
                if office_hours.get("sunday"):
                    loc_text += f"\n  - Sunday: {office_hours['sunday']}"
        sections.append(loc_text)

    # === PROGRAMS & LEVELS ===
    levels = config.get("levels", {})
    program_basics = config.get("program_basics", {})

    prog_text = "## PROGRAMS & LEVELS\n"
    prog_text += f"\n### Class Basics"
    prog_text += f"\n- Duration: {program_basics.get('class_duration_minutes', 30)} minutes"
    prog_text += f"\n- Pool Type: {program_basics.get('pool_type', 'indoor')}"
    temp = program_basics.get("pool_temperature_f", [84, 86])
    if isinstance(temp, list) and len(temp) == 2:
        prog_text += f"\n- Pool Temperature: {temp[0]}-{temp[1]}°F"
    prog_text += f"\n- Year-Round Enrollment: {'Yes' if program_basics.get('year_round_enrollment') else 'No'}"
    prog_text += f"\n- Earliest Enrollment: {program_basics.get('earliest_enrollment_months', 3)} months old"

    standard_levels = levels.get("standard_levels", [])
    if standard_levels:
        prog_text += f"\n\n### Standard Levels"
        for level in standard_levels:
            prog_text += f"\n- {level}"

    specialty = levels.get("specialty_programs", [])
    if specialty:
        prog_text += f"\n\n### Specialty Programs"
        for prog in specialty:
            prog_text += f"\n- {prog}"

    sections.append(prog_text)

    # === LEVEL PLACEMENT RULES ===
    placement = config.get("level_placement_rules", {})
    if placement:
        place_text = "## LEVEL PLACEMENT RULES\n"

        for age_group, rules in placement.items():
            if isinstance(rules, list) and rules:
                place_text += f"\n### {age_group.replace('_', ' ').title()}"
                for rule in rules:
                    if isinstance(rule, dict):
                        place_text += f"\n- {rule.get('condition', 'Unknown')} → {rule.get('level', 'Unknown')}"

        sections.append(place_text)

    # === TUITION & PRICING ===
    tuition = config.get("tuition", {})
    if tuition:
        tuit_text = "## TUITION & PRICING\n"

        if tuition.get("billing_summary"):
            tuit_text += f"\n{tuition['billing_summary']}\n"

        if tuition.get("tuition_details"):
            tuit_text += f"\n{tuition['tuition_details']}"

        pricing_rules = tuition.get("pricing_rules", [])
        if pricing_rules:
            tuit_text += "\n\n### Billing Rules"
            for rule in pricing_rules:
                tuit_text += f"\n- {rule}"

        sections.append(tuit_text)

    # === FEES ===
    fees = config.get("fees", {})
    if fees:
        fee_text = "## FEES\n"
        reg_fee = fees.get("registration_fee", {})
        if reg_fee:
            fee_text += f"\n### Registration Fee"
            fee_text += f"\n- Single Swimmer: ${reg_fee.get('single_swimmer', 60)}"
            fee_text += f"\n- Family Maximum: ${reg_fee.get('family_max', 90)}"
            fee_text += f"\n- One-Time: {'Yes' if reg_fee.get('one_time') else 'No'}"

        other_fees = fees.get("other_fees", [])
        if other_fees:
            fee_text += f"\n\n### Other Fees"
            for f in other_fees:
                fee_text += f"\n- {f}"

        sections.append(fee_text)

    # === POLICIES ===
    policies = config.get("policies", {})
    if policies:
        pol_text = "## POLICIES\n"

        for policy_name, rules in policies.items():
            if isinstance(rules, list) and rules:
                pol_text += f"\n### {policy_name.replace('_', ' ').title()}"
                for rule in rules:
                    pol_text += f"\n- {rule}"

        sections.append(pol_text)

    # === DISCOUNTS ===
    discounts = config.get("discounts", [])
    if discounts:
        disc_text = "## DISCOUNTS\n"
        for d in discounts:
            disc_text += f"\n- {d}"
        sections.append(disc_text)

    # === REGISTRATION ===
    registration = config.get("registration", {})
    if registration:
        reg_text = "## REGISTRATION\n"
        reg_text += f"\n- Delivery Methods: {', '.join(registration.get('delivery_methods', ['text', 'email']))}"
        reg_text += f"\n- Link Policy: {registration.get('link_policy', 'send_only_after_level_and_location_confirmed')}"

        link_template = registration.get("registration_link_template", "")
        if link_template:
            reg_text += f"\n- Link Template: {link_template}"

        sections.append(reg_text)

    return "\n\n".join(sections)


# =============================================================================
# CHANNEL-SPECIFIC WRAPPERS
# =============================================================================

WEB_CHAT_WRAPPER = """# WEB CHATBOT SYSTEM PROMPT

You are a helpful assistant for {business_name}.
Your role is to answer questions, help families find the right program, and guide them to enrollment.

## DELIVERY RULES (WEB CHAT)
- Rich text formatting allowed (bold, bullets, links)
- Can include clickable URLs
- Longer explanations are acceptable
- Use markdown formatting for clarity
- Include clear calls-to-action
- Be conversational but professional

## CONTACT COLLECTION
- Progressively collect: name, email, phone
- Don't be pushy - ask naturally during conversation
- One piece of info at a time
- Thank them after each piece provided

## CONVERSATION FLOW
- Start with a friendly greeting
- Ask clarifying questions one at a time
- Provide helpful information before asking for contact
- End each response with a follow-up question or call-to-action

---

{core_brain}

---

## RESPONSE GUIDELINES
- Be helpful, friendly, and professional
- Use bullet points for lists
- Bold important information
- Include relevant links when appropriate
- Always offer next steps
"""

VOICE_BOT_WRAPPER = """# VOICE BOT SYSTEM PROMPT

You are {business_name}'s voice assistant.
Your role is to welcome callers, answer questions, and guide families step by step using spoken conversation only.
You must sound calm, professional, helpful, and natural when spoken.

## ABSOLUTE VOICE RULES (HIGHEST PRIORITY)

### Speech Safety
- NEVER read or spell URLs aloud
- NEVER read full street addresses aloud
- NEVER speak symbols or formatting literally
- Convert all numbers to natural speech ("once a week" not "1x/week", "two hundred sixty six dollars" not "266")
- NEVER say: slash, dot, percent, dash, underscore, colon

### Links (STRICT)
- NEVER invent links
- NEVER offer links until: swimmer is placed into a level, level is explained and confirmed, location is confirmed
- If a link is allowed, say only: "I can send that link by text or email."
- Links are sent out-of-band only (SMS or email)

### Response Structure
- Keep responses to 2-3 sentences maximum
- Ask ONE question per turn
- End each turn with a follow-up question or gentle call-to-action
- Use confirmation checkpoints ("Does that sound right?")

### Conversation Flow
- Always start with: "Hi, thanks for calling {business_name}. My name is the virtual assistant. How can I help you today?"
- Pause for caller's intent before beginning placement
- If general question → answer first, then transition to placement

### Contact Capture (Voice-Safe)
- Email: Repeat letter by letter, say "at" for @, "dot" for period, confirm accuracy
- Phone: Repeat in digit groups, confirm accuracy
- Collect ONE contact method at a time
- Ask for name LAST

## NEVER
- Book a class or say customer is booked
- Invent links or programs
- Use asterisks or hashtags
- Jump into placement without asking how to help first

---

{core_brain}

---

## LEVEL PLACEMENT FLOW

### Step 1 - Always Start With
"Who is the swim class for?"
1. Infant (3 months – 36 months)
2. Child (3–11)
3. Teen (12–17)
4. Adult (18+)

### Step 2 - Ask skill questions ONE at a time based on age group

### Step 3 - Summarize recommended class, ask "Does that sound right?"

### Step 4 - Ask for ZIP code, recommend nearest location, confirm

### Step 5 - Offer to send registration link by text or email
"""

SMS_BOT_WRAPPER = """# SMS BOT SYSTEM PROMPT

You are {business_name}'s text message assistant.
Your role is to answer questions and guide families to enrollment via SMS.

## DELIVERY RULES (SMS)
- Keep responses ULTRA-CONCISE (under 160 characters when possible)
- Plain text ONLY - NO markdown, no bold, no bullets, no asterisks
- Links allowed but use sparingly
- Be direct and brief
- Split long responses into multiple messages if needed
- DO NOT ask for phone number (you already have it)

## RESPONSE FORMAT
- One short paragraph or a few brief lines
- Include registration URLs exactly as provided (plain text)
- Ask ONE question at a time
- Include a brief call-to-action

## CONTACT COLLECTION
- If email provided: thank them, ask for name
- If name provided: thank them, proceed to enrollment
- One contact method is acceptable
- Don't be pushy

## REGISTRATION LINK FORMAT
Generate links as: https://britishswimschool.com/cypress-spring/register/?loc=[LOCATION_CODE]&type=[LEVEL]

Location Codes:
- LALANG: LA Fitness Langham Creek
- LAFCypress: LA Fitness Cypress
- 24Spring: 24Hr Fitness Spring Energy

---

{core_brain}

---

## QUICK REFERENCE

### Level Placement (Ask one question at a time)
- Adult: Comfortable? Float? All four strokes? → Adult Level 1/2/3
- Teen (12-17): Same as adult → Young Adult Level 1/2/3
- Infant (3-24mo): First program? Comfortable? Submerge? → Tadpole/Swimboree
- Infant (24-36mo): Comfortable? Sit? Float? → Tadpole/Swimboree/Seahorse
- Child (3-11): First time? Submerge? Float? Freestyle/backstroke? → Starfish/Minnow/Turtle 1/Turtle 2

### Key Policies (Brief answers)
- No refunds
- No free trials (observation OK)
- 30-day notice for cancellation
- Makeups: report via app, 60-day expiry, max 3
"""


# =============================================================================
# MAIN GENERATOR
# =============================================================================

async def generate_prompts(tenant_id: int):
    """Generate all three channel prompts for a tenant."""

    async with AsyncSessionLocal() as db:
        # Get tenant info
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()

        if not tenant:
            print(f"ERROR: Tenant {tenant_id} not found")
            return

        # Get tenant config
        result = await db.execute(
            select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
        )
        config_record = result.scalar_one_or_none()

        if not config_record or not config_record.config_json:
            print(f"ERROR: Tenant {tenant_id} has no prompt config")
            return

        config = config_record.config_json
        business_name = config.get("display_name", tenant.name)

        # Assemble Core Brain
        core_brain = assemble_core_brain(config, tenant.name)

        # Generate channel prompts
        web_prompt = WEB_CHAT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        voice_prompt = VOICE_BOT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        sms_prompt = SMS_BOT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        # Output
        separator = "=" * 80

        print(f"\n{separator}")
        print(f"GENERATED PROMPTS FOR: {business_name} (Tenant ID: {tenant_id})")
        print(f"Generated: {datetime.now().isoformat()}")
        print(f"{separator}\n")

        print(f"\n{'=' * 80}")
        print("=== WEB CHATBOT PROMPT ===")
        print(f"{'=' * 80}\n")
        print(web_prompt)

        print(f"\n\n{'=' * 80}")
        print("=== VOICE BOT PROMPT ===")
        print(f"{'=' * 80}\n")
        print(voice_prompt)

        print(f"\n\n{'=' * 80}")
        print("=== SMS BOT PROMPT ===")
        print(f"{'=' * 80}\n")
        print(sms_prompt)

        print(f"\n{separator}")
        print("END OF GENERATED PROMPTS")
        print(f"{separator}\n")


async def save_prompts_to_db(tenant_id: int):
    """Generate and save channel prompts to the database."""

    async with AsyncSessionLocal() as db:
        # Get tenant info
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()

        if not tenant:
            print(f"ERROR: Tenant {tenant_id} not found")
            return

        # Get tenant config
        result = await db.execute(
            select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
        )
        config_record = result.scalar_one_or_none()

        if not config_record or not config_record.config_json:
            print(f"ERROR: Tenant {tenant_id} has no prompt config")
            return

        config = config_record.config_json
        business_name = config.get("display_name", tenant.name)

        # Assemble Core Brain
        core_brain = assemble_core_brain(config, tenant.name)

        # Generate channel prompts
        web_prompt = WEB_CHAT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        voice_prompt = VOICE_BOT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        sms_prompt = SMS_BOT_WRAPPER.format(
            business_name=business_name,
            core_brain=core_brain
        )

        # Save to database
        config_record.config_json["web_prompt"] = web_prompt
        config_record.config_json["voice_prompt"] = voice_prompt
        config_record.config_json["sms_prompt"] = sms_prompt

        await db.commit()

        print(f"\n{'=' * 60}")
        print(f"SAVED PROMPTS FOR: {business_name} (Tenant ID: {tenant_id})")
        print(f"{'=' * 60}")
        print(f"\n✓ web_prompt: {len(web_prompt)} characters")
        print(f"✓ voice_prompt: {len(voice_prompt)} characters")
        print(f"✓ sms_prompt: {len(sms_prompt)} characters")
        print(f"\nPrompts are now active and will be used by the system.")


if __name__ == "__main__":
    tenant_id = 1  # Default to tenant 1
    save_mode = False

    args = sys.argv[1:]

    # Parse arguments
    for arg in args:
        if arg == "--save":
            save_mode = True
        else:
            try:
                tenant_id = int(arg)
            except ValueError:
                print(f"Invalid argument: {arg}")
                print("Usage: python scripts/generate_channel_prompts.py [tenant_id] [--save]")
                sys.exit(1)

    if save_mode:
        asyncio.run(save_prompts_to_db(tenant_id))
    else:
        asyncio.run(generate_prompts(tenant_id))
