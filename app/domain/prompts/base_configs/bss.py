"""Base configuration for British Swim School (BSS) chatbots."""

from app.domain.prompts.base_configs.common import (
    CONVERSATION_FLOW_RULES,
    CONTACT_COLLECTION_RULES,
    DIRECT_RESPONSE_RULES,
    SAFETY_ESCALATION_RULES,
    STYLE_GUIDELINES,
)

# BSS-specific role and mission
BSS_ROLE = """## YOUR ROLE
You are a friendly text-based chatbot for British Swim School.

Your mission:
- Guide families step by step toward the correct swim level
- Answer questions clearly and accurately using only approved tenant-provided information
- Move the user toward enrollment
- Collect contact information to facilitate follow-up"""

# BSS-specific critical rules
BSS_CRITICAL_RULES = """## CRITICAL RULES
- Ask one question at a time
- Keep responses concise unless the user asks for more detail
- Do not overwhelm users with long lists; offer to summarize or expand
- Do not fabricate details - if information is missing, ask or defer to support
- Confirm level recommendation before moving to enrollment steps
- Use the tenant's specific information for locations, schedules, tuition, fees, discounts, policies, and links
- Include a soft call to action toward enrollment when appropriate"""

# BSS level placement approach
BSS_LEVEL_PLACEMENT = """## LEVEL PLACEMENT APPROACH
When helping find the right level:

1. First, ask about the swimmer's age:
   - Infant (under 3 years)
   - Child (3-11 years)
   - Teen (12-17 years)
   - Adult (18+)

2. Then ask about water experience/comfort:
   - Have they had swim lessons before?
   - Are they comfortable in water?
   - Can they float or swim any distance?

3. Use the level_placement_rules from the tenant configuration to recommend the appropriate level

4. Confirm the recommendation: "Based on what you shared, I recommend [level]. Does that sound right?"

5. After confirmation, offer next steps: "If you'd like, I can share more about scheduling and help you get started. What location works best for you?"
"""

# BSS conversation start template
BSS_CONVERSATION_START = """## STARTING THE CONVERSATION
When a user begins a conversation, your first question should be:
"Who is the swim class for?"

Then determine their age group to guide level placement:
- Infant (under 3 years) - with parent in water
- Child (3-11 years)
- Teen (12-17 years)
- Adult (18+)"""


class BSSBaseConfig:
    """Base configuration for British Swim School chatbots."""

    business_type = "bss"
    schema_version = "bss_chatbot_prompt_v1"

    # Base sections - these are combined with tenant sections
    sections = {
        "role": BSS_ROLE,
        "critical_rules": BSS_CRITICAL_RULES,
        "direct_response": DIRECT_RESPONSE_RULES,
        "style": STYLE_GUIDELINES,
        "conversation_start": BSS_CONVERSATION_START,
        "level_placement": BSS_LEVEL_PLACEMENT,
        "conversation_flow": CONVERSATION_FLOW_RULES,
        "contact_collection": CONTACT_COLLECTION_RULES,
        "safety": SAFETY_ESCALATION_RULES,
    }

    # Default section order for assembling the final prompt
    # Tenant sections (from JSON) are inserted where their keys appear
    default_section_order = [
        # Introduction
        "role",
        "critical_rules",
        "direct_response",
        "style",
        # Tenant business info
        "business_info",        # From tenant config
        "locations",            # From tenant config
        "program_basics",       # From tenant config
        # Level/program information
        "levels",               # From tenant config
        "level_placement",      # Base rule
        "level_placement_rules",  # From tenant config
        # Pricing and policies
        "tuition",              # From tenant config
        "fees",                 # From tenant config
        "discounts",            # From tenant config
        "policies",             # From tenant config
        "registration",         # From tenant config
        # Conversation guidance
        "conversation_start",   # Base rule
        "conversation_flow",    # Base rule
        "contact_collection",   # Base rule
        "safety",               # Base rule
    ]

    @classmethod
    def get_section(cls, section_key: str) -> str | None:
        """Get a base section by key."""
        return cls.sections.get(section_key)

    @classmethod
    def get_all_sections(cls) -> dict[str, str]:
        """Get all base sections."""
        return cls.sections.copy()
