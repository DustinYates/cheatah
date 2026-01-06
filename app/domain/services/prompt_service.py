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
        """Activate a prompt bundle (deactivates others).

        Args:
            tenant_id: The tenant context (used for access control). If None (global admin),
                       the bundle's actual tenant_id is used for deactivating other bundles.
            bundle_id: The ID of the bundle to activate.
        """
        bundle = await self.prompt_repo.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None

        # Use the bundle's actual tenant_id to deactivate other bundles
        # This ensures we only deactivate bundles belonging to the same tenant
        actual_tenant_id = bundle.tenant_id
        await self.prompt_repo.deactivate_all_bundles(actual_tenant_id)

        bundle.is_active = True
        await self.session.commit()
        await self.session.refresh(bundle)

        # Invalidate cache for the bundle's actual tenant
        PromptCache.invalidate(actual_tenant_id)

        return bundle

    async def publish_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Publish a bundle to production."""
        result = await self.prompt_repo.publish_bundle(tenant_id, bundle_id)
        if result:
            # Invalidate cache for the bundle's actual tenant (not the passed tenant_id)
            PromptCache.invalidate(result.tenant_id)
        return result

    async def set_testing(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Set a bundle to testing status."""
        result = await self.prompt_repo.set_testing(tenant_id, bundle_id)
        if result:
            # Invalidate cache for the bundle's actual tenant
            PromptCache.invalidate(result.tenant_id)
        return result

    async def deactivate_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Deactivate a bundle (move from production to draft)."""
        result = await self.prompt_repo.deactivate_bundle(tenant_id, bundle_id)
        if result:
            # Invalidate cache for the bundle's actual tenant
            PromptCache.invalidate(result.tenant_id)
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
            "- Use abbreviations sparingly and only when clear\n"
            "- DO NOT ask for their phone number - you already have it since they texted you"
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
- Naturally ask for their name and email when appropriate
- DO NOT ask for their phone number - you already have it from caller ID
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

        return await self.compose_prompt_chat_from_base(base_prompt, context)

    async def compose_prompt_chat_from_base(
        self, base_prompt: str, context: dict | None = None
    ) -> str:
        """Attach chat-specific guidance to a pre-composed base prompt."""
        contact_context = self._build_chat_contact_context(context)
        return base_prompt + contact_context + self._chat_instructions()

    def _build_chat_contact_context(self, context: dict | None) -> str:
        if not context:
            return ""

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

            if not collected_email and not collected_phone:
                contact_context += f"- Consider naturally asking for email OR phone when contextually appropriate\n"
            elif collected_email and not collected_phone:
                contact_context += f"- If helpful, you can ask if they'd like to share phone number as well\n"
            elif collected_phone and not collected_email:
                contact_context += f"- If helpful, you can ask if they'd like to share email as well\n"

            if (collected_email or collected_phone) and not collected_name:
                contact_context += f"- You can politely ask for their name once if it would be helpful\n"
            return contact_context

        if turn_count >= 2:
            contact_context = f"\n\nCURRENT CONVERSATION STATUS:\n"
            contact_context += f"- No contact information collected yet\n"
            contact_context += f"- Consider naturally asking for email OR phone when contextually appropriate (after answering questions, when discussing services, etc.)\n"
            return contact_context

        return ""

    def _chat_instructions(self) -> str:
        return """

WEB CHAT COMMUNICATION STYLE:

Your Approach:
- Use natural, conversational language appropriate for web chat
- Balance being helpful with being concise - provide enough detail to be useful
- Ask ONE question at a time to avoid overwhelming the customer
- Follow up questions should feel natural and conversational

CRITICAL - KEEP THE CONVERSATION FLOWING:
- ALWAYS end your response with a question or invitation to continue
- Never give dead-end responses that leave the customer with nothing to respond to
- After answering a question, ask a relevant follow-up to understand their needs better
- Good follow-up examples:
  * "What age group would this be for?"
  * "Would you like me to tell you more about our options?"
  * "Is there a particular day or time that works best for you?"
  * "What questions do you have about getting started?"
- The conversation should feel like a natural back-and-forth dialogue
- Always finish complete sentences; never end with a dangling conjunction like "and" or "or"

CRITICAL - NO EMAIL COMMUNICATION:
- NEVER offer to email or send information to the customer
- NEVER say "I can email you...", "Would you like me to send you...", or similar
- Instead, direct customers to URLs/links where they can find information
- If asked for schedules/pricing/details, share URLs if available OR offer to have someone call them
- You may ACCEPT and CAPTURE emails when customers provide them, but don't offer to send emails

Contact Information Collection:
- Remember to collect contact information naturally during the conversation
- Only ask when it makes sense contextually (after answering questions, discussing services, etc.)
- Follow the progressive collection pattern described in your base instructions
- Be helpful and friendly, never pushy or salesy
- Prefer offering a callback over offering to email information"""

    async def compose_prompt_sms_qualification(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str | None:
        """Compose SMS-specific prompt for lead qualification follow-ups.

        This prompt guides the AI to collect qualification data:
        - Name (if not already captured)
        - Email address
        - Budget/price range
        - Timeline/urgency
        - Specific needs/services interested in

        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context dict that may include:
                - collected_name: bool - Whether user's name has been collected
                - collected_email: bool - Whether user's email has been collected
                - collected_phone: bool - Whether user's phone has been collected
                - collected_budget: bool - Whether budget has been collected
                - collected_timeline: bool - Whether timeline has been collected
                - collected_needs: bool - Whether needs have been collected

        Returns:
            Composed prompt string with qualification instructions, or None if no prompt is configured
        """
        base_prompt = await self.compose_prompt_sms(tenant_id, context)

        if base_prompt is None:
            return None

        # Build qualification context based on what's been collected
        qualification_context = ""
        if context:
            collected_name = context.get("collected_name", False)
            collected_email = context.get("collected_email", False)
            collected_budget = context.get("collected_budget", False)
            collected_timeline = context.get("collected_timeline", False)
            collected_needs = context.get("collected_needs", False)

            still_needed = []
            if not collected_name:
                still_needed.append("name")
            if not collected_email:
                still_needed.append("email")
            if not collected_needs:
                still_needed.append("what they're looking for")
            if not collected_timeline:
                still_needed.append("timeline")
            if not collected_budget:
                still_needed.append("budget range")

            if still_needed:
                qualification_context = f"\n\nINFORMATION TO COLLECT (naturally, one at a time):\n"
                qualification_context += f"Still need: {', '.join(still_needed)}\n"
                qualification_context += "Priority order: name > email > needs > timeline > budget\n"

        qualification_instructions = """

LEAD QUALIFICATION GOALS:
You are following up to qualify this lead. Your goal is to naturally collect:
1. Their name (if not already known)
2. Email address (for sending information)
3. What they're looking for (specific services/needs)
4. Their timeline (when they need it)
5. Budget expectations (price range they're considering)

IMPORTANT: DO NOT ask for their phone number - you already have it since they texted you.

APPROACH:
- Be warm and helpful, not pushy or sales-y
- Answer their questions first before asking yours
- Ask ONE qualifying question per message
- If they provide information voluntarily, acknowledge it
- Keep messages SHORT (under 160 chars when possible)
- Be conversational, not like filling out a form
- If they seem uninterested, don't push - thank them and leave the door open"""

        return base_prompt + qualification_context + qualification_instructions

    async def compose_prompt_sms_followup(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str | None:
        """Compose SMS-specific prompt for generating follow-up outreach messages.

        This prompt guides the LLM to compose a contextual follow-up SMS to re-engage
        with leads who previously contacted the business but didn't complete the conversation.

        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context dict that may include:
                - lead_name: Lead's name if known
                - first_name: Lead's first name
                - lead_source: How they originally contacted us (voice_call, email, sms, chatbot)
                - time_since_contact: Human-readable time since original contact
                - conversation_summary: Summary of original conversation

        Returns:
            Composed prompt string for follow-up message generation, or None if no prompt configured
        """
        base_prompt = await self.compose_prompt(tenant_id, context)

        if base_prompt is None:
            return None

        followup_instructions = """

SMS FOLLOW-UP MESSAGE GENERATION:

You are composing a follow-up SMS message to re-engage with someone who previously contacted the business but the conversation didn't complete or they didn't respond.

CRITICAL CONSTRAINTS:
- Message MUST be under 160 characters (standard SMS limit)
- NO markdown, links, URLs, or special formatting
- Use plain, conversational text only
- Be warm and friendly, not pushy or salesy

MESSAGE REQUIREMENTS:
- Reference the previous interaction naturally (call, email, chat, etc.)
- Use their first name if known
- Include a simple question or invitation to continue the conversation
- Match the business's friendly, professional tone
- Make it feel personal, not automated
- End with an open question to encourage response

EXAMPLES OF GOOD MESSAGES:
- "Hi John! Following up from earlier. Still have questions about our services?"
- "Hey there! Thanks for reaching out. Did you find what you needed?"
- "Hi Sarah! Wanted to check in after your call. How can I help?"

Generate ONLY the SMS message text, nothing else. No quotes, no explanation, just the message."""

        return base_prompt + followup_instructions
