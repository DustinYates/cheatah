"""Prompt service for managing prompt bundles and composition."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus
from app.persistence.repositories.prompt_repository import PromptRepository


class PromptService:
    """Service for prompt bundle management and composition."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize prompt service."""
        self.session = session
        self.prompt_repo = PromptRepository(session)

    async def get_active_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the active prompt bundle for a tenant."""
        return await self.prompt_repo.get_active_bundle(tenant_id)

    async def get_production_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the production prompt bundle for a tenant."""
        return await self.prompt_repo.get_production_bundle(tenant_id)

    async def get_draft_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the draft prompt bundle for a tenant."""
        return await self.prompt_repo.get_draft_bundle(tenant_id)

    async def compose_prompt(
        self, tenant_id: int | None, context: dict | None = None, use_draft: bool = False
    ) -> str | None:
        """Compose final prompt from global base + tenant overrides.

        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context for prompt composition
            use_draft: If True, use draft bundle for testing

        Returns:
            Composed prompt string, or None if no prompt is configured
        """
        global_bundle = await self.prompt_repo.get_global_base_bundle()
        
        tenant_bundle = None
        if tenant_id is not None:
            if use_draft:
                tenant_bundle = await self.prompt_repo.get_draft_bundle(tenant_id)
                if not tenant_bundle:
                    tenant_bundle = await self.prompt_repo.get_production_bundle(tenant_id)
            else:
                tenant_bundle = await self.prompt_repo.get_production_bundle(tenant_id)
                if not tenant_bundle:
                    tenant_bundle = await self.prompt_repo.get_active_bundle(tenant_id)

        all_sections = []
        
        if global_bundle:
            global_sections = await self.prompt_repo.get_sections(global_bundle.id)
            all_sections.extend(global_sections)
        
        if tenant_bundle:
            tenant_sections = await self.prompt_repo.get_sections(tenant_bundle.id)
            all_sections.extend(tenant_sections)

        if not all_sections:
            # No prompt configured - return None to signal error
            return None
        
        section_map: dict[str, tuple[str, int]] = {}
        for section in all_sections:
            section_map[section.section_key] = (section.content, section.order)
        
        sorted_sections = sorted(
            section_map.items(),
            key=lambda x: (x[1][1], x[0])
        )
        
        prompt_parts = [content for _, (content, _) in sorted_sections]
        
        return "\n\n".join(prompt_parts)

    async def activate_bundle(
        self, tenant_id: int | None, bundle_id: int
    ) -> PromptBundle | None:
        """Activate a prompt bundle (deactivates others)."""
        bundle = await self.prompt_repo.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None

        await self.prompt_repo.deactivate_all_bundles(tenant_id)

        bundle.is_active = True
        await self.session.commit()
        await self.session.refresh(bundle)
        return bundle

    async def publish_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Publish a bundle to production."""
        return await self.prompt_repo.publish_bundle(tenant_id, bundle_id)

    async def set_testing(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Set a bundle to testing status."""
        return await self.prompt_repo.set_testing(tenant_id, bundle_id)

    async def deactivate_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Deactivate a bundle (move from production to draft)."""
        return await self.prompt_repo.deactivate_bundle(tenant_id, bundle_id)

    async def compose_prompt_sms(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str | None:
        """Compose SMS-specific prompt with constraints.
        
        Returns:
            Composed prompt string with SMS constraints, or None if no prompt is configured
        """
        base_prompt = await self.compose_prompt(tenant_id, context)
        
        if base_prompt is None:
            return None
        
        sms_instructions = (
            "\n\nIMPORTANT SMS CONSTRAINTS:\n"
            "- Keep responses SHORT (under 160 characters when possible)\n"
            "- NO markdown formatting (no **bold**, *italic*, links, etc.)\n"
            "- Use plain text only\n"
            "- Be concise and direct\n"
            "- If response is too long, split into multiple messages\n"
            "- Use abbreviations sparingly and only when clear"
        )
        
        return base_prompt + sms_instructions

    async def compose_prompt_voice(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str | None:
        """Compose voice-specific prompt with constraints for phone calls.
        
        Voice prompts are optimized for:
        - Natural spoken language (no markdown, links, etc.)
        - Short responses (1-2 sentences + question)
        - Clear pronunciation
        - Guardrails against sensitive content
        
        Returns:
            Composed prompt string with voice constraints, or None if no prompt is configured
        """
        base_prompt = await self.compose_prompt(tenant_id, context)
        
        if base_prompt is None:
            return None
        
        voice_instructions = """

IMPORTANT VOICE CALL CONSTRAINTS:

Response Style:
- Keep responses to 1-2 SHORT sentences maximum, then ask a question
- Speak naturally as if on a phone call
- NO markdown, bullet points, links, or special formatting
- Use conversational language, not formal writing
- End with a question to keep the conversation moving

Prohibited Topics (DO NOT):
- Process payments or discuss credit card information
- Provide legal advice or specific legal guidance
- Provide medical advice or diagnoses
- Make guarantees or binding promises
- Discuss specific pricing without verified information
- Share confidential business information

If Asked About Prohibited Topics:
- Politely redirect to speak with a team member
- Offer to have someone follow up with them

Lead Capture:
- Listen for name, email, and callback preferences
- If caller mentions contact info, acknowledge you've noted it
- Ask for name and best way to reach them when appropriate

Call Ending:
- If caller says goodbye, thank them warmly and end professionally
- Always confirm any follow-up actions before ending"""
        
        return base_prompt + voice_instructions

