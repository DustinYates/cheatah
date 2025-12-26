"""Prompt service for managing prompt bundles and composition."""

import time
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus
from app.persistence.repositories.prompt_repository import PromptRepository


class PromptCache:
    """Simple in-memory cache for composed prompts with TTL."""
    
    # Cache structure: {cache_key: (prompt_text, timestamp)}
    _cache: ClassVar[dict[str, tuple[str, float]]] = {}
    _ttl_seconds: ClassVar[int] = 300  # 5 minute cache TTL
    
    @classmethod
    def get(cls, key: str) -> str | None:
        """Get cached prompt if not expired."""
        if key in cls._cache:
            prompt, timestamp = cls._cache[key]
            if time.time() - timestamp < cls._ttl_seconds:
                return prompt
            # Expired - remove from cache
            del cls._cache[key]
        return None
    
    @classmethod
    def set(cls, key: str, prompt: str) -> None:
        """Cache a prompt with current timestamp."""
        cls._cache[key] = (prompt, time.time())
    
    @classmethod
    def invalidate(cls, tenant_id: int | None = None) -> None:
        """Invalidate cache entries for a tenant, or all if tenant_id is None."""
        if tenant_id is None:
            cls._cache.clear()
        else:
            # Remove all keys containing this tenant_id
            keys_to_remove = [k for k in cls._cache if f"tenant:{tenant_id}" in k]
            for key in keys_to_remove:
                del cls._cache[key]


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
        
        # Invalidate cache for this tenant
        PromptCache.invalidate(tenant_id)
        
        return bundle

    async def publish_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Publish a bundle to production."""
        result = await self.prompt_repo.publish_bundle(tenant_id, bundle_id)
        if result:
            # Invalidate cache for this tenant
            PromptCache.invalidate(tenant_id)
        return result

    async def set_testing(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Set a bundle to testing status."""
        result = await self.prompt_repo.set_testing(tenant_id, bundle_id)
        if result:
            # Invalidate cache for this tenant
            PromptCache.invalidate(tenant_id)
        return result

    async def deactivate_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Deactivate a bundle (move from production to draft)."""
        result = await self.prompt_repo.deactivate_bundle(tenant_id, bundle_id)
        if result:
            # Invalidate cache for this tenant
            PromptCache.invalidate(tenant_id)
        return result

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
        - Natural, warm spoken language
        - Complete, helpful answers (2-4 sentences)
        - Conversational flow
        - Guardrails against sensitive content
        
        Uses caching to reduce database queries for frequently accessed prompts.
        
        Returns:
            Composed prompt string with voice constraints, or None if no prompt is configured
        """
        # Check cache first
        cache_key = f"voice:tenant:{tenant_id}:context:{hash(str(context)) if context else 'none'}"
        cached_prompt = PromptCache.get(cache_key)
        if cached_prompt:
            return cached_prompt
        
        base_prompt = await self.compose_prompt(tenant_id, context)
        
        if base_prompt is None:
            return None
        
        voice_instructions = """

VOICE CALL COMMUNICATION STYLE:

Your Personality:
- Sound warm, friendly, and genuinely helpful - like a knowledgeable friend
- Speak naturally and conversationally, not like a scripted robot
- Show empathy and understanding when callers express concerns
- Be patient and take time to fully answer questions

CRITICAL - FACTS AND HONESTY:
- ONLY state information that appears in the VERIFIED BUSINESS FACTS section or in the conversation
- NEVER invent prices, hours, addresses, phone numbers, email addresses, or policies
- If asked about something not in the FACTS, say: "I don't have that specific information, but I can take your details and have someone get back to you with the answer."
- It's better to admit you don't know than to guess wrong
- DO NOT make up URLs, websites, or links

Answering Questions:
- FIRST: Directly answer what the caller asked - don't deflect to a question
- Provide complete, useful information in 2-4 natural sentences
- Only ask a follow-up question when it genuinely helps the conversation
- If you don't have the information, say so honestly and offer alternatives

Response Format:
- NO markdown, bullet points, links, or special formatting
- Use natural spoken language - contractions are fine ("we're", "you'll", "that's")
- Vary your responses - don't repeat the same phrases
- Speak at a comfortable pace - complete thoughts, not fragments

Prohibited Topics (redirect politely):
- Payment processing or credit card information
- Legal or medical advice
- Guarantees or binding promises

Lead Capture:
- Naturally ask for their name and contact info when appropriate
- Don't make it feel like filling out a form

Call Ending:
- When caller says goodbye, thank them warmly
- Confirm any next steps or follow-up actions"""
        
        composed_prompt = base_prompt + voice_instructions
        
        # Cache the composed prompt
        PromptCache.set(cache_key, composed_prompt)
        
        return composed_prompt

    async def compose_prompt_chat(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str | None:
        """Compose chat-specific prompt with contact collection context.
        
        Chat prompts are optimized for:
        - Natural, conversational web chat interactions
        - Context-aware contact information collection
        - Progressive, non-pushy lead capture
        - One-question-at-a-time approach
        
        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context dict that may include:
                - collected_name: bool - Whether user's name has been collected
                - collected_email: bool - Whether user's email has been collected
                - collected_phone: bool - Whether user's phone has been collected
                - turn_count: int - Number of turns in conversation
                
        Returns:
            Composed prompt string with chat-specific instructions, or None if no prompt is configured
        """
        base_prompt = await self.compose_prompt(tenant_id, context)
        
        if base_prompt is None:
            return None
        
        # Build contact collection context based on what's been collected
        contact_context = ""
        if context:
            collected_name = context.get("collected_name", False)
            collected_email = context.get("collected_email", False)
            collected_phone = context.get("collected_phone", False)
            turn_count = context.get("turn_count", 0)
            
            contact_status = []
            if collected_name:
                contact_status.append("name")
            if collected_email:
                contact_status.append("email")
            if collected_phone:
                contact_status.append("phone")
            
            if contact_status:
                contact_context = f"\n\nCURRENT CONVERSATION STATUS:\n"
                contact_context += f"- Contact information collected: {', '.join(contact_status)}\n"
                contact_context += f"- Do not ask for information you already have\n"
                
                # Guide on what to ask for next
                if not collected_email and not collected_phone:
                    contact_context += f"- Consider naturally asking for email OR phone when contextually appropriate\n"
                elif collected_email and not collected_phone:
                    contact_context += f"- If helpful, you can ask if they'd like to share phone number as well\n"
                elif collected_phone and not collected_email:
                    contact_context += f"- If helpful, you can ask if they'd like to share email as well\n"
                
                if (collected_email or collected_phone) and not collected_name:
                    contact_context += f"- You can politely ask for their name once if it would be helpful\n"
            else:
                # No contact info collected yet
                if turn_count >= 2:  # After a few exchanges
                    contact_context = f"\n\nCURRENT CONVERSATION STATUS:\n"
                    contact_context += f"- No contact information collected yet\n"
                    contact_context += f"- Consider naturally asking for email OR phone when contextually appropriate (after answering questions, when discussing services, etc.)\n"
        
        chat_instructions = """
        
WEB CHAT COMMUNICATION STYLE:

Your Approach:
- Use natural, conversational language appropriate for web chat
- Balance being helpful with being concise - provide enough detail to be useful
- Ask ONE question at a time to avoid overwhelming the customer
- Follow up questions should feel natural and conversational

Contact Information Collection:
- Remember to collect contact information naturally during the conversation
- Only ask when it makes sense contextually (after answering questions, discussing services, etc.)
- Follow the progressive collection pattern described in your base instructions
- Be helpful and friendly, never pushy or salesy"""
        
        return base_prompt + contact_context + chat_instructions

