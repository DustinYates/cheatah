"""Voice service for processing voice calls and generating summaries."""

import json
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.domain.services.conversation_service import ConversationService
from app.domain.services.lead_service import LeadService
from app.domain.services.prompt_service import PromptService
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.call_repository import CallRepository
from app.persistence.repositories.call_summary_repository import CallSummaryRepository
from app.persistence.repositories.contact_repository import ContactRepository

logger = logging.getLogger(__name__)


# Intent categories
class VoiceIntent:
    """Voice call intent categories."""
    PRICING_INFO = "pricing_info"
    HOURS_LOCATION = "hours_location"
    BOOKING_REQUEST = "booking_request"
    SUPPORT_REQUEST = "support_request"
    WRONG_NUMBER = "wrong_number"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


# Call outcomes
class CallOutcome:
    """Call outcome categories."""
    LEAD_CREATED = "lead_created"
    INFO_PROVIDED = "info_provided"
    BOOKING_REQUESTED = "booking_requested"
    VOICEMAIL = "voicemail"
    TRANSFERRED = "transferred"
    DISMISSED = "dismissed"
    INCOMPLETE = "incomplete"


@dataclass
class VoiceResult:
    """Result of processing a voice turn."""
    response_text: str
    intent: str | None = None
    requires_escalation: bool = False
    extracted_data: dict | None = None


@dataclass
class ExtractedCallData:
    """Extracted structured data from a call."""
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    reason: str | None = None
    urgency: str | None = None  # high, medium, low
    preferred_callback_time: str | None = None


class VoiceService:
    """Service for processing voice calls."""

    # Voice-specific guardrails
    MAX_RESPONSE_SENTENCES = 3  # Keep responses short for voice
    MAX_RESPONSE_CHARS = 300  # Approximate max characters
    
    # Blocked content patterns
    BLOCKED_PATTERNS = [
        r"payment|credit card|card number|cvv|expir",
        r"legal advice|lawyer|attorney|sue|lawsuit",
        r"medical advice|prescription|diagnos",
        r"guarantee|promise|definitely will|100%",
    ]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize voice service."""
        self.session = session
        self.conversation_service = ConversationService(session)
        self.lead_service = LeadService(session)
        self.prompt_service = PromptService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.call_repo = CallRepository(session)
        self.call_summary_repo = CallSummaryRepository(session)
        self.contact_repo = ContactRepository(session)

    async def process_voice_turn(
        self,
        tenant_id: int | None,
        call_sid: str,
        conversation_id: int | None,
        transcribed_text: str,
    ) -> VoiceResult:
        """Process a single voice turn.
        
        Args:
            tenant_id: Tenant ID
            call_sid: Twilio call SID
            conversation_id: Conversation ID
            transcribed_text: Transcribed speech from caller
            
        Returns:
            VoiceResult with response and metadata
        """
        if not tenant_id or not conversation_id:
            return VoiceResult(
                response_text="I'm sorry, I'm having trouble processing your request. Please try calling back.",
                intent=VoiceIntent.UNKNOWN,
            )
        
        try:
            # Get conversation history
            messages = await self._get_conversation_messages(conversation_id)
            
            # Detect intent from current message
            intent = await self._detect_intent(transcribed_text)
            
            # Check for escalation triggers
            if self._should_escalate(transcribed_text, intent):
                return VoiceResult(
                    response_text="I understand you'd like to speak with someone on our team. Let me connect you with a team member who can help.",
                    intent=intent,
                    requires_escalation=True,
                )
            
            # Generate response using LLM
            response_text = await self._generate_voice_response(
                tenant_id=tenant_id,
                messages=messages,
                current_message=transcribed_text,
                intent=intent,
            )
            
            # Apply guardrails
            response_text = self._apply_response_guardrails(response_text)
            
            return VoiceResult(
                response_text=response_text,
                intent=intent,
            )
            
        except Exception as e:
            logger.error(f"Error processing voice turn: {e}", exc_info=True)
            return VoiceResult(
                response_text="I apologize, but I'm having some difficulty right now. Could you please repeat that?",
                intent=VoiceIntent.UNKNOWN,
            )

    async def _detect_intent(self, text: str) -> str:
        """Detect intent from transcribed text.
        
        Args:
            text: Transcribed speech
            
        Returns:
            Intent category string
        """
        lower_text = text.lower()
        
        # Pattern-based intent detection (fast path)
        if any(word in lower_text for word in ["price", "cost", "how much", "rate", "fee", "pricing"]):
            return VoiceIntent.PRICING_INFO
        
        if any(word in lower_text for word in ["hours", "open", "close", "location", "address", "where"]):
            return VoiceIntent.HOURS_LOCATION
        
        if any(word in lower_text for word in ["book", "schedule", "appointment", "reserve", "sign up"]):
            return VoiceIntent.BOOKING_REQUEST
        
        if any(word in lower_text for word in ["help", "problem", "issue", "not working", "broken", "complaint"]):
            return VoiceIntent.SUPPORT_REQUEST
        
        if any(word in lower_text for word in ["wrong number", "wrong person", "not", "who is this"]):
            return VoiceIntent.WRONG_NUMBER
        
        return VoiceIntent.GENERAL_INQUIRY

    def _should_escalate(self, text: str, intent: str) -> bool:
        """Check if call should be escalated to human.
        
        Args:
            text: Transcribed speech
            intent: Detected intent
            
        Returns:
            True if escalation needed
        """
        lower_text = text.lower()
        
        # Explicit escalation requests
        escalation_phrases = [
            "speak to a human",
            "talk to someone",
            "real person",
            "manager",
            "supervisor",
            "human please",
            "not a robot",
            "speak with someone",
        ]
        
        return any(phrase in lower_text for phrase in escalation_phrases)

    async def _generate_voice_response(
        self,
        tenant_id: int,
        messages: list[Message],
        current_message: str,
        intent: str,
    ) -> str:
        """Generate AI response for voice conversation.
        
        Args:
            tenant_id: Tenant ID
            messages: Previous conversation messages
            current_message: Current transcribed speech
            intent: Detected intent
            
        Returns:
            Response text optimized for voice
        """
        # Get voice-specific prompt
        system_prompt = await self.prompt_service.compose_prompt_voice(tenant_id)
        
        if not system_prompt:
            return "Thank you for calling. How may I help you today?"
        
        # Build conversation context
        conversation_context = self._build_voice_context(
            system_prompt=system_prompt,
            messages=messages,
            current_message=current_message,
            intent=intent,
        )
        
        # Generate response
        try:
            llm_start = time.time()
            response = await self.llm_orchestrator.generate(
                conversation_context,
                context={"temperature": 0.4, "max_tokens": 150},  # Short responses
            )
            llm_latency = (time.time() - llm_start) * 1000
            logger.info(f"Voice LLM latency: {llm_latency:.1f}ms")
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"LLM generation failed for voice: {e}", exc_info=True)
            return "I apologize, but I'm having trouble right now. Could you please repeat that?"

    def _build_voice_context(
        self,
        system_prompt: str,
        messages: list[Message],
        current_message: str,
        intent: str,
    ) -> str:
        """Build context for voice LLM generation.
        
        Args:
            system_prompt: Voice-specific system prompt
            messages: Previous messages
            current_message: Current transcribed speech
            intent: Detected intent
            
        Returns:
            Full prompt for LLM
        """
        # Build conversation history (last 5 turns for voice)
        history = []
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        for msg in recent_messages:
            role = "Caller" if msg.role == "user" else "You"
            history.append(f"{role}: {msg.content}")
        
        history.append(f"Caller: {current_message}")
        
        prompt_parts = [
            system_prompt,
            f"\n\nDetected Intent: {intent}",
            "\n\nConversation:",
            "\n".join(history),
            "\n\nYou (respond in 1-2 short sentences, end with a question if appropriate):",
        ]
        
        return "\n".join(prompt_parts)

    def _apply_response_guardrails(self, response: str) -> str:
        """Apply guardrails to voice response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Sanitized response
        """
        # Remove any markdown
        response = re.sub(r'\*+', '', response)
        response = re.sub(r'`+', '', response)
        response = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', response)  # Links
        
        # Check for blocked content
        lower_response = response.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, lower_response):
                logger.warning(f"Blocked content detected in response: {pattern}")
                return "I'd be happy to help with that. Could you tell me a bit more about what you're looking for?"
        
        # Truncate if too long
        if len(response) > self.MAX_RESPONSE_CHARS:
            # Find a good breaking point
            sentences = response.split('. ')
            truncated = []
            char_count = 0
            for sentence in sentences[:self.MAX_RESPONSE_SENTENCES]:
                if char_count + len(sentence) < self.MAX_RESPONSE_CHARS:
                    truncated.append(sentence)
                    char_count += len(sentence) + 2
            response = '. '.join(truncated)
            if not response.endswith('.') and not response.endswith('?'):
                response += '.'
        
        return response

    async def _get_conversation_messages(self, conversation_id: int) -> list[Message]:
        """Get messages for a conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            List of messages ordered by sequence number
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def generate_call_summary(self, call_id: int) -> CallSummary | None:
        """Generate and store a summary for a completed call.
        
        Args:
            call_id: Call ID
            
        Returns:
            Created CallSummary or None if failed
        """
        try:
            # Get call details
            call = await self._get_call_with_conversation(call_id)
            if not call:
                logger.warning(f"Call not found for summary generation: {call_id}")
                return None
            
            # Get conversation if exists
            conversation = await self._get_conversation_for_call(call.call_sid)
            if not conversation:
                logger.info(f"No conversation found for call: {call.call_sid}")
                # Create a basic summary for calls without conversation
                return await self.call_summary_repo.create_summary(
                    call_id=call_id,
                    intent=VoiceIntent.UNKNOWN,
                    outcome=CallOutcome.VOICEMAIL,
                    summary_text="Call ended without AI conversation.",
                )
            
            # Get conversation messages
            messages = await self._get_conversation_messages(conversation.id)
            if not messages:
                return await self.call_summary_repo.create_summary(
                    call_id=call_id,
                    intent=VoiceIntent.UNKNOWN,
                    outcome=CallOutcome.INCOMPLETE,
                    summary_text="No messages recorded in conversation.",
                )
            
            # Analyze conversation
            conversation_text = "\n".join([
                f"{'Caller' if m.role == 'user' else 'Assistant'}: {m.content}"
                for m in messages
            ])
            
            # Detect primary intent from conversation
            all_user_text = " ".join([m.content for m in messages if m.role == "user"])
            primary_intent = await self._detect_intent(all_user_text)
            
            # Extract structured data
            extracted_data = await self._extract_call_data(messages, call.from_number)
            
            # Generate summary using LLM
            summary_text = await self._generate_summary_text(
                conversation_text=conversation_text,
                intent=primary_intent,
                extracted_data=extracted_data,
            )
            
            # Determine outcome
            outcome = await self._determine_outcome(
                messages=messages,
                intent=primary_intent,
                extracted_data=extracted_data,
            )
            
            # Create or update lead/contact
            contact_id, lead_id = await self._create_or_update_lead_contact(
                tenant_id=call.tenant_id,
                phone=call.from_number,
                extracted_data=extracted_data,
                conversation_id=conversation.id,
            )
            
            # Create summary
            summary = await self.call_summary_repo.create_summary(
                call_id=call_id,
                contact_id=contact_id,
                lead_id=lead_id,
                intent=primary_intent,
                outcome=outcome,
                summary_text=summary_text,
                extracted_fields=extracted_data.__dict__ if extracted_data else None,
            )
            
            logger.info(f"Created call summary: call_id={call_id}, intent={primary_intent}, outcome={outcome}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate call summary: {e}", exc_info=True)
            return None

    async def _get_call_with_conversation(self, call_id: int) -> Call | None:
        """Get call by ID.
        
        Args:
            call_id: Call ID
            
        Returns:
            Call or None
        """
        stmt = select(Call).where(Call.id == call_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_conversation_for_call(self, call_sid: str) -> Conversation | None:
        """Get conversation associated with a call.
        
        Args:
            call_sid: Twilio call SID
            
        Returns:
            Conversation or None
        """
        stmt = select(Conversation).where(Conversation.external_id == call_sid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _extract_call_data(
        self,
        messages: list[Message],
        caller_phone: str,
    ) -> ExtractedCallData:
        """Extract structured data from call conversation.
        
        Args:
            messages: Conversation messages
            caller_phone: Caller's phone number (from caller ID)
            
        Returns:
            ExtractedCallData with extracted fields
        """
        # Combine user messages for extraction
        user_text = " ".join([m.content for m in messages if m.role == "user"])
        
        # Start with caller ID phone
        data = ExtractedCallData(phone=caller_phone)
        
        # Extract email with regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_matches = re.findall(email_pattern, user_text, re.IGNORECASE)
        if email_matches:
            data.email = email_matches[0].lower()
        
        # Extract name patterns
        name_patterns = [
            r"(?:I'?m|I am|my name is|this is|im|name's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, user_text, re.IGNORECASE)
            if matches:
                data.name = matches[0].strip().title()
                break
        
        # Try LLM extraction for more complex data
        try:
            extraction_prompt = f"""Analyze this phone call transcript and extract information:

Transcript:
{user_text}

Extract:
1. reason: Why is the caller calling? (one sentence)
2. urgency: Is this urgent? (high/medium/low)
3. preferred_callback_time: Did they mention a preferred time to call back?

Respond with ONLY JSON:
{{"reason": null, "urgency": "medium", "preferred_callback_time": null}}"""

            response = await self.llm_orchestrator.generate(
                extraction_prompt,
                context={"temperature": 0.0, "max_tokens": 150},
            )
            
            # Parse JSON
            response = response.strip()
            if response.startswith("{"):
                json_end = response.rfind("}") + 1
                response = response[:json_end]
                extracted = json.loads(response)
                
                if extracted.get("reason") and extracted["reason"] != "null":
                    data.reason = extracted["reason"]
                if extracted.get("urgency") and extracted["urgency"] != "null":
                    data.urgency = extracted["urgency"]
                if extracted.get("preferred_callback_time") and extracted["preferred_callback_time"] != "null":
                    data.preferred_callback_time = extracted["preferred_callback_time"]
                    
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
        
        return data

    async def _generate_summary_text(
        self,
        conversation_text: str,
        intent: str,
        extracted_data: ExtractedCallData,
    ) -> str:
        """Generate a concise summary of the call.
        
        Args:
            conversation_text: Full conversation text
            intent: Detected intent
            extracted_data: Extracted structured data
            
        Returns:
            Summary text
        """
        try:
            summary_prompt = f"""Summarize this phone call in 2-3 sentences. Focus on:
- What the caller wanted
- What information was provided
- Any next steps or follow-up needed

Intent: {intent}
Caller reason: {extracted_data.reason or 'Not specified'}

Conversation:
{conversation_text[:2000]}

Write a professional summary (2-3 sentences):"""

            summary = await self.llm_orchestrator.generate(
                summary_prompt,
                context={"temperature": 0.3, "max_tokens": 150},
            )
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return f"Call regarding {intent.replace('_', ' ')}. {extracted_data.reason or 'Details not captured.'}"

    async def _determine_outcome(
        self,
        messages: list[Message],
        intent: str,
        extracted_data: ExtractedCallData,
    ) -> str:
        """Determine the outcome of the call.
        
        Args:
            messages: Conversation messages
            intent: Detected intent
            extracted_data: Extracted data
            
        Returns:
            Outcome category
        """
        if intent == VoiceIntent.BOOKING_REQUEST:
            return CallOutcome.BOOKING_REQUESTED
        
        if intent == VoiceIntent.WRONG_NUMBER:
            return CallOutcome.DISMISSED
        
        # Check if we captured lead info
        if extracted_data.name or extracted_data.email:
            return CallOutcome.LEAD_CREATED
        
        # Check message count for engagement
        user_messages = [m for m in messages if m.role == "user"]
        if len(user_messages) >= 2:
            return CallOutcome.INFO_PROVIDED
        
        return CallOutcome.INCOMPLETE

    async def _create_or_update_lead_contact(
        self,
        tenant_id: int,
        phone: str,
        extracted_data: ExtractedCallData,
        conversation_id: int,
    ) -> tuple[int | None, int | None]:
        """Create or update lead and contact from call data.
        
        Args:
            tenant_id: Tenant ID
            phone: Caller phone number
            extracted_data: Extracted call data
            conversation_id: Conversation ID
            
        Returns:
            Tuple of (contact_id, lead_id)
        """
        contact_id = None
        lead_id = None
        
        try:
            # Check for existing contact by phone
            existing_contact = await self.contact_repo.get_by_email_or_phone(
                tenant_id,
                email=extracted_data.email,
                phone=phone,
            )
            
            if existing_contact:
                contact_id = existing_contact.id
                # Update contact name if we have new info
                if extracted_data.name and not existing_contact.name:
                    existing_contact.name = extracted_data.name
                    await self.session.commit()
            
            # Create or update lead
            existing_lead = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation_id
            )
            
            if existing_lead:
                lead_id = existing_lead.id
            elif extracted_data.name or extracted_data.email or phone:
                # Create new lead
                lead = await self.lead_service.capture_lead(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    email=extracted_data.email,
                    phone=phone,
                    name=extracted_data.name,
                    metadata={
                        "source": "voice_call",
                        "reason": extracted_data.reason,
                        "urgency": extracted_data.urgency,
                        "preferred_callback_time": extracted_data.preferred_callback_time,
                    },
                )
                lead_id = lead.id
                logger.info(f"Created lead from voice call: lead_id={lead_id}")
                
        except Exception as e:
            logger.error(f"Failed to create/update lead/contact: {e}", exc_info=True)
        
        return contact_id, lead_id

