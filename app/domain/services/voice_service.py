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
from app.domain.services.voice_config_service import VoiceConfigService
from app.infrastructure.notifications import NotificationService
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
class VoiceLatencyMetrics:
    """Latency tracking metrics for voice processing."""
    total_ms: float = 0.0
    intent_detection_ms: float = 0.0
    prompt_composition_ms: float = 0.0
    llm_first_token_ms: float | None = None  # Time to first token (streaming only)
    llm_full_ms: float = 0.0  # Time to complete LLM response
    post_processing_ms: float = 0.0
    
    def log_summary(self, call_sid: str) -> None:
        """Log a summary of latency metrics."""
        ttft_str = f"{self.llm_first_token_ms:.1f}ms" if self.llm_first_token_ms else "n/a"
        logger.info(
            f"Voice latency metrics for {call_sid}: "
            f"total={self.total_ms:.1f}ms, "
            f"intent={self.intent_detection_ms:.1f}ms, "
            f"prompt={self.prompt_composition_ms:.1f}ms, "
            f"llm_first_token={ttft_str}, "
            f"llm_full={self.llm_full_ms:.1f}ms, "
            f"post_proc={self.post_processing_ms:.1f}ms"
        )


@dataclass
class VoiceResult:
    """Result of processing a voice turn."""
    response_text: str
    intent: str | None = None
    requires_escalation: bool = False
    extracted_data: dict | None = None
    latency_metrics: VoiceLatencyMetrics | None = None


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

    # Voice-specific guardrails - optimized for natural, concise responses
    # Shorter responses = faster TTS = lower latency
    MAX_RESPONSE_SENTENCES = 3  # Concise, focused responses
    MAX_RESPONSE_CHARS = 350  # Short enough for fast TTS, long enough to be helpful
    
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
        self.voice_config_service = VoiceConfigService(session)
        self.notification_service = NotificationService(session)
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
            VoiceResult with response and metadata including latency metrics
        """
        total_start = time.time()
        metrics = VoiceLatencyMetrics()
        
        if not tenant_id or not conversation_id:
            logger.warning(f"Missing tenant_id or conversation_id: tenant_id={tenant_id}, conversation_id={conversation_id}")
            return VoiceResult(
                response_text="I'm sorry, I'm having trouble processing your request. Please try calling back.",
                intent=VoiceIntent.UNKNOWN,
            )
        
        try:
            # Get conversation history
            messages = await self._get_conversation_messages(conversation_id)
            
            # Detect intent from current message (with timing)
            intent_start = time.time()
            intent = await self._detect_intent(transcribed_text)
            metrics.intent_detection_ms = (time.time() - intent_start) * 1000
            
            # Check for escalation triggers
            if self._should_escalate(transcribed_text, intent):
                metrics.total_ms = (time.time() - total_start) * 1000
                logger.info(
                    f"Voice escalation for {call_sid}: "
                    f"total={metrics.total_ms:.1f}ms, intent={metrics.intent_detection_ms:.1f}ms"
                )
                return VoiceResult(
                    response_text="I understand you'd like to speak with someone on our team. Let me connect you with a team member who can help.",
                    intent=intent,
                    requires_escalation=True,
                    latency_metrics=metrics,
                )
            
            # Generate response using LLM (timing tracked inside _generate_voice_response)
            llm_start = time.time()
            response_text = await self._generate_voice_response(
                tenant_id=tenant_id,
                messages=messages,
                current_message=transcribed_text,
                intent=intent,
            )
            metrics.llm_full_ms = (time.time() - llm_start) * 1000
            
            # Apply guardrails (with timing)
            post_start = time.time()
            response_text = self._apply_response_guardrails(response_text)
            metrics.post_processing_ms = (time.time() - post_start) * 1000
            
            # Calculate total
            metrics.total_ms = (time.time() - total_start) * 1000
            
            # Log comprehensive latency metrics
            logger.info(
                f"Voice turn latency for {call_sid}: "
                f"total={metrics.total_ms:.1f}ms, "
                f"intent={metrics.intent_detection_ms:.1f}ms, "
                f"llm={metrics.llm_full_ms:.1f}ms, "
                f"post_proc={metrics.post_processing_ms:.1f}ms"
            )
            
            return VoiceResult(
                response_text=response_text,
                intent=intent,
                latency_metrics=metrics,
            )
            
        except Exception as e:
            logger.error(f"Error processing voice turn: {e}", exc_info=True)
            return VoiceResult(
                response_text="I apologize, but I'm having some difficulty right now. Could you please repeat that?",
                intent=VoiceIntent.UNKNOWN,
            )

    async def process_voice_turn_streaming(
        self,
        tenant_id: int | None,
        call_sid: str,
        conversation_id: int | None,
        transcribed_text: str,
    ):
        """Process a voice turn with streaming LLM response.
        
        This method uses streaming to reduce perceived latency by yielding
        response chunks as soon as they form complete clauses. This allows
        TTS to start speaking before the full response is generated.
        
        Args:
            tenant_id: Tenant ID
            call_sid: Twilio call SID
            conversation_id: Conversation ID
            transcribed_text: Transcribed speech from caller
            
        Yields:
            StreamingVoiceChunk with text chunk, intent, and completion status
        """
        from dataclasses import dataclass
        
        @dataclass
        class StreamingVoiceChunk:
            """A chunk of streaming voice response."""
            text: str
            intent: str | None = None
            is_first_chunk: bool = False
            is_final_chunk: bool = False
            requires_escalation: bool = False
        
        if not tenant_id or not conversation_id:
            logger.warning(f"Missing tenant_id or conversation_id: tenant_id={tenant_id}, conversation_id={conversation_id}")
            yield StreamingVoiceChunk(
                text="I'm sorry, I'm having trouble processing your request. Please try calling back.",
                intent=VoiceIntent.UNKNOWN,
                is_first_chunk=True,
                is_final_chunk=True,
            )
            return
        
        try:
            # Get conversation history
            messages = await self._get_conversation_messages(conversation_id)
            
            # Detect intent from current message
            intent = await self._detect_intent(transcribed_text)
            
            # Check for escalation triggers
            if self._should_escalate(transcribed_text, intent):
                yield StreamingVoiceChunk(
                    text="I understand you'd like to speak with someone on our team. Let me connect you with a team member who can help.",
                    intent=intent,
                    is_first_chunk=True,
                    is_final_chunk=True,
                    requires_escalation=True,
                )
                return
            
            # Get voice-specific prompt
            system_prompt = await self.prompt_service.compose_prompt_voice(tenant_id)
            
            if not system_prompt:
                yield StreamingVoiceChunk(
                    text="Thank you for calling. How may I help you today?",
                    intent=intent,
                    is_first_chunk=True,
                    is_final_chunk=True,
                )
                return
            
            # Build conversation context
            conversation_context = self._build_voice_context(
                system_prompt=system_prompt,
                messages=messages,
                current_message=transcribed_text,
                intent=intent,
            )
            
            # Stream response and chunk into speakable segments
            llm_start = time.time()
            buffer = ""
            is_first = True
            chunk_count = 0
            
            # Sentence-ending patterns for chunking
            sentence_enders = ('.', '!', '?', '—')
            clause_enders = (',', ';', ':', '—')
            
            async for token in self.llm_orchestrator.generate_stream(
                conversation_context,
                context={"temperature": 0.7, "max_tokens": 350},
            ):
                buffer += token
                
                # Check if we have a complete chunk to yield
                # First chunk: yield after first sentence or clause (for fast start)
                # Subsequent chunks: yield after sentences for natural flow
                
                should_yield = False
                yield_text = ""
                
                if is_first:
                    # For first chunk, yield after first sentence OR if we have enough for a clause
                    for ender in sentence_enders:
                        if ender in buffer:
                            idx = buffer.rfind(ender)
                            yield_text = buffer[:idx + 1].strip()
                            buffer = buffer[idx + 1:].lstrip()
                            should_yield = True
                            break
                    
                    # If no sentence ender but we have a clause and enough text, yield it
                    if not should_yield and len(buffer) > 50:
                        for ender in clause_enders:
                            if ender in buffer:
                                idx = buffer.rfind(ender)
                                yield_text = buffer[:idx + 1].strip()
                                buffer = buffer[idx + 1:].lstrip()
                                should_yield = True
                                break
                else:
                    # For subsequent chunks, prefer complete sentences
                    for ender in sentence_enders:
                        if ender in buffer:
                            idx = buffer.rfind(ender)
                            yield_text = buffer[:idx + 1].strip()
                            buffer = buffer[idx + 1:].lstrip()
                            should_yield = True
                            break
                
                if should_yield and yield_text:
                    # Apply post-processing to the chunk
                    processed_text = self._post_process_for_speech(yield_text)
                    chunk_count += 1
                    
                    yield StreamingVoiceChunk(
                        text=processed_text,
                        intent=intent,
                        is_first_chunk=is_first,
                        is_final_chunk=False,
                    )
                    is_first = False
            
            # Yield any remaining buffer as final chunk
            if buffer.strip():
                processed_text = self._post_process_for_speech(buffer.strip())
                processed_text = self._apply_response_guardrails(processed_text)
                
                yield StreamingVoiceChunk(
                    text=processed_text,
                    intent=intent,
                    is_first_chunk=is_first,
                    is_final_chunk=True,
                )
            elif chunk_count > 0:
                # Mark last yielded chunk as final
                pass  # Already yielded, caller should handle
            else:
                # No chunks yielded, yield error message
                yield StreamingVoiceChunk(
                    text="I apologize, but I couldn't generate a response. Could you please repeat that?",
                    intent=intent,
                    is_first_chunk=True,
                    is_final_chunk=True,
                )
            
            llm_latency = (time.time() - llm_start) * 1000
            logger.info(f"Voice streaming LLM latency: {llm_latency:.1f}ms, chunks: {chunk_count}")
            
        except Exception as e:
            logger.error(f"Error processing streaming voice turn: {e}", exc_info=True)
            yield StreamingVoiceChunk(
                text="I apologize, but I'm having some difficulty right now. Could you please repeat that?",
                intent=VoiceIntent.UNKNOWN,
                is_first_chunk=True,
                is_final_chunk=True,
            )

    async def _detect_intent(self, text: str) -> str:
        """Detect intent from transcribed text.
        
        Uses pattern-based detection for clear cases, with LLM fallback
        for ambiguous messages to improve accuracy.
        
        Args:
            text: Transcribed speech
            
        Returns:
            Intent category string
        """
        lower_text = text.lower()
        
        # Pattern-based intent detection (fast path for clear intents)
        pattern_scores = {
            VoiceIntent.PRICING_INFO: 0,
            VoiceIntent.HOURS_LOCATION: 0,
            VoiceIntent.BOOKING_REQUEST: 0,
            VoiceIntent.SUPPORT_REQUEST: 0,
            VoiceIntent.WRONG_NUMBER: 0,
        }
        
        # Score each intent based on keyword matches
        pricing_words = ["price", "cost", "how much", "rate", "fee", "pricing", "charge", "pay", "expensive", "afford"]
        hours_words = ["hours", "open", "close", "location", "address", "where", "directions", "time", "when"]
        booking_words = ["book", "schedule", "appointment", "reserve", "sign up", "register", "enroll", "start", "begin", "join"]
        support_words = ["help", "problem", "issue", "not working", "broken", "complaint", "fix", "wrong", "error", "trouble"]
        wrong_number_words = ["wrong number", "wrong person", "who is this", "who are you", "didn't call"]
        
        for word in pricing_words:
            if word in lower_text:
                pattern_scores[VoiceIntent.PRICING_INFO] += 1
                
        for word in hours_words:
            if word in lower_text:
                pattern_scores[VoiceIntent.HOURS_LOCATION] += 1
                
        for word in booking_words:
            if word in lower_text:
                pattern_scores[VoiceIntent.BOOKING_REQUEST] += 1
                
        for word in support_words:
            if word in lower_text:
                pattern_scores[VoiceIntent.SUPPORT_REQUEST] += 1
                
        for phrase in wrong_number_words:
            if phrase in lower_text:
                pattern_scores[VoiceIntent.WRONG_NUMBER] += 2  # Higher weight for wrong number
        
        # Find highest scoring intent
        max_score = max(pattern_scores.values())
        
        # If we have a clear winner (score >= 2), use it
        if max_score >= 2:
            for intent, score in pattern_scores.items():
                if score == max_score:
                    return intent
        
        # If score is 1 or ambiguous (multiple intents tied), use LLM for better detection
        if max_score >= 1:
            # Check for ties
            top_intents = [intent for intent, score in pattern_scores.items() if score == max_score]
            if len(top_intents) == 1:
                return top_intents[0]
            # Multiple intents tied - use LLM
            return await self._detect_intent_with_llm(text)
        
        # No pattern matches - use LLM for general inquiry classification
        if len(text.split()) >= 5:  # Only use LLM for longer messages worth analyzing
            return await self._detect_intent_with_llm(text)
        
        return VoiceIntent.GENERAL_INQUIRY

    async def _detect_intent_with_llm(self, text: str) -> str:
        """Use LLM to detect intent for ambiguous messages.
        
        Args:
            text: Transcribed speech
            
        Returns:
            Intent category string
        """
        try:
            intent_prompt = f"""Classify this phone call message into ONE category:

Message: "{text}"

Categories:
- pricing_info: Asking about prices, costs, rates, or fees
- hours_location: Asking about business hours, location, or directions
- booking_request: Wanting to book, schedule, sign up, or register
- support_request: Reporting a problem, complaint, or needing help with an issue
- wrong_number: Caller reached wrong number or is confused about who they called
- general_inquiry: General questions or conversation

Respond with ONLY the category name (e.g., "pricing_info"):"""

            response = await self.llm_orchestrator.generate(
                intent_prompt,
                context={"temperature": 0.0, "max_tokens": 20},
            )
            
            detected = response.strip().lower().replace('"', '').replace("'", "")
            
            # Map to our intent constants
            intent_map = {
                "pricing_info": VoiceIntent.PRICING_INFO,
                "hours_location": VoiceIntent.HOURS_LOCATION,
                "booking_request": VoiceIntent.BOOKING_REQUEST,
                "support_request": VoiceIntent.SUPPORT_REQUEST,
                "wrong_number": VoiceIntent.WRONG_NUMBER,
                "general_inquiry": VoiceIntent.GENERAL_INQUIRY,
            }
            
            return intent_map.get(detected, VoiceIntent.GENERAL_INQUIRY)
            
        except Exception as e:
            logger.warning(f"LLM intent detection failed: {e}")
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
                context={"temperature": 0.7, "max_tokens": 350},  # Natural, complete responses
            )
            llm_latency = (time.time() - llm_start) * 1000
            logger.info(f"Voice LLM latency: {llm_latency:.1f}ms")
            
            return response.strip()
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"LLM generation failed for voice: {e}", exc_info=True)
            
            # Check for quota exhaustion and provide more helpful response
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                logger.warning("LLM quota exhausted - returning quota-specific message")
                return "I'm sorry, but our AI system is currently at capacity. Please try calling back in a few minutes, or leave a message and we'll get back to you."
            
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
        
        # Build response instruction based on intent
        response_instruction = self._get_response_instruction(intent, current_message)
        
        prompt_parts = [
            system_prompt,
            f"\n\nDetected Intent: {intent}",
            "\n\nConversation:",
            "\n".join(history),
            f"\n\n{response_instruction}",
        ]
        
        return "\n".join(prompt_parts)

    def _get_response_instruction(self, intent: str, current_message: str) -> str:
        """Get tailored response instruction based on intent and message.
        
        Args:
            intent: Detected intent category
            current_message: Current user message
            
        Returns:
            Response instruction for the LLM
        """
        # Check if user is asking a question
        is_question = any(word in current_message.lower() for word in [
            "what", "when", "where", "how", "why", "which", "who", "can", "do", "does", "is", "are", "?",
        ])
        
        if is_question:
            return """You (answer the caller's question completely and naturally):
- First, directly answer their question with the specific information they need
- Use 2-4 natural sentences, speaking as you would on a friendly phone call
- If helpful, add relevant context or next steps
- Only ask a follow-up question if it naturally continues the conversation"""
        
        if intent == VoiceIntent.BOOKING_REQUEST:
            return """You (help the caller with their booking request):
- Acknowledge their interest warmly
- Provide clear information about booking or next steps
- Ask any clarifying questions needed to help them"""
        
        if intent == VoiceIntent.PRICING_INFO:
            return """You (provide pricing information naturally):
- Share the pricing details they asked about
- Keep it conversational and easy to understand
- Offer to explain or clarify anything"""
        
        # Default instruction for general conversation
        return """You (respond naturally and helpfully):
- Speak conversationally, as you would on a friendly phone call
- Provide complete, helpful information in 2-4 sentences
- Ask a natural follow-up question only if it genuinely helps the conversation"""

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
        
        # Apply speech post-processing for natural voice output
        response = self._post_process_for_speech(response)
        
        return response

    def _post_process_for_speech(self, text: str) -> str:
        """Transform formal text into natural conversational speech.
        
        This method applies various transformations to make the text sound
        more natural when spoken by TTS, reducing the "robotic" feel.
        
        Args:
            text: The formal LLM response text
            
        Returns:
            Text optimized for natural speech synthesis
        """
        if not text:
            return text
        
        # --- Contractions: Make speech more natural ---
        contraction_map = {
            r"\bI am\b": "I'm",
            r"\bI will\b": "I'll",
            r"\bI would\b": "I'd",
            r"\bI have\b": "I've",
            r"\bI had\b": "I'd",
            r"\byou are\b": "you're",
            r"\byou will\b": "you'll",
            r"\byou would\b": "you'd",
            r"\byou have\b": "you've",
            r"\bwe are\b": "we're",
            r"\bwe will\b": "we'll",
            r"\bwe would\b": "we'd",
            r"\bwe have\b": "we've",
            r"\bthey are\b": "they're",
            r"\bthey will\b": "they'll",
            r"\bthey would\b": "they'd",
            r"\bthey have\b": "they've",
            r"\bthat is\b": "that's",
            r"\bthat will\b": "that'll",
            r"\bthat would\b": "that'd",
            r"\bwhat is\b": "what's",
            r"\bwhere is\b": "where's",
            r"\bwho is\b": "who's",
            r"\bhow is\b": "how's",
            r"\bit is\b": "it's",
            r"\bit will\b": "it'll",
            r"\bit would\b": "it'd",
            r"\bthere is\b": "there's",
            r"\bthere are\b": "there're",
            r"\bhere is\b": "here's",
            r"\blet us\b": "let's",
            r"\bcannot\b": "can't",
            r"\bwill not\b": "won't",
            r"\bwould not\b": "wouldn't",
            r"\bcould not\b": "couldn't",
            r"\bshould not\b": "shouldn't",
            r"\bdo not\b": "don't",
            r"\bdoes not\b": "doesn't",
            r"\bdid not\b": "didn't",
            r"\bis not\b": "isn't",
            r"\bare not\b": "aren't",
            r"\bwas not\b": "wasn't",
            r"\bwere not\b": "weren't",
            r"\bhas not\b": "hasn't",
            r"\bhave not\b": "haven't",
            r"\bhad not\b": "hadn't",
        }
        
        for pattern, replacement in contraction_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # --- Convert numbered lists to natural flow ---
        # "1. First item 2. Second item" -> "First, first item. Then, second item."
        text = re.sub(r'\b1\.\s*', 'First, ', text)
        text = re.sub(r'\b2\.\s*', 'Then, ', text)
        text = re.sub(r'\b3\.\s*', 'Also, ', text)
        text = re.sub(r'\b4\.\s*', 'And finally, ', text)
        text = re.sub(r'\b[5-9]\.\s*', 'Additionally, ', text)
        
        # Remove bullet points
        text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
        
        # --- Replace formal phrases with conversational ones ---
        formal_to_casual = [
            (r"\bI would be happy to\b", "I'd be glad to"),
            (r"\bI would like to\b", "I'd like to"),
            (r"\bPlease do not hesitate to\b", "Feel free to"),
            (r"\bDo not hesitate to\b", "Feel free to"),
            (r"\bAt this time\b", "Right now"),
            (r"\bAt this moment\b", "Right now"),
            (r"\bIn order to\b", "To"),
            (r"\bPrior to\b", "Before"),
            (r"\bSubsequently\b", "Then"),
            (r"\bAdditionally\b", "Also"),
            (r"\bFurthermore\b", "Also"),
            (r"\bNevertheless\b", "Still"),
            (r"\bNotwithstanding\b", "Even so"),
            (r"\bWith regard to\b", "About"),
            (r"\bWith respect to\b", "About"),
            (r"\bIn the event that\b", "If"),
            (r"\bDue to the fact that\b", "Because"),
            (r"\bFor the purpose of\b", "To"),
            (r"\bIn accordance with\b", "Following"),
            (r"\bAs per your request\b", "As you asked"),
            (r"\bKindly\b", "Please"),
            (r"\bUtilize\b", "Use"),
            (r"\bPurchase\b", "Buy"),
            (r"\bAssist\b", "Help"),
            (r"\bEnquire\b", "Ask"),
            (r"\bInquire\b", "Ask"),
            (r"\bCommence\b", "Start"),
            (r"\bTerminate\b", "End"),
            (r"\bFacilitate\b", "Help with"),
            (r"\bI apologize for any inconvenience\b", "Sorry about that"),
            (r"\bWe apologize for any inconvenience\b", "Sorry about that"),
        ]
        
        for pattern, replacement in formal_to_casual:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # --- Add natural sentence starters (sparingly) ---
        # Only add fillers to sentences that start with very abrupt responses
        # This makes it feel more conversational
        sentences = text.split('. ')
        processed_sentences = []
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # For the first sentence, add a soft opener if it starts abruptly
            if i == 0 and len(sentence) > 10:
                # Check if it starts with an affirmative response pattern
                if re.match(r'^(Yes|Sure|Absolutely|Definitely|Of course)', sentence, re.IGNORECASE):
                    # Add a softer version
                    sentence = re.sub(r'^Yes,?\s*', "Yeah, ", sentence, flags=re.IGNORECASE)
                    sentence = re.sub(r'^Absolutely,?\s*', "Absolutely — ", sentence, flags=re.IGNORECASE)
                    sentence = re.sub(r'^Definitely,?\s*', "Definitely — ", sentence, flags=re.IGNORECASE)
            
            processed_sentences.append(sentence)
        
        text = '. '.join(processed_sentences)
        
        # --- Replace commas with dashes for natural pauses ---
        # Only for longer pauses (commas followed by conjunctions)
        text = re.sub(r',\s+(and|but|so|or)\s+', r' — \1 ', text)
        
        # --- Clean up spacing and punctuation ---
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single
        text = re.sub(r'\s+([.,!?])', r'\1', text)  # No space before punctuation
        text = re.sub(r'([.,!?])\s*([.,!?])', r'\1', text)  # Remove duplicate punctuation
        text = text.strip()
        
        # Ensure proper ending
        if text and not text[-1] in '.!?':
            text += '.'
        
        return text

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
            
            # Determine outcome (pass call to check handoff status)
            outcome = await self._determine_outcome(
                messages=messages,
                intent=primary_intent,
                extracted_data=extracted_data,
                call=call,
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
            
            # Send notifications based on tenant preferences
            await self._send_call_notifications(
                tenant_id=call.tenant_id,
                call=call,
                summary_text=summary_text,
                intent=primary_intent,
                outcome=outcome,
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate call summary: {e}", exc_info=True)
            return None
    
    async def _send_call_notifications(
        self,
        tenant_id: int,
        call: Call,
        summary_text: str,
        intent: str,
        outcome: str,
    ) -> None:
        """Send notifications for a completed call.
        
        Args:
            tenant_id: Tenant ID
            call: Call record
            summary_text: Generated summary text
            intent: Detected intent
            outcome: Call outcome
        """
        try:
            # Get notification config from voice settings
            notification_config = await self.voice_config_service.get_notification_config(tenant_id)
            methods = notification_config.get("methods", ["email", "in_app"])
            
            # Send call summary notification
            await self.notification_service.notify_call_summary(
                tenant_id=tenant_id,
                call_id=call.id,
                summary_text=summary_text,
                intent=intent,
                outcome=outcome,
                caller_phone=call.from_number,
                recording_url=call.recording_url,
                methods=methods,
            )
            
            # If call was a voicemail, send additional voicemail notification
            if outcome == CallOutcome.VOICEMAIL and call.recording_url:
                await self.notification_service.notify_voicemail(
                    tenant_id=tenant_id,
                    call_id=call.id,
                    caller_phone=call.from_number,
                    recording_url=call.recording_url,
                    methods=methods,
                )
            
            logger.info(f"Sent notifications for call {call.id}")
            
        except Exception as e:
            # Don't fail the summary generation if notifications fail
            logger.error(f"Failed to send call notifications: {e}", exc_info=True)

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
        call: Call | None = None,
    ) -> str:
        """Determine the outcome of the call.
        
        Args:
            messages: Conversation messages
            intent: Detected intent
            extracted_data: Extracted data
            call: Call record (optional, for checking handoff status)
            
        Returns:
            Outcome category
        """
        # Check if handoff was attempted (transferred)
        if call and call.handoff_attempted:
            return CallOutcome.TRANSFERRED
        
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
                # Auto-verify existing leads from voice calls (we have confirmed phone from caller ID)
                if existing_lead.status != 'verified':
                    existing_lead.status = 'verified'
                    await self.session.commit()
                    logger.info(f"Auto-verified lead from voice call: lead_id={lead_id}")
            elif extracted_data.name or extracted_data.email or phone:
                # Create new lead - auto-verified since we have phone from caller ID
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
                # Auto-verify voice call leads since we have confirmed phone from caller ID
                lead.status = 'verified'
                await self.session.commit()
                lead_id = lead.id
                logger.info(f"Created and auto-verified lead from voice call: lead_id={lead_id}")
            
            # If no existing contact but we have a phone number, create one
            # Voice calls always have a phone number from caller ID
            if not contact_id and phone:
                from app.persistence.models.contact import Contact
                contact = Contact(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    email=extracted_data.email,
                    phone=phone,
                    name=extracted_data.name,
                    source='voice_call',
                )
                self.session.add(contact)
                await self.session.commit()
                await self.session.refresh(contact)
                contact_id = contact.id
                logger.info(f"Created contact from voice call: contact_id={contact_id}, phone={phone}")
                
        except Exception as e:
            logger.error(f"Failed to create/update lead/contact: {e}", exc_info=True)
        
        return contact_id, lead_id

