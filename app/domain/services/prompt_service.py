"""Prompt service for managing prompt bundles and composition."""

import logging
import time
from typing import ClassVar

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.domain.prompts.assembler import PromptAssembler
from app.domain.prompts.base_configs.bss import (
    BSS_EQUIPMENT_KNOWLEDGE,
    BSS_LOCATION_LINK_GUARDRAILS,
)
from app.domain.prompts.base_configs.common import (
    SWIMMER_IDENTIFICATION_RULES,
    PRONOUN_USAGE_RULES,
)
from app.domain.prompts.schemas.v1.bss_schema import BSSTenantConfig
from app.persistence.models.prompt import PromptBundle, PromptChannel, PromptSection, PromptStatus
from app.persistence.repositories.prompt_repository import PromptRepository
from app.persistence.repositories.tenant_prompt_config_repository import TenantPromptConfigRepository


logger = logging.getLogger(__name__)


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
        self.prompt_config_repo = TenantPromptConfigRepository(session)

    async def get_active_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the active prompt bundle for a tenant."""
        return await self.prompt_repo.get_active_bundle(tenant_id)

    async def get_production_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the production prompt bundle for a tenant."""
        return await self.prompt_repo.get_production_bundle(tenant_id)

    async def get_draft_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the draft prompt bundle for a tenant."""
        return await self.prompt_repo.get_draft_bundle(tenant_id)

    async def has_dedicated_voice_prompt(self, tenant_id: int | None) -> bool:
        """Check if tenant has a dedicated voice prompt bundle.

        Returns True if there's a voice-channel prompt bundle, which means
        we should NOT apply transform_chat_to_voice wrapping.
        """
        voice_bundle = await self.prompt_repo.get_voice_bundle(tenant_id)
        return voice_bundle is not None

    async def compose_prompt(
        self,
        tenant_id: int | None,
        context: dict | None = None,
        use_draft: bool = False,
        channel: str = PromptChannel.CHAT.value,
    ) -> str | None:
        """Compose final prompt from global base + tenant overrides.

        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context for prompt composition
            use_draft: If True, use draft bundle for testing
            channel: Channel type (chat, voice, sms, email)

        Returns:
            Composed prompt string, or None if no prompt is configured
        """
        global_bundle = await self.prompt_repo.get_global_base_bundle(channel)

        tenant_bundle = None
        if tenant_id is not None:
            if use_draft:
                tenant_bundle = await self.prompt_repo.get_draft_bundle(tenant_id, channel)
                if not tenant_bundle:
                    tenant_bundle = await self.prompt_repo.get_production_bundle(tenant_id, channel)
            else:
                tenant_bundle = await self.prompt_repo.get_production_bundle(tenant_id, channel)
                if not tenant_bundle:
                    tenant_bundle = await self.prompt_repo.get_active_bundle(tenant_id, channel)

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

        Uses v2 JSON-based prompts if available, falls back to v1.

        Returns:
            Composed prompt string with SMS constraints, or None if no prompt is configured
        """
        # Try v2 first if tenant_id is provided
        if tenant_id is not None:
            v2_prompt = await self.compose_prompt_v2_sms(tenant_id, context)
            if v2_prompt is not None:
                logger.debug(f"Using v2 SMS prompt for tenant {tenant_id}")
                return v2_prompt
            logger.debug(f"No v2 config for tenant {tenant_id}, falling back to v1")

        # Fall back to v1
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

        Voice prompts are composed in this priority:
        1. Try v2 JSON-based prompt (if tenant has config)
        2. If tenant has a dedicated voice prompt bundle, use it directly (no extra wrapping)
        3. Otherwise, fall back to chat prompt + voice instructions

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

        # Try v2 first if tenant_id is provided
        if tenant_id is not None:
            v2_prompt = await self.compose_prompt_v2_voice(tenant_id, context)
            if v2_prompt is not None:
                logger.debug(f"Using v2 voice prompt for tenant {tenant_id}")
                PromptCache.set(cache_key, v2_prompt)
                return v2_prompt
            logger.debug(f"No v2 config for tenant {tenant_id}, falling back to v1")

        # First, try to get a dedicated voice prompt bundle
        voice_prompt = await self.compose_prompt(
            tenant_id, context, channel=PromptChannel.VOICE.value
        )

        if voice_prompt:
            # Tenant has a dedicated voice prompt - use it directly (already voice-safe)
            PromptCache.set(cache_key, voice_prompt)
            return voice_prompt

        # Fall back to chat prompt + voice instructions
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

        Uses v2 JSON-based prompts if available, falls back to v1.

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
        # Try v2 first if tenant_id is provided
        if tenant_id is not None:
            v2_prompt = await self.compose_prompt_v2_chat(tenant_id, context)
            if v2_prompt is not None:
                logger.info(f"[PROMPT] Using v2 chat prompt for tenant {tenant_id}")
                return v2_prompt
            logger.info(f"[PROMPT] No v2 config for tenant {tenant_id}, falling back to v1")

        # Fall back to v1
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
- Do NOT repeat back or confirm names, emails, dates, or other information the user provided - they can see what they typed
- Skip phrases like "Got it, [Name]" or "Is that right?" - just continue to the next question or response
- Avoid filler phrases at the start of responses like "That makes total sense!", "Great question!", "Absolutely!", "Of course!" - just answer directly

CRITICAL - KEEP THE CONVERSATION FLOWING:
- End your response with a question or invitation to continue
- Never give dead-end responses that leave the customer with nothing to respond to
- After answering a question, you may ask a relevant follow-up OR simply invite them to ask more
- IMPORTANT: Do NOT repeat the same question you already asked earlier in the conversation
- If you asked a question and the user asked something else instead of answering, just answer their question - they will get back to your question when ready
- Good follow-up examples:
  * "What age group would this be for?"
  * "Would you like me to tell you more about our options?"
  * "Is there a particular day or time that works best for you?"
  * "What questions do you have about getting started?"
  * "Let me know if you have any other questions!" (when you already have a pending question)
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
- ALWAYS introduce yourself as the automated assistant for the business (use the business name from your system prompt)
- NEVER say "I saw your email" or reference emails directly - instead say something like "I saw that you're interested in our services"
- Do NOT use the person's name. Just say "Hi!" — never guess or assume a name.
- Include a simple question or invitation to continue the conversation
- Match the business's friendly, professional tone
- End with an open question to encourage response

EXAMPLES OF GOOD MESSAGES (adapt the business name to match your system prompt):
- "Hi! I'm the automated assistant for [Business Name]. I saw you're interested in our services. How can I help?"
- "Hi there! This is the [Business Name] chatbot. Noticed you're interested - any questions I can answer?"
- "Hi! I'm the chatbot for [Business Name]. What can I help you with today?"

Generate ONLY the SMS message text, nothing else. No quotes, no explanation, just the message."""

        return base_prompt + followup_instructions

    async def compose_prompt_v2(
        self,
        tenant_id: int,
        channel: str = "chat",
        context: dict | None = None,
    ) -> str | None:
        """Compose prompt using the new JSON-based architecture (v2).

        This method uses the new tenant_prompt_configs table which stores
        JSON configurations that are combined with hardcoded base rules.

        Args:
            tenant_id: Tenant ID (required for v2)
            channel: Channel type ("chat", "voice", "sms")
            context: Runtime context (collected contact info, turn count, etc.)

        Returns:
            Assembled system prompt string, or None if no v2 config exists
        """
        # Get tenant's JSON config from database
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)

        if not config_record:
            logger.debug(f"No v2 prompt config found for tenant {tenant_id}")
            return None

        try:
            # Validate JSON against schema
            tenant_config = BSSTenantConfig.model_validate(config_record.config_json)
        except ValidationError as e:
            logger.error(f"Invalid tenant config for tenant {tenant_id}: {e}")
            return None

        # Assemble the prompt
        business_type = config_record.business_type or "bss"
        assembler = PromptAssembler(business_type=business_type)

        prompt = assembler.assemble(
            tenant_config=tenant_config,
            channel=channel,
            context=context,
        )

        return prompt

    async def compose_prompt_v2_chat(
        self,
        tenant_id: int,
        context: dict | None = None,
    ) -> str | None:
        """Compose chat-specific prompt using v2 architecture.

        Priority:
        1. Check for direct 'web_prompt' field in config_json (new unified system)
        2. Fall back to assembled prompt from base config + tenant sections

        Args:
            tenant_id: Tenant ID
            context: Runtime context

        Returns:
            Assembled chat prompt, or None if no v2 config exists
        """
        # Try new unified prompt system first
        direct_prompt = await self._get_channel_prompt(tenant_id, "web_prompt")
        if direct_prompt:
            logger.info(f"[PROMPT] Using direct web_prompt for tenant {tenant_id}")
            critical_rules = await self._get_critical_base_rules_for_tenant(tenant_id)
            # Add contact collection context and chat instructions
            contact_context = self._build_chat_contact_context(context)
            chat_instructions = self._chat_instructions()
            return critical_rules + direct_prompt + contact_context + chat_instructions

        # Fall back to assembled prompt
        base_prompt = await self.compose_prompt_v2(tenant_id, channel="chat", context=context)
        if base_prompt is None:
            return None
        return await self.compose_prompt_chat_from_base(base_prompt, context)

    async def compose_prompt_v2_voice(
        self,
        tenant_id: int,
        context: dict | None = None,
    ) -> str | None:
        """Compose voice-specific prompt using v2 architecture.

        Priority:
        1. Check for direct 'voice_prompt' field in config_json (new unified system)
        2. Fall back to assembled prompt from base config + tenant sections

        Args:
            tenant_id: Tenant ID
            context: Runtime context

        Returns:
            Assembled voice prompt, or None if no v2 config exists
        """
        # Try new unified prompt system first
        direct_prompt = await self._get_channel_prompt(tenant_id, "voice_prompt")
        if direct_prompt:
            logger.info(f"[PROMPT] Using direct voice_prompt for tenant {tenant_id}")
            critical_rules = await self._get_critical_base_rules_for_tenant(tenant_id)
            return critical_rules + direct_prompt

        # Fall back to assembled prompt
        return await self.compose_prompt_v2(tenant_id, channel="voice", context=context)

    async def compose_prompt_v2_sms(
        self,
        tenant_id: int,
        context: dict | None = None,
    ) -> str | None:
        """Compose SMS-specific prompt using v2 architecture.

        Priority:
        1. Check for direct 'sms_prompt' field in config_json (new unified system)
        2. Fall back to assembled prompt from base config + tenant sections

        Args:
            tenant_id: Tenant ID
            context: Runtime context

        Returns:
            Assembled SMS prompt, or None if no v2 config exists
        """
        # Try new unified prompt system first
        direct_prompt = await self._get_channel_prompt(tenant_id, "sms_prompt")
        if direct_prompt:
            logger.info(f"[PROMPT] Using direct sms_prompt for tenant {tenant_id}")
            critical_rules = await self._get_critical_base_rules_for_tenant(tenant_id)
            return critical_rules + direct_prompt

        # Fall back to assembled prompt
        return await self.compose_prompt_v2(tenant_id, channel="sms", context=context)

    async def _get_channel_prompt(self, tenant_id: int, prompt_key: str) -> str | None:
        """Get a direct channel prompt from config_json.

        Args:
            tenant_id: Tenant ID
            prompt_key: Key in config_json (web_prompt, voice_prompt, sms_prompt)

        Returns:
            Prompt string if found, None otherwise
        """
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        if not config_record or not config_record.config_json:
            return None

        prompt = config_record.config_json.get(prompt_key)
        if prompt and isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
        return None

    def _get_critical_base_rules(self) -> str:
        """Get critical BSS base rules.

        These rules are prepended to direct channel prompts for BSS tenants to ensure
        critical guardrails are always in place, even when using custom prompts.

        Returns:
            String containing critical base rules (swimmer identification, pronouns,
            location guardrails, equipment knowledge)
        """
        return f"""
{SWIMMER_IDENTIFICATION_RULES}

{PRONOUN_USAGE_RULES}

{BSS_LOCATION_LINK_GUARDRAILS}

{BSS_EQUIPMENT_KNOWLEDGE}
"""

    async def _get_critical_base_rules_for_tenant(self, tenant_id: int) -> str:
        """Get critical base rules for swim school tenants.

        Returns swimmer identification rules, pronoun usage, location guardrails,
        and equipment knowledge for BSS and swim school tenants.
        """
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        business_type = config_record.business_type if config_record else "bss"
        # Apply swim school rules to BSS tenants and tenant 1 (swim school)
        if business_type == "bss" or tenant_id == 1:
            return self._get_critical_base_rules()
        return ""

    async def get_channel_prompt(self, tenant_id: int, channel: str) -> str | None:
        """Get direct channel prompt for editing.

        Args:
            tenant_id: Tenant ID
            channel: Channel name (web, voice, sms)

        Returns:
            Prompt string if found, None otherwise
        """
        prompt_key_map = {
            "web": "web_prompt",
            "chat": "web_prompt",
            "voice": "voice_prompt",
            "voice_es": "voice_es_prompt",
            "sms": "sms_prompt",
        }
        prompt_key = prompt_key_map.get(channel)
        if not prompt_key:
            return None
        return await self._get_channel_prompt(tenant_id, prompt_key)

    async def set_channel_prompt(self, tenant_id: int, channel: str, prompt: str) -> bool:
        """Set direct channel prompt.

        Args:
            tenant_id: Tenant ID
            channel: Channel name (web, voice, sms)
            prompt: The complete prompt text

        Returns:
            True if successful, False otherwise
        """
        prompt_key_map = {
            "web": "web_prompt",
            "chat": "web_prompt",
            "voice": "voice_prompt",
            "voice_es": "voice_es_prompt",
            "sms": "sms_prompt",
        }
        prompt_key = prompt_key_map.get(channel)
        if not prompt_key:
            return False

        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        if not config_record:
            # Create new config record
            from app.persistence.models.tenant_prompt_config import TenantPromptConfig
            config_record = TenantPromptConfig(
                tenant_id=tenant_id,
                schema_version="v2",
                config_json={prompt_key: prompt},
                is_active=True,
            )
            self.session.add(config_record)
        else:
            # Update existing config
            if config_record.config_json is None:
                config_record.config_json = {}
            config_record.config_json[prompt_key] = prompt
            # Mark the JSON column as modified so SQLAlchemy detects the change
            attributes.flag_modified(config_record, "config_json")

        await self.session.commit()

        # Invalidate cache for this tenant
        PromptCache.invalidate(tenant_id)

        return True

    async def get_all_channel_prompts(self, tenant_id: int) -> dict[str, str | None]:
        """Get all channel prompts for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dict with keys: web_prompt, voice_prompt, voice_es_prompt, sms_prompt
        """
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        if not config_record or not config_record.config_json:
            return {"web_prompt": None, "voice_prompt": None, "voice_es_prompt": None, "sms_prompt": None}

        return {
            "web_prompt": config_record.config_json.get("web_prompt"),
            "voice_prompt": config_record.config_json.get("voice_prompt"),
            "voice_es_prompt": config_record.config_json.get("voice_es_prompt"),
            "sms_prompt": config_record.config_json.get("sms_prompt"),
        }

    async def get_prompt_v2_config(self, tenant_id: int) -> dict | None:
        """Get the raw v2 config JSON for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Config JSON dict, or None if not found
        """
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        if not config_record:
            return None
        return config_record.config_json

    async def has_v2_config(self, tenant_id: int) -> bool:
        """Check if tenant has a v2 prompt config.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if tenant has a v2 config
        """
        config_record = await self.prompt_config_repo.get_by_tenant_id(tenant_id)
        return config_record is not None
