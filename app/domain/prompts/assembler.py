"""Assembles final system prompt from base config + tenant config."""

from datetime import datetime
from typing import Optional

from app.domain.prompts.base_configs import get_base_config
from app.domain.prompts.base_configs.common import SMS_CONSTRAINTS, VOICE_WRAPPER
from app.domain.prompts.renderer import render_section
from app.domain.prompts.schemas.v1.bss_schema import BSSTenantConfig


class PromptAssembler:
    """Assembles system prompts from base + tenant configurations.

    This class combines:
    1. Base config sections (hardcoded Python rules)
    2. Tenant config sections (rendered from JSON)
    3. Channel-specific wrappers (voice/SMS modifications)

    The final prompt is ordered according to the assembly.system_prompt_sections_order
    defined in the tenant config.
    """

    def __init__(self, business_type: str = "bss"):
        """Initialize the assembler.

        Args:
            business_type: The type of business (e.g., "bss" for British Swim School)
        """
        self.business_type = business_type
        self.base_config = get_base_config(business_type)

    def assemble(
        self,
        tenant_config: BSSTenantConfig,
        channel: str = "chat",
        context: Optional[dict] = None,
    ) -> str:
        """Assemble the final system prompt.

        Args:
            tenant_config: Validated tenant configuration
            channel: Channel type ("chat", "voice", "sms")
            context: Runtime context (collected contact info, turn count, etc.)

        Returns:
            Assembled system prompt string
        """
        # Get section order from tenant config (or use default)
        section_order = tenant_config.assembly.system_prompt_sections_order

        # Build all sections (base + tenant)
        sections = self._build_sections(tenant_config)

        # Assemble in order, skipping empty sections
        prompt_parts = []
        for section_key in section_order:
            content = sections.get(section_key)
            if content:
                prompt_parts.append(content)

        # Join sections
        prompt = "\n\n".join(prompt_parts)

        # Apply channel-specific modifications
        prompt = self._apply_channel_wrapper(prompt, channel, context)

        return prompt

    def _build_sections(self, tenant_config: BSSTenantConfig) -> dict[str, str]:
        """Build all sections from base config and tenant config.

        Args:
            tenant_config: The tenant configuration

        Returns:
            Dict mapping section_key to rendered content
        """
        sections: dict[str, str] = {}

        # Add base sections from Python config
        base_sections = self.base_config.get_all_sections()
        for key, content in base_sections.items():
            if content:
                sections[key] = content

        # Render tenant sections from JSON config
        tenant_section_keys = [
            "business_info",
            "locations",
            "program_basics",
            "levels",
            "level_placement_rules",
            "tuition",
            "fees",
            "discounts",
            "policies",
            "registration",
        ]

        for key in tenant_section_keys:
            rendered = render_section(key, tenant_config)
            if rendered:
                sections[key] = rendered

        return sections

    def _apply_channel_wrapper(
        self,
        prompt: str,
        channel: str,
        context: Optional[dict],
    ) -> str:
        """Apply channel-specific modifications to the prompt.

        Args:
            prompt: The base assembled prompt
            channel: Channel type
            context: Runtime context

        Returns:
            Modified prompt with channel-specific wrapper
        """
        if channel == "voice":
            # Wrap in voice-specific instructions
            return VOICE_WRAPPER.format(base_prompt=prompt)

        elif channel == "sms":
            # Add SMS constraints at the end
            return prompt + "\n\n" + SMS_CONSTRAINTS

        elif channel == "chat" and context:
            # Add contact collection context for chat
            return self._add_chat_context(prompt, context)

        return prompt

    def _add_chat_context(self, prompt: str, context: dict) -> str:
        """Add runtime contact collection context to chat prompt.

        Args:
            prompt: The base prompt
            context: Runtime context with collected info status

        Returns:
            Prompt with contact collection guidance
        """
        collected_name = context.get("collected_name", False)
        collected_email = context.get("collected_email", False)
        collected_phone = context.get("collected_phone", False)
        turn_count = context.get("turn_count", 0)

        # Build context section
        context_lines = ["\n## CURRENT CONVERSATION CONTEXT"]

        # Add current date/time so the chatbot knows the actual date
        now = datetime.now()
        context_lines.append(f"Today's date: {now.strftime('%A, %B %d, %Y')}")

        # What's been collected
        collected = []
        if collected_name:
            collected.append("name")
        if collected_email:
            collected.append("email")
        if collected_phone:
            collected.append("phone")

        if collected:
            context_lines.append(f"Already collected: {', '.join(collected)}")
        else:
            context_lines.append("No contact information collected yet.")

        # What's still needed
        needed = []
        if not collected_email and not collected_phone:
            needed.append("email or phone (at least one)")
        if not collected_name and (collected_email or collected_phone):
            needed.append("name")

        if needed:
            context_lines.append(f"Still need: {', '.join(needed)}")
        else:
            context_lines.append("All required contact info collected.")

        # Guidance based on turn count
        if turn_count >= 3 and not (collected_email or collected_phone):
            context_lines.append(
                "Suggestion: After answering the user's question, "
                "gently ask for email to send more information."
            )

        return prompt + "\n".join(context_lines)


def assemble_prompt(
    tenant_config: BSSTenantConfig,
    business_type: str = "bss",
    channel: str = "chat",
    context: Optional[dict] = None,
) -> str:
    """Convenience function to assemble a prompt.

    Args:
        tenant_config: Validated tenant configuration
        business_type: Type of business
        channel: Channel type
        context: Runtime context

    Returns:
        Assembled system prompt
    """
    assembler = PromptAssembler(business_type=business_type)
    return assembler.assemble(tenant_config, channel=channel, context=context)
