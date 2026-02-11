"""Chat service for processing web chat requests."""

import json
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.calendar_service import CalendarService
from app.domain.services.conversation_service import ConversationService
from app.domain.services.escalation_service import EscalationService
from app.domain.services.intent_detector import IntentDetector
from app.domain.services.lead_service import LeadService
from app.domain.services.contact_service import ContactService
from app.domain.services.pending_promise_service import PendingPromiseService
from app.domain.services.promise_detector import PromiseDetector, DetectedPromise
from app.domain.services.chat_sms_handoff_service import ChatSmsHandoffService
from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
from app.domain.services.user_request_detector import UserRequestDetector
from app.domain.services.prompt_service import PromptService
from app.infrastructure.jackrabbit_client import fetch_classes, format_classes_for_prompt
from app.utils.name_validator import validate_name, extract_name_from_explicit_statement
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository
from app.persistence.repositories.tenant_repository import TenantRepository
from app.settings import settings

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for better performance
# These are compiled once at module load instead of on each function call
_EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.IGNORECASE)
_PHONE_PATTERN = re.compile(r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})')
# Pattern for explicit introductions like "I'm John", "my name is Sarah", "im ralph", "am shelly" (typo for "I'm shelly")
_EXPLICIT_NAME_PATTERN = re.compile(r"\b(?:I'?m|I am|my name is|this is|im|am|name's|call me|it's|its)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", re.IGNORECASE)
# Pattern for name stated first followed by comma and context, like "scott, im 68" or "john, I need help"
_NAME_FIRST_PATTERN = re.compile(r"^([A-Za-z]{2,15})(?:\s+[A-Za-z]{2,15})?,\s*(?:im|i'm|i am|i)\s", re.IGNORECASE)
_CAPITALIZED_NAME_PATTERN = re.compile(r"([A-Z][a-z]+\s+[A-Z][a-z]+)")
# Pattern to detect when assistant asked for the user's name
_NAME_QUESTION_PATTERN = re.compile(
    r"(?:who (?:am i|do i have the pleasure of) (?:chatting|speaking|talking) with|"
    r"what(?:'s| is) your name|"
    r"may i (?:have|get|ask) your name|"
    r"can i (?:have|get|ask) your name|"
    r"could i (?:have|get) your name|"
    r"who(?:'s| is) this|"
    r"your name\??)",
    re.IGNORECASE
)
# Pattern for standalone name response (First or First Last, with optional punctuation)
# Handles: "John", "John Smith", "John Smith.", "Regina Edwards-Thicklin"
# Case-insensitive to handle lowercase input like "dustin" - we title-case during validation
_STANDALONE_NAME_PATTERN = re.compile(r"^([A-Za-z][A-Za-z]+(?:\s+[A-Za-z][A-Za-z-]+)?)[.!]?$", re.IGNORECASE)
_DRAFT_PREFIX_PATTERN = re.compile(r'^draft\s+\d+:\s*', re.IGNORECASE)
_TRAILING_WORD_PATTERN = re.compile(r"([A-Za-z]+)$")
_LOWERCASE_ENDING_PATTERN = re.compile(r"[a-z]$")
# Pattern to extract name from bot's greeting response (e.g., "Hi Dustin!", "Nice to meet you, Dustin")
# This is a reliable fallback since the bot only greets by name when it recognized the name
# Includes common greeting patterns: "Hi X", "Hello X", "Hey X", "Nice to meet you, X"
_BOT_GREETING_NAME_PATTERN = re.compile(
    r"(?:nice to meet you|great to (?:meet you|have you (?:here|with us))|(?:good |great |so glad )to have you here|hello|hey|hi)[,!]?\s+([A-Z][a-z]+)",
    re.IGNORECASE
)
# Patterns for chat-to-SMS handoff detection
_BOT_HANDOFF_OFFER_PATTERN = re.compile(
    r"(?:text you|send you a text|(?:firing|sending|shoot) .{0,20}text|"
    r"continue (?:this |our )?(?:conversation )?(?:via|over|through|by) (?:text|sms)|"
    r"reach out (?:via|over|through) text|follow up (?:via|over|by) text|"
    r"send (?:that|this|the info|the details|the link|it) (?:to your phone|via text|by text|over)|"
    r"(?:more )?details (?:via|by|over) text|"
    r"text (?:to|at) \d{3}[\s\-]?\d{3}[\s\-]?\d{4}|"
    r"(?:i'(?:ll|m)|let me) (?:send|text|shoot|fire))",
    re.IGNORECASE,
)
_USER_HANDOFF_REQUEST_PATTERN = re.compile(
    r"(?:text me|can you text|send (?:me )?a? ?text|prefer text|rather text|switch to text|"
    r"continue (?:via|over|by) text|message me|send it to my phone|"
    r"send the (?:first )?text|text (?:this|that|it) to|shoot .{0,10}text|"
    r"(?:can you |could you )?(?:text|message|sms) (?:me|my|this|that|\d))",
    re.IGNORECASE,
)
# Pattern to detect when assistant asked for user's name
_NAME_REQUEST_PATTERN = re.compile(
    r"(?:who (?:am i|do i have the pleasure of) (?:chatting|speaking|talking) with|what(?:'s| is) your name|may i (?:have|get) your name|"
    r"(?:and )?your name(?: is)?|who(?:'s| is) this|what should i call you)",
    re.IGNORECASE
)


@dataclass
class ChatResult:
    """Result of a chat request."""

    session_id: str
    response: str
    requires_contact_info: bool
    conversation_complete: bool
    lead_captured: bool
    turn_count: int
    llm_latency_ms: float
    escalation_requested: bool = False
    escalation_id: int | None = None
    scheduling: dict | None = None  # {mode, slots[], booking_link, booking_confirmed}
    handoff_initiated: bool = False
    handoff_phone: str | None = None


class ChatService:
    """Service for processing chat requests from web widget."""

    # Guardrails
    MAX_TURNS = settings.chat_max_turns
    TIMEOUT_SECONDS = settings.chat_timeout_seconds
    FOLLOW_UP_NUDGE_TURN = settings.chat_follow_up_nudge_turn

    def __init__(self, session: AsyncSession) -> None:
        """Initialize chat service."""
        self.session = session
        self.conversation_service = ConversationService(session)
        self.escalation_service = EscalationService(session)
        self.lead_service = LeadService(session)
        self.contact_service = ContactService(session)
        self.promise_detector = PromiseDetector()
        self.user_request_detector = UserRequestDetector()
        self.promise_fulfillment_service = PromiseFulfillmentService(session)
        self.pending_promise_service = PendingPromiseService(session)
        self.prompt_service = PromptService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.tenant_repo = TenantRepository(session)
        self.cs_config_repo = CustomerServiceConfigRepository(session)
        self.calendar_service = CalendarService(session)
        self.intent_detector = IntentDetector()

    async def process_chat(
        self,
        tenant_id: int,
        session_id: str | None,
        user_message: str,
        user_name: str | None = None,
        user_email: str | None = None,
        user_phone: str | None = None,
    ) -> ChatResult:
        """Process a chat request.
        
        Args:
            tenant_id: Tenant ID (required)
            session_id: Session ID (creates new conversation if None)
            user_message: User's message
            user_name: Optional user name (for lead capture)
            user_email: Optional user email (for lead capture)
            user_phone: Optional user phone (for lead capture)
            
        Returns:
            ChatResult with response and metadata
            
        Raises:
            ValueError: If tenant not found or invalid request
        """
        # Verify tenant exists and is active
        tenant = await self.tenant_repo.get_by_id(None, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        if not tenant.is_active:
            raise ValueError(f"Tenant {tenant_id} is not active")

        # Get or create conversation
        conversation = await self._get_or_create_conversation(
            tenant_id, session_id
        )
        session_id = str(conversation.id)  # Use conversation ID as session_id

        # Get conversation history
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation.id
        )
        turn_count = len([m for m in messages if m.role == "user"])

        # Check guardrails
        if turn_count >= self.MAX_TURNS:
            return ChatResult(
                session_id=session_id,
                response="Thank you for chatting! I've reached the maximum number of turns. Please contact us directly for further assistance.",
                requires_contact_info=False,
                conversation_complete=True,
                lead_captured=False,
                turn_count=turn_count,
                llm_latency_ms=0.0,
                escalation_requested=False,
                escalation_id=None,
            )

        # Check timeout (conversation age)

        from datetime import datetime
        conversation_age = (datetime.utcnow() - conversation.created_at).total_seconds()
        if conversation_age > self.TIMEOUT_SECONDS:
            return ChatResult(
                session_id=session_id,
                response="This conversation has timed out. Please start a new conversation if you need further assistance.",
                requires_contact_info=False,
                conversation_complete=True,
                lead_captured=False,
                turn_count=turn_count,
                llm_latency_ms=0.0,
                escalation_requested=False,
                escalation_id=None,
            )

        # Add user message
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "user", user_message
        )

        # Check for escalation request (customer asking to speak with human)
        escalation_requested = False
        escalation_id = None
        escalation = await self.escalation_service.check_and_escalate(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=user_message,
            channel="chat",
            customer_phone=user_phone,
            customer_email=user_email,
            customer_name=user_name,
        )
        if escalation:
            escalation_requested = True
            escalation_id = escalation.id
            logger.info(
                f"Escalation detected in chat - tenant_id={tenant_id}, "
                f"conversation_id={conversation.id}, escalation_id={escalation.id}, "
                f"reason={escalation.reason}"
            )

        # Check if user is responding to a scheduling prompt
        scheduling_state = self._get_scheduling_state(messages)

        # STATE: pending_name_collection — user should be providing their name
        if scheduling_state and scheduling_state.get("pending_name_collection"):
            name_result = await self._handle_pending_name_for_booking(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=user_message,
                scheduling_state=scheduling_state,
                user_name=user_name,
                user_email=user_email,
                user_phone=user_phone,
            )
            if name_result:
                return name_result
            # Not a name — clear scheduling state and fall through to LLM
            await self._set_scheduling_state(
                tenant_id, conversation.id, {"awaiting_selection": False}
            )

        # STATE: pending_confirmation — user should be confirming yes/no
        elif scheduling_state and scheduling_state.get("pending_confirmation"):
            confirm_result = await self._handle_booking_confirmation(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=user_message,
                scheduling_state=scheduling_state,
                customer_name=user_name,
                customer_email=user_email,
                customer_phone=user_phone,
            )
            if confirm_result:
                return confirm_result
            # User declined or changed topic — clear state and fall through to LLM
            await self._set_scheduling_state(
                tenant_id, conversation.id, {"awaiting_selection": False}
            )

        # STATE: awaiting_selection — user should be picking a slot number
        elif scheduling_state and scheduling_state.get("awaiting_selection"):
            booking_result = await self._handle_slot_selection(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=user_message,
                scheduling_state=scheduling_state,
                customer_name=user_name,
                customer_email=user_email,
                customer_phone=user_phone,
            )
            if booking_result:
                return booking_result

        # Handle lead capture
        lead_captured = False
        if user_name or user_email or user_phone:
            # Check if lead already exists for this conversation
            existing_lead = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation.id
            )
            
            if not existing_lead:
                # Capture lead
                await self.lead_service.capture_lead(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    email=user_email,
                    phone=user_phone,
                    name=user_name,
                    metadata={"source": "chatbot"},
                )
                lead_captured = True

        # Check existing lead to see what contact info we have
        existing_lead = await self.lead_service.get_lead_by_conversation(
            tenant_id, conversation.id
        )
        
        # Build context about collected contact info for prompt
        # Pass actual values so the LLM knows what was collected (not just booleans)
        collected_name = None
        collected_email = None
        collected_phone = None

        if existing_lead:
            collected_name = existing_lead.name or None
            collected_email = existing_lead.email or None
            collected_phone = existing_lead.phone or None
        elif lead_captured:
            # Just captured in this turn
            collected_name = user_name or None
            collected_email = user_email or None
            collected_phone = user_phone or None

        # Determine if we should suggest collecting contact info
        # (but let the prompt handle it naturally, not with hardcoded messages)
        # DISABLED: Contact form popup feature disabled per user request
        # Code preserved for future use but never triggered
        requires_contact_info = False
        # Legacy logic (disabled):
        # if not (collected_email or collected_phone) and turn_count >= self.FOLLOW_UP_NUDGE_TURN:
        #     requires_contact_info = True

        # Build prompt context with contact info status (pass actual values, not just booleans)
        prompt_context = {
            "collected_name": collected_name,
            "collected_email": collected_email,
            "collected_phone": collected_phone,
            "turn_count": turn_count,
        }
        
        # Fetch live class schedule from Jackrabbit (if configured for this tenant)
        class_schedule_context = await self._get_class_schedule_context(tenant_id)

        # Use core chat processing logic with chat-specific prompt method
        llm_response, llm_latency_ms = await self._process_chat_core(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=user_message,
            messages=messages,
            system_prompt_method=self.prompt_service.compose_prompt_chat,
            prompt_context=prompt_context,
            additional_context=class_schedule_context,
        )

        # For tenant 3 (BSS), replace basic BSS URLs with Jackrabbit pre-filled URLs
        # This ensures chat responses contain the same pre-filled URLs that would be sent via SMS
        # Enriched data (name, students, class_id) is returned so promise fulfillment
        # can build SMS links with the same info the chat link has.
        bss_enriched_name = None
        bss_enriched_students = None
        bss_enriched_class_id = None
        if tenant_id == 3:
            # Get phone/name from existing lead if available
            temp_lead = await self.lead_service.get_lead_by_conversation(tenant_id, conversation.id)
            temp_phone = user_phone or (temp_lead.phone if temp_lead else None)
            temp_name = user_name or (temp_lead.name if temp_lead else None)

            llm_response, bss_enriched_name, bss_enriched_students, bss_enriched_class_id = (
                await self._replace_bss_urls_with_jackrabbit(
                    tenant_id, conversation.id, llm_response, temp_phone, temp_name,
                    messages=messages, current_user_message=user_message,
                )
            )

        # Add assistant response
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "assistant", llm_response
        )

        # IMMEDIATE NAME EXTRACTION: If the bot just greeted the user by name,
        # extract it directly from this response (most reliable method)
        immediate_name = None
        greeting_match = _BOT_GREETING_NAME_PATTERN.search(llm_response)
        if greeting_match:
            potential_name = greeting_match.group(1).strip()
            validated = validate_name(potential_name, require_explicit=True)
            if validated:
                immediate_name = validated
                logger.info(f"IMMEDIATE NAME EXTRACTION: Bot greeted user as '{immediate_name}' in response")

        # Refresh messages to include current turn (user message + assistant response)
        # This is needed for qualification checks that analyze the full conversation
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation.id
        )

        # Always try to extract contact info from conversation
        # This ensures we capture newly provided information even if a lead already exists
        logger.debug(
            f"Extracting contact info from conversation - tenant_id={tenant_id}, conversation_id={conversation.id}"
        )
        
        # Get existing lead for this conversation
        existing_lead = await self.lead_service.get_lead_by_conversation(
            tenant_id, conversation.id
        )
        if existing_lead:
            await self.lead_service.bump_lead_activity(tenant_id, existing_lead.id)

        # Track phone BEFORE extraction to detect if it was just collected this turn
        phone_before_extraction = existing_lead.phone if existing_lead else None

        # Extract contact info from conversation messages
        extracted_info = await self._extract_contact_info_from_conversation(
            messages, user_message
        )
        
        logger.info(
            f"EXTRACTION RESULT: name={extracted_info.get('name')}, "
            f"email={extracted_info.get('email')}, phone={extracted_info.get('phone')}, "
            f"name_is_explicit={extracted_info.get('name_is_explicit')}"
        )
        
        extracted_name = extracted_info.get("name")
        extracted_email = extracted_info.get("email")
        extracted_phone = extracted_info.get("phone")
        name_is_explicit = extracted_info.get("name_is_explicit", False)
        name_confidence = extracted_info.get("name_confidence", "none")

        # Use immediate name extraction (bot greeting) as highest priority — most reliable
        if immediate_name:
            if not extracted_name:
                extracted_name = immediate_name
                name_is_explicit = True
                logger.info(f"Using immediate name extraction: '{immediate_name}'")
            elif immediate_name.lower() not in (extracted_name or "").lower():
                # Bot greeted a different name than LLM extracted — trust the bot
                logger.warning(
                    f"Name mismatch: bot greeted '{immediate_name}' but LLM extracted '{extracted_name}'. Using bot greeting."
                )
                extracted_name = immediate_name
                name_is_explicit = True

        # Name-downgrade protection: don't overwrite a multi-word name (first+last)
        # with a shorter name unless we have high confidence
        if extracted_name and existing_lead and existing_lead.name:
            existing_parts = existing_lead.name.strip().split()
            new_parts = extracted_name.strip().split()
            if len(existing_parts) >= 2 and len(new_parts) < len(existing_parts) and name_confidence != "high":
                logger.info(
                    f"Name protection: keeping '{existing_lead.name}' over '{extracted_name}' "
                    f"(existing={len(existing_parts)} words, new={len(new_parts)} words, confidence={name_confidence})"
                )
                extracted_name = None
                name_is_explicit = False

        # If any contact info was extracted, create or update lead
        if extracted_name or extracted_email or extracted_phone:
            try:
                if existing_lead:
                    # Update existing lead with new information
                    # If name is from explicit introduction ("my name is X", "I'm X"),
                    # allow it to override a previously captured (possibly wrong) name
                    updated_lead = await self.lead_service.update_lead_info(
                        tenant_id=tenant_id,
                        lead_id=existing_lead.id,
                        email=extracted_email,
                        phone=extracted_phone,
                        name=extracted_name,
                        force_name_update=name_is_explicit,
                    )
                    if updated_lead:
                        logger.info(
                            f"Lead updated with extracted info - tenant_id={tenant_id}, "
                            f"conversation_id={conversation.id}, lead_id={updated_lead.id}, "
                            f"name={extracted_name}, email={extracted_email}, phone={extracted_phone}"
                        )
                        
                        # Update contact if it exists and is linked to this lead
                        await self._update_contact_from_lead(
                            tenant_id, updated_lead, extracted_email, extracted_phone, extracted_name
                        )
                else:
                    # Create new lead with extracted information
                    # skip_dedup=True ensures each conversation gets its own lead,
                    # even if the phone/email matches an existing lead (e.g., family members)
                    lead = await self.lead_service.capture_lead(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        email=extracted_email,
                        phone=extracted_phone,
                        name=extracted_name,
                        metadata={"source": "chatbot"},
                        skip_dedup=True,
                    )
                    lead_captured = True
                    logger.info(
                        f"Lead auto-captured from conversation - tenant_id={tenant_id}, "
                        f"conversation_id={conversation.id}, lead_id={lead.id}, "
                        f"name={extracted_name}, email={extracted_email}, phone={extracted_phone}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to capture/update lead after extraction - tenant_id={tenant_id}, "
                    f"conversation_id={conversation.id}, error={e}",
                    exc_info=True
                )
        else:
            logger.debug(
                f"No contact info extracted from conversation "
                f"(tenant_id={tenant_id}, conversation_id={conversation.id})"
            )
        
        # Check if we have a lead (either existing or newly created)
        if not lead_captured:
            existing_lead_after = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation.id
            )
            if existing_lead_after:
                lead_captured = True

        # Link conversation to contact if not already linked
        # This ensures the SMS handoff and lead timeline can find the conversation
        if not conversation.contact_id:
            lead_for_linking = existing_lead or await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation.id
            )
            if lead_for_linking and lead_for_linking.contact_id:
                conversation.contact_id = lead_for_linking.contact_id
                await self.session.commit()
                logger.info(
                    f"Linked conversation {conversation.id} to contact {lead_for_linking.contact_id}"
                )

        # ============================================================
        # HIGH INTENT LEAD NOTIFICATION: Check if this conversation
        # shows high enrollment intent and notify business owner
        # ============================================================
        try:
            await self._check_and_notify_high_intent_lead(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=user_message,
                messages=messages,
                lead=existing_lead or await self.lead_service.get_lead_by_conversation(tenant_id, conversation.id),
                extracted_name=extracted_name,
                extracted_phone=extracted_phone,
                extracted_email=extracted_email,
                channel="chat",
            )
        except Exception as e:
            # Don't let notification failure affect the chat flow
            logger.error(f"Failed to check/send high intent lead notification: {e}", exc_info=True)

        # Check for user requests and AI promises to send information (registration links, schedules, etc.)
        # Get phone number from user input, extracted info, or existing lead
        customer_phone = (
            user_phone
            or extracted_phone
            or (existing_lead.phone if existing_lead else None)
        )
        customer_name = (
            bss_enriched_name  # Includes last name from message scanning (if BSS)
            or user_name
            or extracted_name
            or (existing_lead.name if existing_lead else None)
        )

        # Import qualification validator for registration link validation
        from app.domain.services.registration_qualification_validator import (
            RegistrationQualificationValidator,
        )
        qualification_validator = RegistrationQualificationValidator(self.session)

        # Extract student info for BSS registration link prefill (once, reused across all fulfill calls)
        # Use enriched data from URL replacement (which already scanned the BSS URL + messages)
        # so the SMS link matches the chat link.
        extracted_students = bss_enriched_students
        extracted_class_id = bss_enriched_class_id
        if tenant_id == 3 and messages and not extracted_students:
            try:
                extracted_students, scan_class_id = self._extract_student_info_from_conversation(
                    messages
                )
                extracted_class_id = extracted_class_id or scan_class_id
            except Exception as e:
                logger.warning(f"Student extraction for fulfill_promise failed: {e}")

        # Track SMS confirmation to append to response
        sms_confirmation = None

        # Detect if phone was just collected this turn
        phone_just_collected = extracted_phone and not phone_before_extraction

        # ============================================================
        # PENDING PROMISE FULFILLMENT: If phone was just collected,
        # check for any pending promises and fulfill them
        # ============================================================
        if phone_just_collected and existing_lead:
            pending_promises = await self.pending_promise_service.get_pending_promises(existing_lead)
            if pending_promises:
                logger.info(
                    f"Phone just collected, fulfilling {len(pending_promises)} pending promises - "
                    f"tenant_id={tenant_id}, conversation_id={conversation.id}"
                )
                for pending in pending_promises:
                    try:
                        # Validate registration links before fulfillment
                        should_fulfill = True
                        if pending.asset_type == "registration_link":
                            qualification_status = await qualification_validator.check_qualification(
                                tenant_id=tenant_id,
                                conversation_id=conversation.id,
                                messages=messages,
                            )
                            if not qualification_status.is_qualified:
                                logger.info(
                                    f"Pending registration link blocked - not qualified. "
                                    f"tenant_id={tenant_id}, missing={qualification_status.missing_requirements}"
                                )
                                should_fulfill = False

                        if should_fulfill:
                            fulfillment_result = await self.promise_fulfillment_service.fulfill_promise(
                                tenant_id=tenant_id,
                                conversation_id=conversation.id,
                                promise=pending.to_detected_promise(),
                                phone=customer_phone,
                                name=customer_name,
                                messages=messages,
                                ai_response=llm_response,
                                students=extracted_students,
                                class_id=extracted_class_id,
                            )
                            await self.pending_promise_service.mark_promise_fulfilled(
                                existing_lead, pending.asset_type, fulfillment_result
                            )
                            logger.info(
                                f"Pending promise fulfilled - tenant_id={tenant_id}, "
                                f"asset_type={pending.asset_type}, status={fulfillment_result.get('status')}"
                            )
                            if fulfillment_result.get("status") == "sent":
                                sms_confirmation = "\n\nI've just sent that information to your phone via text!"
                    except Exception as e:
                        logger.error(
                            f"Failed to fulfill pending promise - tenant_id={tenant_id}, error={e}",
                            exc_info=True,
                        )

        # ============================================================
        # IMMEDIATE FULFILLMENT: Handle user requests and AI promises
        # when phone is already available
        # ============================================================
        if customer_phone:
            # First check if user requested registration info
            user_request = self.user_request_detector.detect_request(user_message)
            if user_request and user_request.confidence >= 0.6:
                logger.info(
                    f"User request detected - tenant_id={tenant_id}, "
                    f"conversation_id={conversation.id}, asset_type={user_request.asset_type}, "
                    f"confidence={user_request.confidence:.2f}"
                )

                # For registration links, validate qualification first
                should_fulfill = True
                if user_request.asset_type == "registration_link":
                    qualification_status = await qualification_validator.check_qualification(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        messages=messages,
                    )
                    if not qualification_status.is_qualified:
                        logger.info(
                            f"Registration link request blocked - not qualified. "
                            f"tenant_id={tenant_id}, missing={qualification_status.missing_requirements}"
                        )
                        should_fulfill = False

                if should_fulfill:
                    try:
                        # Convert user request to promise format for fulfillment
                        promise = DetectedPromise(
                            asset_type=user_request.asset_type,
                            confidence=user_request.confidence,
                            original_text=user_request.original_text,
                        )
                        fulfillment_result = await self.promise_fulfillment_service.fulfill_promise(
                            tenant_id=tenant_id,
                            conversation_id=conversation.id,
                            promise=promise,
                            phone=customer_phone,
                            name=customer_name,
                            messages=messages,
                            ai_response=llm_response,
                            students=extracted_students,
                            class_id=extracted_class_id,
                        )
                        logger.info(
                            f"User request fulfillment result - tenant_id={tenant_id}, "
                            f"status={fulfillment_result.get('status')}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to fulfill user request - tenant_id={tenant_id}, error={e}",
                            exc_info=True,
                        )

        # ============================================================
        # AI PROMISE DETECTION: Check for AI promises to text info
        # (runs regardless of phone availability)
        # ============================================================
        # Build conversation context for better promise classification
        conversation_context = " ".join(
            msg.content for msg in messages if msg.content
        )
        promise = self.promise_detector.detect_promise(llm_response, conversation_context)
        if promise and promise.confidence >= 0.6:
            logger.info(
                f"AI promise detected - tenant_id={tenant_id}, "
                f"conversation_id={conversation.id}, asset_type={promise.asset_type}, "
                f"confidence={promise.confidence:.2f}"
            )

            # Handle email promises separately - alert tenant instead of fulfilling
            if promise.asset_type == "email_promise":
                try:
                    from app.infrastructure.notifications import NotificationService
                    notification_service = NotificationService(self.session)

                    # Extract topic from conversation context
                    combined_text = f"{user_message} {llm_response}".lower()
                    topic = "information"  # default
                    topic_keywords = {
                        "registration": ["registration", "register", "sign up", "signup", "enroll"],
                        "pricing": ["pricing", "price", "cost", "fee", "rate", "tuition"],
                        "schedule": ["schedule", "class time", "hours", "availability", "when"],
                        "details": ["details", "information", "info", "brochure"],
                    }
                    for topic_name, keywords in topic_keywords.items():
                        if any(kw in combined_text for kw in keywords):
                            topic = topic_name
                            break

                    await notification_service.notify_email_promise(
                        tenant_id=tenant_id,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        customer_email=customer_email,
                        conversation_id=conversation.id,
                        channel="chat",
                        topic=topic,
                    )
                    logger.info(
                        f"Email promise alert sent - tenant_id={tenant_id}, "
                        f"conversation_id={conversation.id}, topic={topic}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send email promise alert - tenant_id={tenant_id}, error={e}",
                        exc_info=True,
                    )
            elif customer_phone:
                # We have a phone - fulfill immediately
                should_fulfill = True
                if promise.asset_type == "registration_link":
                    qualification_status = await qualification_validator.check_qualification(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        messages=messages,
                    )
                    if not qualification_status.is_qualified:
                        logger.info(
                            f"Registration link promise blocked - not qualified. "
                            f"tenant_id={tenant_id}, missing={qualification_status.missing_requirements}"
                        )
                        should_fulfill = False

                if should_fulfill:
                    try:
                        fulfillment_result = await self.promise_fulfillment_service.fulfill_promise(
                            tenant_id=tenant_id,
                            conversation_id=conversation.id,
                            promise=promise,
                            phone=customer_phone,
                            name=customer_name,
                            messages=messages,
                            ai_response=llm_response,
                            students=extracted_students,
                            class_id=extracted_class_id,
                        )
                        logger.info(
                            f"Promise fulfillment result - tenant_id={tenant_id}, "
                            f"status={fulfillment_result.get('status')}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to fulfill promise - tenant_id={tenant_id}, error={e}",
                            exc_info=True,
                        )
            else:
                # No phone available - store as pending promise for later fulfillment
                if existing_lead:
                    await self.pending_promise_service.store_pending_promise(existing_lead, promise)
                    logger.info(
                        f"Stored pending promise (no phone yet) - tenant_id={tenant_id}, "
                        f"conversation_id={conversation.id}, asset_type={promise.asset_type}"
                    )

        # ============================================================
        # CHAT-TO-SMS HANDOFF: If bot offered to text or user requested,
        # initiate handoff to SMS channel
        # ============================================================
        handoff_initiated = False
        handoff_phone = None
        if customer_phone and not sms_confirmation:
            # Check if bot offered to text OR user requested text
            bot_offered = bool(_BOT_HANDOFF_OFFER_PATTERN.search(llm_response))
            user_requested = bool(_USER_HANDOFF_REQUEST_PATTERN.search(user_message))
            if bot_offered or user_requested:
                try:
                    handoff_service = ChatSmsHandoffService(self.session)
                    handoff_result = await handoff_service.initiate_handoff(
                        tenant_id=tenant_id,
                        chat_conversation_id=conversation.id,
                        phone=customer_phone,
                        customer_name=customer_name,
                    )
                    if handoff_result.status == "sent":
                        handoff_initiated = True
                        handoff_phone = customer_phone
                        sms_confirmation = "\n\nI've just sent you a text message! Feel free to continue our conversation there."
                        logger.info(
                            f"Chat-to-SMS handoff triggered - tenant_id={tenant_id}, "
                            f"conversation_id={conversation.id}, sms_conv={handoff_result.sms_conversation_id}"
                        )
                    elif handoff_result.status == "skipped":
                        logger.info(
                            f"Chat-to-SMS handoff skipped (already done) - tenant_id={tenant_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"Chat-to-SMS handoff failed - tenant_id={tenant_id}, error={e}",
                        exc_info=True,
                    )

        # Build final response with optional SMS confirmation
        final_response = llm_response
        if sms_confirmation:
            final_response = llm_response + sms_confirmation

        # ============================================================
        # SCHEDULING: If escalation or scheduling intent detected,
        # offer available time slots or booking link
        # ============================================================
        scheduling_data = None
        intent_result = self.intent_detector.detect_intent(user_message)
        if escalation_requested or intent_result.intent == "scheduling":
            try:
                scheduling_mode = await self.calendar_service.get_scheduling_mode(tenant_id)
                if scheduling_mode == "calendar_api":
                    from datetime import date as date_type
                    slots = await self.calendar_service.get_available_slots(
                        tenant_id, date_type.today()
                    )
                    if slots:
                        slot_text = "\n\nI can help you schedule a meeting. Here are some available times:\n"
                        slot_list = []
                        for i, slot in enumerate(slots, 1):
                            slot_text += f"\n{i}. {slot.display_label}"
                            slot_list.append({
                                "start": slot.start.isoformat(),
                                "end": slot.end.isoformat(),
                                "display_label": slot.display_label,
                            })
                        slot_text += "\n\nPlease select a time that works for you."
                        final_response += slot_text

                        # Store scheduling state as system message metadata
                        await self._set_scheduling_state(
                            tenant_id, conversation.id,
                            {"awaiting_selection": True, "offered_slots": slot_list},
                        )

                        scheduling_data = {
                            "mode": "calendar_api",
                            "slots": slot_list,
                        }
                        logger.info(
                            f"Scheduling slots offered in chat - tenant_id={tenant_id}, "
                            f"conversation_id={conversation.id}, num_slots={len(slots)}"
                        )
                elif scheduling_mode == "booking_link":
                    link = await self.calendar_service.get_booking_link(tenant_id)
                    if link:
                        final_response += f"\n\nYou can schedule a meeting here: {link}"
                        scheduling_data = {
                            "mode": "booking_link",
                            "booking_link": link,
                        }
            except Exception as e:
                logger.error(
                    f"Failed to offer scheduling in chat - tenant_id={tenant_id}, error={e}",
                    exc_info=True,
                )

        return ChatResult(
            session_id=session_id,
            response=final_response,
            requires_contact_info=requires_contact_info and not lead_captured,
            conversation_complete=False,
            lead_captured=lead_captured,
            turn_count=turn_count + 1,
            llm_latency_ms=llm_latency_ms,
            escalation_requested=escalation_requested,
            escalation_id=escalation_id,
            scheduling=scheduling_data,
            handoff_initiated=handoff_initiated,
            handoff_phone=handoff_phone,
        )

    async def _update_contact_from_lead(
        self,
        tenant_id: int,
        lead,
        extracted_email: str | None,
        extracted_phone: str | None,
        extracted_name: str | None,
    ) -> None:
        """Update contact linked to a lead with newly extracted information.

        Args:
            tenant_id: Tenant ID
            lead: Lead object that was updated
            extracted_email: Email that was extracted (only update if contact email is missing)
            extracted_phone: Phone that was extracted (only update if contact phone is missing)
            extracted_name: Name that was extracted (only update if contact name is missing)
        """
        if not lead or not lead.id:
            return

        try:
            # Find contact linked to this lead by lead_id
            from sqlalchemy import select
            from app.persistence.models.contact import Contact
            
            stmt = select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.lead_id == lead.id,
                Contact.deleted_at.is_(None),
                Contact.merged_into_contact_id.is_(None)
            )
            result = await self.session.execute(stmt)
            contact = result.scalar_one_or_none()
            
            if contact:
                # Update contact with missing fields only
                update_data = {}
                if extracted_email and not contact.email:
                    update_data['email'] = extracted_email
                if extracted_phone and not contact.phone:
                    update_data['phone'] = extracted_phone
                if extracted_name and not contact.name:
                    update_data['name'] = extracted_name
                
                if update_data:
                    await self.contact_service.update_contact(
                        tenant_id=tenant_id,
                        contact_id=contact.id,
                        **update_data
                    )
                    logger.info(
                        f"Updated contact {contact.id} from lead {lead.id} with new info: {update_data}"
                    )
        except Exception as e:
            logger.error(
                f"Failed to update contact from lead {lead.id}: {e}",
                exc_info=True
            )

    # ============================================================
    # SCHEDULING HELPERS
    # ============================================================

    def _get_scheduling_state(self, messages) -> dict | None:
        """Read scheduling state from recent system messages with metadata."""
        # Scan messages in reverse to find the most recent scheduling state
        for msg in reversed(messages):
            if msg.role == "system" and msg.message_metadata:
                meta = msg.message_metadata
                if isinstance(meta, dict) and "scheduling_state" in meta:
                    return meta["scheduling_state"]
        return None

    async def _set_scheduling_state(
        self, tenant_id: int, conversation_id: int, state: dict
    ) -> None:
        """Store scheduling state as a system message with metadata."""
        await self.conversation_service.add_message(
            tenant_id, conversation_id, "system", "[scheduling]",
            metadata={"scheduling_state": state},
        )

    async def _handle_slot_selection(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        scheduling_state: dict,
        customer_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> ChatResult | None:
        """Handle a user's time slot selection.

        Parses the user's message to match an offered slot, books the meeting,
        and returns a confirmation ChatResult. Returns None if no match found
        (the message will proceed through normal LLM processing).
        """
        offered_slots = scheduling_state.get("offered_slots", [])
        if not offered_slots:
            return None

        # Try to match the user's message to an offered slot
        selected_slot = None
        msg_lower = user_message.strip().lower()

        # Match by number (e.g., "1", "option 1", "number 2")
        import re
        num_match = re.search(r'\b(\d{1,2})\b', msg_lower)
        if num_match:
            idx = int(num_match.group(1)) - 1  # 1-indexed
            if 0 <= idx < len(offered_slots):
                selected_slot = offered_slots[idx]

        # Match by display label substring
        if not selected_slot:
            for slot in offered_slots:
                label_lower = slot.get("display_label", "").lower()
                if label_lower and label_lower in msg_lower:
                    selected_slot = slot
                    break

        # Match by "book" keyword + any partial time reference
        if not selected_slot and ("book" in msg_lower or "select" in msg_lower or "pick" in msg_lower):
            if num_match:
                idx = int(num_match.group(1)) - 1
                if 0 <= idx < len(offered_slots):
                    selected_slot = offered_slots[idx]

        if not selected_slot:
            # User message doesn't match a slot - let it go through normal LLM flow
            return None

        # Instead of booking immediately, ask for confirmation
        selected_slot_data = {
            "start": selected_slot["start"],
            "end": selected_slot.get("end"),
            "display_label": selected_slot["display_label"],
        }

        await self._set_scheduling_state(
            tenant_id, conversation_id,
            {
                "pending_confirmation": True,
                "selected_slot": selected_slot_data,
                "offered_slots": offered_slots,
            },
        )

        confirmation_prompt = (
            f"Would you like me to book {selected_slot['display_label']} for you? "
            "Just reply yes to confirm, or let me know if you'd prefer a different time."
        )

        await self.conversation_service.add_message(
            tenant_id, conversation_id, "assistant", confirmation_prompt,
        )

        session_id = str(conversation_id)
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation_id
        )
        turn_count = len([m for m in messages if m.role == "user"])

        return ChatResult(
            session_id=session_id,
            response=confirmation_prompt,
            requires_contact_info=False,
            conversation_complete=False,
            lead_captured=False,
            turn_count=turn_count,
            llm_latency_ms=0.0,
            escalation_requested=False,
            escalation_id=None,
            scheduling={"mode": "calendar_api", "awaiting_confirmation": True},
        )

    async def _handle_booking_confirmation(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        scheduling_state: dict,
        customer_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> ChatResult | None:
        """Handle user's yes/no response to booking confirmation.

        Returns ChatResult if user confirmed (proceeds to book or collect name).
        Returns None if user declined or message doesn't match (caller clears state).
        """
        msg_lower = user_message.strip().lower()

        affirmative_words = {
            "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
            "book it", "book that", "sounds good", "perfect", "please",
            "go ahead", "let's do it", "lets do it", "do it", "absolutely",
            "that works", "works for me", "i'll take it", "ill take it",
            "y", "si", "yes please",
        }

        is_confirmed = any(word in msg_lower for word in affirmative_words)

        if not is_confirmed:
            return None

        selected_slot = scheduling_state.get("selected_slot")
        if not selected_slot:
            return None

        # Check if we have a customer name
        name = customer_name
        if not name:
            existing_lead = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation_id
            )
            if existing_lead and existing_lead.name:
                name = existing_lead.name

        if not name:
            # No name available — collect before booking
            await self._set_scheduling_state(
                tenant_id, conversation_id,
                {"pending_name_collection": True, "selected_slot": selected_slot},
            )

            name_prompt = "Before I finalize the booking, may I have your name?"

            await self.conversation_service.add_message(
                tenant_id, conversation_id, "assistant", name_prompt,
            )

            session_id = str(conversation_id)
            messages = await self.conversation_service.get_conversation_history(
                tenant_id, conversation_id
            )
            turn_count = len([m for m in messages if m.role == "user"])

            return ChatResult(
                session_id=session_id,
                response=name_prompt,
                requires_contact_info=False,
                conversation_complete=False,
                lead_captured=False,
                turn_count=turn_count,
                llm_latency_ms=0.0,
                escalation_requested=False,
                escalation_id=None,
                scheduling={"mode": "calendar_api", "awaiting_name": True},
            )

        # We have a name — book immediately
        return await self._execute_booking(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            selected_slot=selected_slot,
            customer_name=name,
            customer_email=customer_email,
            customer_phone=customer_phone,
        )

    async def _handle_pending_name_for_booking(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        scheduling_state: dict,
        user_name: str | None = None,
        user_email: str | None = None,
        user_phone: str | None = None,
    ) -> ChatResult | None:
        """Handle name collection for a pending booking.

        Tries to extract a name from the user message. If found, saves the lead
        and books the meeting. Returns None if the message doesn't look like a
        name (user changed topic — caller clears state).
        """
        from app.utils.name_validator import validate_name

        selected_slot = scheduling_state.get("selected_slot")
        if not selected_slot:
            return None

        # Try to get name from widget form field first
        name = user_name

        if not name:
            # Try regex extraction (handles "I'm Sarah", "my name is John", etc.)
            extracted_name, _ = self._extract_name_regex(user_message)
            if extracted_name:
                name = extracted_name

        if not name:
            # Try standalone name pattern (just "Sarah" or "Sarah Jones")
            standalone_match = _STANDALONE_NAME_PATTERN.match(user_message.strip())
            if standalone_match:
                potential = standalone_match.group(1)
                validated = validate_name(potential)
                if validated:
                    name = validated

        if not name:
            # Message doesn't look like a name — user probably changed topic
            return None

        # Save name to lead
        existing_lead = await self.lead_service.get_lead_by_conversation(
            tenant_id, conversation_id
        )
        if existing_lead:
            await self.lead_service.update_lead_info(
                tenant_id=tenant_id,
                lead_id=existing_lead.id,
                name=name,
                force_name_update=True,
            )
        else:
            await self.lead_service.capture_lead(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                name=name,
            )

        # Now book the meeting
        return await self._execute_booking(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            selected_slot=selected_slot,
            customer_name=name,
            customer_email=user_email,
            customer_phone=user_phone,
        )

    async def _execute_booking(
        self,
        tenant_id: int,
        conversation_id: int,
        selected_slot: dict,
        customer_name: str,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> ChatResult:
        """Execute the actual calendar booking and return ChatResult.

        This is the final step — only called after confirmation and name collection.
        """
        from datetime import datetime as dt
        slot_start = dt.fromisoformat(selected_slot["start"])

        result = await self.calendar_service.book_meeting(
            tenant_id=tenant_id,
            slot_start=slot_start,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            topic="Meeting requested via chatbot",
        )

        # Clear scheduling state
        await self._set_scheduling_state(
            tenant_id, conversation_id, {"awaiting_selection": False},
        )

        if result.success:
            confirmation_text = (
                f"Your meeting has been booked for {selected_slot['display_label']}! "
                "You should receive a calendar invitation shortly."
            )
            scheduling_data = {
                "mode": "calendar_api",
                "booking_confirmed": {
                    "display_label": selected_slot["display_label"],
                    "event_link": result.event_link,
                },
            }
        else:
            confirmation_text = (
                f"I'm sorry, I wasn't able to book that time slot. {result.error or ''} "
                "Would you like to try a different time?"
            )
            scheduling_data = None

        await self.conversation_service.add_message(
            tenant_id, conversation_id, "assistant", confirmation_text,
        )

        session_id = str(conversation_id)
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation_id
        )
        turn_count = len([m for m in messages if m.role == "user"])

        return ChatResult(
            session_id=session_id,
            response=confirmation_text,
            requires_contact_info=False,
            conversation_complete=False,
            lead_captured=False,
            turn_count=turn_count,
            llm_latency_ms=0.0,
            escalation_requested=False,
            escalation_id=None,
            scheduling=scheduling_data,
        )

    async def _get_or_create_conversation(
        self, tenant_id: int, session_id: str | None
    ) -> Conversation:
        """Get existing conversation or create new one.
        
        Args:
            tenant_id: Tenant ID
            session_id: Session ID (conversation ID as string)
            
        Returns:
            Conversation
        """
        if session_id:
            try:
                conversation_id = int(session_id)
                conversation = await self.conversation_service.get_conversation(
                    tenant_id, conversation_id
                )
                if conversation:
                    return conversation
            except ValueError:
                pass  # Invalid session_id, create new
        
        # Create new conversation
        return await self.conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="web",
            external_id=None,
        )

    async def _get_class_schedule_context(self, tenant_id: int) -> str | None:
        """Fetch live class schedule from Jackrabbit for prompt injection."""
        try:
            config = await self.cs_config_repo.get_by_tenant_id(tenant_id)
            if not config or not config.settings:
                return None
            org_id = config.settings.get("jackrabbit_org_id")
            if not org_id:
                return None
            classes = await fetch_classes(org_id)
            if not classes:
                return None
            return format_classes_for_prompt(classes)
        except Exception as e:
            logger.warning(f"Failed to fetch class schedule for tenant {tenant_id}: {e}")
            return None

    async def _check_and_notify_high_intent_lead(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        messages: list,
        lead,
        extracted_name: str | None,
        extracted_phone: str | None,
        extracted_email: str | None,
        channel: str = "chat",
    ) -> None:
        """Check for high enrollment intent and notify business owner if detected.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            user_message: Current user message
            messages: Full conversation history
            lead: Lead object (if exists)
            extracted_name: Name extracted from conversation
            extracted_phone: Phone extracted from conversation
            extracted_email: Email extracted from conversation
            channel: Communication channel (chat, sms, voice, email)
        """
        from app.domain.services.intent_detector import IntentDetector
        from app.infrastructure.notifications import NotificationService

        # Build conversation history strings for intent detection
        conversation_history = [msg.content for msg in messages if hasattr(msg, "content")]

        # Determine contact info status
        has_phone = bool(extracted_phone or (lead and lead.phone))
        has_email = bool(extracted_email or (lead and lead.email))

        # Detect enrollment intent
        intent_detector = IntentDetector()
        intent_result = intent_detector.detect_enrollment_intent(
            message=user_message,
            conversation_history=conversation_history,
            has_phone=has_phone,
            has_email=has_email,
        )

        if not intent_result.is_high_intent:
            logger.debug(
                f"No high intent detected - tenant_id={tenant_id}, "
                f"conversation_id={conversation_id}, confidence={intent_result.confidence:.2f}"
            )
            return

        logger.info(
            f"High enrollment intent detected - tenant_id={tenant_id}, "
            f"conversation_id={conversation_id}, confidence={intent_result.confidence:.2f}, "
            f"keywords={intent_result.keywords}, boost_factors={intent_result.boost_factors}"
        )

        # Get customer info
        customer_name = extracted_name or (lead.name if lead else None)
        customer_phone = extracted_phone or (lead.phone if lead else None)
        customer_email = extracted_email or (lead.email if lead else None)

        # Send notification
        notification_service = NotificationService(self.session)
        result = await notification_service.notify_high_intent_lead(
            tenant_id=tenant_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            channel=channel,
            message_preview=user_message[:150],
            confidence=intent_result.confidence,
            keywords=intent_result.keywords,
            conversation_id=conversation_id,
            lead_id=lead.id if lead else None,
        )

        logger.info(
            f"Lead notification result - tenant_id={tenant_id}, "
            f"conversation_id={conversation_id}, status={result.get('status')}"
        )

    def _build_conversation_context(
        self,
        system_prompt: str,
        messages: list[Message],
        current_user_message: str,
        additional_context: str | None = None,
    ) -> str:
        """Build conversation context for LLM.
        
        Args:
            system_prompt: System prompt from tenant settings (already includes contact collection guidance)
            messages: Previous messages in conversation
            current_user_message: Current user message
            additional_context: Additional context to add to prompt
            
        Returns:
            Full prompt string for LLM
        """
        # Build conversation history
        conversation_history = []
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            conversation_history.append(f"{role_label}: {msg.content}")
        
        # Add current user message
        conversation_history.append(f"User: {current_user_message}")
        
        # Build full prompt
        prompt_parts = [system_prompt]
        
        if conversation_history:
            prompt_parts.append("\n\nConversation History:")
            prompt_parts.append("\n".join(conversation_history))
        
        if additional_context:
            prompt_parts.append(f"\n\n{additional_context}")
        
        prompt_parts.append("\n\nAssistant:")
        
        return "\n".join(prompt_parts)

    def _extract_email_regex(self, text: str) -> str | None:
        """Extract email using regex as fallback."""
        matches = _EMAIL_PATTERN.findall(text)
        return matches[0].lower() if matches else None
    
    def _extract_phone_regex(self, text: str) -> str | None:
        """Extract phone number using regex as fallback."""
        matches = _PHONE_PATTERN.findall(text)
        if matches:
            # Extract digits only
            match = matches[0]
            digits = ''.join([m for m in match if m and m.isdigit()])
            if len(digits) >= 10:
                # Format as US phone: +1XXXXXXXXXX or just the 10 digits
                if len(digits) == 10:
                    return digits
                elif len(digits) == 11 and digits[0] == '1':
                    return digits
        return None
    
    def _extract_name_regex(self, text: str) -> tuple[str | None, bool]:
        """Extract name using regex patterns as fallback.

        Returns:
            Tuple of (name, is_explicit) where is_explicit indicates if the name
            came from an explicit introduction like "my name is X" or "I'm X".
            Explicit names should be allowed to overwrite previously captured names.
        """
        # Common false positives - phrases that look like names but aren't
        # These are common chat phrases that get incorrectly matched
        false_positive_names = {
            'hey whats', 'hey what', 'hi there', 'hello there', 'going good',
            'doing good', 'pretty good', 'sounds good', 'looks good',
            'thank you', 'thanks much', 'nice one', 'good morning',
            'good afternoon', 'good evening', 'good night', 'how are',
            'what is', 'who is', 'where is', 'when is', 'why is',
            'can you', 'could you', 'would you', 'will you', 'should you',
            # Single words that are commonly misinterpreted as names
            'good', 'great', 'fine', 'cool', 'nice', 'ok', 'okay', 'sure',
            'yes', 'no', 'nah', 'yeah', 'yep', 'nope', 'thanks', 'thank',
            'im good', 'nah im good', 'all good', 'thats good', "that's good",
        }

        # Common stop words that indicate the name has ended
        # Includes conjunctions, prepositions, common response words, and verbs that often follow names in requests
        stop_words = {
            'and', 'is', 'my', 'the', 'a', 'an', 'with', 'or', 'to', 'for', 'in', 'on', 'at', 'from',
            'yea', 'yeah', 'yes', 'no', 'ok', 'okay', 'sure', 'thanks', 'thank', 'please', 'hi', 'hey',
            'i', 'we', 'you', 'they', 'he', 'she', 'it', 'this', 'that', 'here', 'there',
            # Common verbs that follow names in requests like "im ralph give me the schedule"
            'give', 'send', 'tell', 'show', 'get', 'need', 'want', 'can', 'could', 'would', 'will',
            'let', 'help', 'just', 'now', 'looking', 'interested', 'calling', 'texting', 'asking',
            # Common adjectives/state descriptors that users say after "I'm" (e.g., "I'm comfortable floating")
            'comfortable', 'able', 'available', 'ready', 'happy', 'excited', 'nervous', 'afraid',
            'good', 'great', 'fine', 'okay', 'doing', 'feeling', 'trying', 'learning', 'starting',
            'new', 'beginner', 'intermediate', 'advanced', 'experienced', 'not', 'very', 'really',
            'currently', 'also', 'actually', 'already', 'still', 'completely', 'totally', 'mostly',
        }

        # Pattern 0: Name stated first, like "scott, im 68" or "john, i need help"
        # This handles cases where users put their name first followed by comma
        match = _NAME_FIRST_PATTERN.match(text)
        if match:
            name = match.group(1).strip()
            name = name.capitalize()
            if len(name) >= 2 and name.lower() not in false_positive_names:
                return (name, True)  # True = explicit name introduction

        # Pattern 1: Explicit name introduction phrases (case insensitive)
        # Patterns like "I'm X", "my name is X", "I am X", "this is X", "im X", "call me X"
        # Use word boundary \b to avoid matching "im" inside words like "swim"
        matches = _EXPLICIT_NAME_PATTERN.findall(text)
        if matches:
            name = matches[0].strip()
            # Split into words and stop at first stop word
            name_parts = []
            for word in name.split():
                if word.lower() in stop_words:
                    break
                name_parts.append(word)
                # Limit to 2 words (first name, last name)
                if len(name_parts) >= 2:
                    break

            if name_parts:
                name = ' '.join(name_parts)
                # Capitalize first letter of each word for consistency
                name = ' '.join(word.capitalize() for word in name.split())
                # Filter out common false positives
                if len(name) > 2 and name.lower() not in false_positive_names:
                    # Skip common sentence starters/words
                    if name.lower() not in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'here', 'there', 'just']:
                        return (name, True)  # True = explicit name introduction

        # Pattern 2: Proper capitalized First Last format (case SENSITIVE - must be properly capitalized)
        # This pattern requires actual capital letters to avoid matching casual phrases
        # Use case-sensitive matching here - names should be capitalized
        matches = _CAPITALIZED_NAME_PATTERN.findall(text)
        if matches:
            name = matches[0].strip()
            # Check it's not a false positive
            if name.lower() not in false_positive_names:
                # Additional check: skip if both words are common English words
                common_words = {'hey', 'hello', 'going', 'doing', 'good', 'nice', 'thank', 'thanks',
                               'pretty', 'sounds', 'looks', 'what', 'whats', 'how', 'who', 'where',
                               'when', 'why', 'can', 'could', 'would', 'will', 'should'}
                # Words that are never last names - adjectives/state descriptors that follow "I'm"
                # e.g., "I'm comfortable floating" should not make "Comfortable" a last name
                non_surname_words = {'comfortable', 'interested', 'able', 'available', 'ready',
                                    'happy', 'excited', 'nervous', 'afraid', 'new', 'fine', 'great',
                                    'looking', 'trying', 'learning', 'starting', 'calling', 'texting',
                                    'beginner', 'intermediate', 'advanced', 'experienced'}
                # US state names - these are never last names
                us_states = {'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
                            'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
                            'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
                            'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
                            'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
                            'hampshire', 'jersey', 'mexico', 'york', 'carolina', 'dakota',
                            'ohio', 'oklahoma', 'oregon', 'pennsylvania', 'island', 'tennessee',
                            'texas', 'utah', 'vermont', 'virginia', 'washington', 'wisconsin', 'wyoming'}
                words = name.lower().split()
                # Skip if both words are common, OR if the second word is a non-surname word
                if (words[0] in common_words and words[1] in common_words) or words[1] in non_surname_words:
                    pass  # Skip this match
                # Skip if second word is a US state (e.g., "Spring Texas", "Fort Worth")
                elif words[1] in us_states or words[0] in us_states:
                    logger.debug(f"Skipping potential location name: {name}")
                    pass  # Skip - this is likely a location
                # Skip if preceded by location phrases like "I live in", "I'm in", "located in", etc.
                elif re.search(rf'\b(?:i\s+live\s+in|i\'?m\s+in|i\s+am\s+in|live\s+in|from|near|located\s+in|based\s+in|reside\s+in)\s+{re.escape(name)}\b', text, re.IGNORECASE):
                    logger.debug(f"Skipping location after 'I live in' or similar: {name}")
                    pass  # Skip - this is clearly a location
                else:
                    return (name, False)  # False = not an explicit introduction

        return (None, False)

    async def _extract_contact_info_from_conversation(
        self,
        messages: list[Message],
        current_user_message: str,
    ) -> dict[str, str | None | bool]:
        """Extract contact information from conversation using LLM as primary method.

        The LLM reads the full conversation transcript and uses context to identify
        the user's name, email, and phone. This is more reliable than regex patterns
        because the LLM understands conversational context (e.g., when the bot asks
        "who am I chatting with?" and the user responds "Regina").

        Args:
            messages: Previous messages in conversation
            current_user_message: Current user message

        Returns:
            Dictionary with 'name', 'email', 'phone' keys (values may be None),
            and 'name_is_explicit' bool indicating if name came from explicit introduction
        """
        # Build full conversation transcript for LLM
        conversation_text = []
        for msg in messages:
            if msg.role == "user":
                conversation_text.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                conversation_text.append(f"Assistant: {msg.content}")
        # NOTE: Do NOT append current_user_message here — `messages` (refreshed
        # on line 363) already includes it.  Appending again would duplicate
        # the last user message in the transcript and confuse the LLM.

        # Use last 20 messages for context (covers most conversations fully)
        recent_messages = conversation_text[-20:]
        transcript = "\n".join(recent_messages)

        # Also run regex for email/phone (these are reliable patterns)
        all_user_text = current_user_message
        for msg in messages:
            if msg.role == "user":
                all_user_text += " | " + msg.content
        regex_email = self._extract_email_regex(all_user_text)
        regex_phone = self._extract_phone_regex(all_user_text)

        # LLM extraction prompt - focused on reading context
        extraction_prompt = f"""Read this conversation transcript and identify the USER's contact information.

TRANSCRIPT:
{transcript}

YOUR TASK: Extract the user's name, email, and phone number based on the conversation context.

NAME EXTRACTION - Read the conversation carefully:
1. ONLY extract the user's PERSONAL name when the assistant asks for it directly:
   - "who am I chatting with?" or "what's your name?" or "may I have your name?"
   - The user's response to THAT specific question IS their name
2. Also look for confirmations like "Nice to meet you, Regina!" - the assistant confirmed the name
3. Look for explicit introductions: "I'm John", "my name is Sarah", "this is Mike", "Am Sarah" (typo for "I'm Sarah")
4. If the user gives first name then last name separately, combine them (e.g., "Regina" then "Edwards-Thicklin" = "Regina Edwards-Thicklin")
5. Email addresses can hint at names (e.g., "thicklin.regina@yahoo.com" suggests "Regina")

CRITICAL - DO NOT extract these as names (these are NOT the user's personal name):
- Answers to "who is swimming?" or "who is this for?" or "who will be taking lessons?":
  - "my child", "my kid", "my son", "my daughter", "my kids", "my children"
  - "my husband", "my wife", "my spouse", "my parent", "my mom", "my dad"
  - "my friend", "my partner", "my family"
- Common English words are NEVER names: feel, feeling, spring, pool, water, class, warm, cold, hot, deep, start, stop, begin, end, love, like, enjoy, wish, hope, open, free, busy, ready, able
- Verbs: need, want, help, calling, texting, checking, enrolling, signing
- Responses: yes, no, ok, sure, thanks
- Business terms: hvac, plumbing, dental, swim, lessons
- Skill levels: beginner, intermediate, advanced
- If you are NOT CERTAIN the extracted value is a human personal name, return null

NAME CONFIDENCE - How certain are you that this is the user's name?
- "high": User explicitly stated their name ("I'm X", "my name is X", responded directly to "what's your name?") OR assistant greeted them by name ("Hi Lesbia", "Nice to meet you, John")
- "medium": Name is inferred indirectly (from email address, mentioned in passing, uncertain context)
- "none": No name found (return null for name)

EMAIL/PHONE: Extract any email address or phone number the user provided.

Respond with ONLY this JSON (no other text):
{{"name": null, "email": null, "phone": null, "name_confidence": "none"}}

Replace null with the actual value if found. Use null if not found or uncertain."""

        result = {"name": None, "email": regex_email, "phone": regex_phone, "name_is_explicit": False}

        try:
            logger.debug(f"LLM name extraction - transcript length: {len(transcript)} chars")
            response = await self.llm_orchestrator.generate(
                extraction_prompt,
                context={"temperature": 0.0, "max_tokens": 150},
            )

            # Parse JSON response
            response = response.strip()

            # Log if response is empty (common Gemini issue)
            if not response:
                logger.warning("LLM returned empty response for name extraction - falling back to regex")

            # Strip markdown code blocks if present
            if response.startswith("`"):
                response = response.lstrip("`")
                if response.lower().startswith("json"):
                    response = response[4:].lstrip()
                if "\n" in response:
                    lines = response.split("\n")
                    if lines and lines[-1].strip().replace("`", "") == "":
                        lines = lines[:-1]
                    response = "\n".join(lines).strip()
                response = response.rstrip("`").strip()

            # Extract JSON
            if response.startswith("{"):
                json_end = response.rfind("}") + 1
                response = response[:json_end]
            else:
                start = response.find("{")
                end = response.rfind("}") + 1
                if start != -1 and end > start:
                    response = response[start:end]
                else:
                    logger.warning(f"No JSON in LLM response: {response[:100]}")
                    return result

            extracted = json.loads(response)
            llm_name = extracted.get("name")
            llm_email = extracted.get("email")
            llm_phone = extracted.get("phone")
            llm_confidence = extracted.get("name_confidence", "none")

            logger.info(f"LLM extraction: name={llm_name}, email={llm_email}, phone={llm_phone}, confidence={llm_confidence}")

            # Validate and use LLM name
            if llm_name and llm_name != "null" and isinstance(llm_name, str):
                validated_name = validate_name(llm_name, require_explicit=True)
                if validated_name:
                    result["name"] = validated_name
                    # Only mark as explicit (allowing overwrite of existing name) for high confidence
                    result["name_is_explicit"] = (llm_confidence == "high")
                    result["name_confidence"] = llm_confidence
                    logger.info(f"Using LLM-extracted name: '{validated_name}' (confidence={llm_confidence}, explicit={result['name_is_explicit']})")
                else:
                    logger.info(f"LLM name '{llm_name}' rejected by validation")

            # Use LLM email/phone if regex didn't find them
            if llm_email and llm_email != "null" and not result["email"]:
                result["email"] = llm_email
            if llm_phone and llm_phone != "null" and not result["phone"]:
                result["phone"] = llm_phone

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # Fall through to regex fallback below
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}", exc_info=True)
            # Fall through to regex fallback below

        # CONTEXT-AWARE FALLBACK: If assistant just asked for name, user's response IS their name
        # This is the most reliable pattern - "who am I chatting with?" -> "Terrell Pipkin."
        if not result["name"] and messages:
            # Find the last assistant message
            last_assistant_msg = None
            for msg in reversed(messages):
                if msg.role == "assistant":
                    last_assistant_msg = msg.content
                    break

            # Check if assistant asked for name
            if last_assistant_msg and _NAME_QUESTION_PATTERN.search(last_assistant_msg):
                # User's current message is likely their name - check if it looks like a name
                standalone_match = _STANDALONE_NAME_PATTERN.match(current_user_message.strip())
                if standalone_match:
                    potential_name = standalone_match.group(1)
                    validated = validate_name(potential_name, require_explicit=True)
                    if validated:
                        result["name"] = validated
                        result["name_is_explicit"] = True
                        logger.info(f"Context-aware name extraction: assistant asked for name, user replied '{validated}'")

        # NOTE: Regex fallback for name extraction was removed.
        # It ran on ALL user text and caused persistent false positives
        # ("My Child", "More About", etc.). LLM + context-aware fallback
        # + bot greeting extraction (line ~354) are sufficient and more reliable.

        return result

    def _extract_student_info_from_conversation(
        self,
        messages: list[Message],
    ) -> tuple[list, str | None]:
        """Extract student/swimmer info and class_id from BSS chat conversation.

        Uses pattern matching on conversation Q&A pairs — the bot follows a
        predictable script asking about swimmers, ages, gender, and class preference.
        No LLM call needed; this is fast and reliable.

        Returns:
            Tuple of (list of StudentInfo, class_id or None)
        """
        from datetime import date
        from app.utils.jackrabbit_url_builder import StudentInfo

        student_name = None
        student_age = None
        student_gender = None
        class_id = None

        # Patterns for bot questions (assistant messages)
        swimmer_q = re.compile(
            r'who.{0,20}(?:swim|lesson|taking|enroll|sign.?up)|'
            r'(?:swimmer|student|child).{0,10}name|'
            r'what.{0,15}(?:their|her|his)\s+name',
            re.IGNORECASE,
        )
        age_q = re.compile(
            r'how old|(?:what|their).{0,10}age|date of birth|birthday',
            re.IGNORECASE,
        )
        gender_q = re.compile(
            r'boy or.{0,5}girl|gender|son or.{0,5}daughter',
            re.IGNORECASE,
        )

        # Patterns for user answers
        age_answer = re.compile(r'\b(\d{1,2})\b')
        gender_male = re.compile(r'\b(?:boy|son|male|he|him)\b', re.IGNORECASE)
        gender_female = re.compile(r'\b(?:girl|daughter|female|she|her)\b', re.IGNORECASE)
        class_id_pattern = re.compile(r'class_id=(\d+)')

        # Scan Q&A pairs: bot asks question, user answers in next message
        for i, msg in enumerate(messages):
            content = msg.content or ""

            # Extract class_id from any message (bot includes it in schedule)
            cid_matches = class_id_pattern.findall(content)
            if cid_matches:
                class_id = cid_matches[-1]

            # Detect gender from user messages (even without a direct question)
            if msg.role == "user":
                if not student_gender:
                    if gender_female.search(content):
                        student_gender = "F"
                    elif gender_male.search(content):
                        student_gender = "M"

            # Look for bot question → user answer pairs
            if msg.role != "assistant":
                continue

            # Find the next user message after this bot message
            next_user = None
            for j in range(i + 1, len(messages)):
                if messages[j].role == "user":
                    next_user = messages[j].content or ""
                    break

            if not next_user:
                continue

            # Bot asked about swimmer → user's answer is the swimmer's name
            if swimmer_q.search(content) and not student_name:
                # Clean up: skip common non-name responses
                answer = next_user.strip()
                skip_words = {
                    "my child", "my kid", "my son", "my daughter",
                    "my kids", "my children", "myself", "me",
                    "yes", "no", "ok", "sure",
                }
                if answer.lower() not in skip_words and len(answer) < 50:
                    # If they say "my daughter Emily" or "my son Jake"
                    name_after_relation = re.search(
                        r'(?:my\s+(?:daughter|son|child|kid)[,\s]+)(\w+)',
                        answer, re.IGNORECASE,
                    )
                    if name_after_relation:
                        student_name = name_after_relation.group(1).title()
                    elif not re.search(r'^my\s+', answer, re.IGNORECASE):
                        # Just a name like "Emily"
                        words = answer.split()
                        if 1 <= len(words) <= 3:
                            student_name = words[0].title()
                    logger.debug(f"Student name extracted: {student_name} from '{answer}'")

            # Bot asked about age → extract number from user's answer
            if age_q.search(content) and not student_age:
                age_match = age_answer.search(next_user)
                if age_match:
                    age_val = int(age_match.group(1))
                    if 0 < age_val < 100:
                        student_age = age_val
                        logger.debug(f"Student age extracted: {student_age}")

            # Bot asked about gender → extract from user's answer
            if gender_q.search(content) and not student_gender:
                if gender_female.search(next_user):
                    student_gender = "F"
                elif gender_male.search(next_user):
                    student_gender = "M"

        # Build StudentInfo if we found a student
        students = []
        if student_name:
            birth_date = None
            if student_age:
                try:
                    today = date.today()
                    approx_birth = today.replace(year=today.year - student_age)
                    birth_date = approx_birth.strftime("%m/%d/%Y")
                except (ValueError, OverflowError):
                    pass
            students.append(StudentInfo(
                first_name=student_name,
                gender=student_gender,
                birth_date=birth_date,
            ))

        logger.info(
            f"Student extraction (pattern): {len(students)} student(s), "
            f"names={[s.first_name for s in students]}, "
            f"age={student_age}, gender={student_gender}, class_id={class_id}"
        )
        return (students, class_id)

    async def _process_chat_core(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        messages: list[Message],
        system_prompt_method,
        prompt_context: dict | None = None,
        additional_context: str | None = None,
    ) -> tuple[str, float]:
        """Core chat processing logic (reusable for web and SMS).
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            user_message: User's message
            messages: Previous messages in conversation
            system_prompt_method: Method to get system prompt (compose_prompt, compose_prompt_chat, or compose_prompt_sms)
            prompt_context: Optional context dict to pass to prompt method (e.g., contact info status)
            additional_context: Additional context to add to prompt
            
        Returns:
            Tuple of (llm_response, llm_latency_ms)
            
        Raises:
            ValueError: If no prompt is configured for the tenant
        """
        # Assemble prompt with conversation history
        if prompt_context:
            system_prompt = await system_prompt_method(tenant_id, prompt_context)
        else:
            system_prompt = await system_prompt_method(tenant_id)
        
        # Check if prompt is configured
        if system_prompt is None:
            raise ValueError(
                "No prompt configured for this tenant. "
                "Please configure a prompt before using the chatbot."
            )
        
        # Build conversation context for LLM
        conversation_context = self._build_conversation_context(
            system_prompt, messages, user_message, additional_context
        )

        # Call LLM
        llm_start = time.time()
        try:
            llm_response = await self.llm_orchestrator.generate(
                conversation_context,
                context={"temperature": 0.3, "max_tokens": settings.chat_max_tokens},
            )
            # Clean up response - remove any "Draft X:" prefixes that LLM might add
            llm_response = self._clean_llm_response(llm_response)
            if self._response_needs_completion(llm_response):
                llm_response = await self._complete_response(llm_response)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            llm_response = "I apologize, but I'm having trouble processing your request right now. Please try again in a moment."

        llm_latency_ms = (time.time() - llm_start) * 1000

        return llm_response, llm_latency_ms

    def _clean_llm_response(self, response: str) -> str:
        """Clean up LLM response by removing unwanted prefixes and formatting.

        Args:
            response: Raw LLM response

        Returns:
            Cleaned response
        """
        if not response:
            return response

        # Strip whitespace
        cleaned = response.strip()

        # Remove "Draft X:" prefix (case insensitive)
        # Matches patterns like "Draft 1:", "draft 2:", "DRAFT 3:", etc.
        cleaned = _DRAFT_PREFIX_PATTERN.sub('', cleaned)

        # Fix URLs in the response (encode spaces, remove line breaks)
        cleaned = self._fix_urls_in_response(cleaned)

        return cleaned

    def _fix_urls_in_response(self, text: str) -> str:
        """Fix URLs in the response by joining split parts.

        This ensures URLs are not broken across lines or spaces. We intentionally
        do NOT re-encode URLs because the LLM is instructed to use pre-encoded
        type codes (e.g., Adult%20Level%203). Re-encoding would cause double-encoding.

        Args:
            text: Text that may contain URLs

        Returns:
            Text with fixed URLs (whitespace removed from within URLs)
        """
        if not text:
            return text

        fixed_text = text

        # First pass: Iteratively join URL parts split by ANY whitespace
        # Pattern: URL + whitespace + continuation starting with URL-like chars
        # Loop to handle multiple breaks in the same URL
        split_url_pattern = re.compile(
            r'(https?://\S+)(\s+)([.&?/][^\s<>"\']*)',
            re.IGNORECASE
        )

        max_iterations = 15  # Safety limit
        for _ in range(max_iterations):
            new_text = split_url_pattern.sub(r'\1\3', fixed_text)
            if new_text == fixed_text:
                break
            fixed_text = new_text

        # Second pass: Join URL + whitespace + path-like continuation
        # e.g., "https://site.com/cy" + " " + "press-spring" -> joined
        path_continuation_pattern = re.compile(
            r'(https?://[^\s<>"\']+/)(\s+)([a-zA-Z0-9][a-zA-Z0-9\-_]*)',
            re.IGNORECASE
        )

        for _ in range(max_iterations):
            new_text = path_continuation_pattern.sub(r'\1\3', fixed_text)
            if new_text == fixed_text:
                break
            fixed_text = new_text

        # Third pass: Remove any remaining embedded whitespace in BSS URLs
        # This is a final safety net for any whitespace we missed
        bss_url_pattern = re.compile(
            r'(https?://britishswimschool[^\s]*)',
            re.IGNORECASE
        )

        def clean_bss_url(match: re.Match) -> str:
            url = match.group(1)
            # Find where the URL ends (at a space followed by non-URL text)
            # and clean only the URL part
            cleaned = re.sub(r'\s+', '', url)
            return cleaned

        fixed_text = bss_url_pattern.sub(clean_bss_url, fixed_text)

        return fixed_text

    def _response_needs_completion(self, response: str) -> bool:
        """Check if the response appears to be cut off mid-sentence."""
        if not response:
            return False

        trimmed = response.strip()
        if trimmed.endswith((".", "!", "?")):
            return False

        trimmed = trimmed.rstrip(')"\'')
        if trimmed.endswith((".", "!", "?")):
            return False

        if trimmed.endswith((",", ":", ";", "-")):
            return True

        match = _TRAILING_WORD_PATTERN.search(trimmed)
        if not match:
            return False

        dangling_words = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "because",
            "so",
            "with",
            "for",
            "to",
            "of",
            "in",
            "per",
            "each",
            "every",
            "about",
            "around",
            "between",
            "during",
            "before",
            "after",
            "into",
            "over",
            "under",
            "until",
            "at",
            "on",
            "from",
            "by",
            "as",
        }
        if match.group(1).lower() in dangling_words:
            return True

        if len(trimmed) >= 80 and _LOWERCASE_ENDING_PATTERN.search(trimmed):
            return True

        return False

    async def _complete_response(self, response: str) -> str:
        """Ask the LLM to finish a cut-off response in a short continuation."""
        completion_prompt = (
            "The assistant response was cut off mid-sentence.\n"
            f"Response so far: \"{response}\"\n\n"
            "Continue and finish the thought in one short sentence. "
            "Only provide the continuation text, no repetition."
        )

        try:
            continuation = await self.llm_orchestrator.generate(
                completion_prompt,
                context={"temperature": 0.2, "max_tokens": 150},
            )
        except Exception as e:
            logger.warning(f"Failed to complete response: {e}")
            return response

        continuation = (continuation or "").strip()
        if not continuation:
            return response

        return f"{response.rstrip()} {continuation.lstrip()}".strip()

    async def _replace_bss_urls_with_jackrabbit(
        self,
        tenant_id: int,
        conversation_id: int,
        response: str,
        phone: str | None,
        name: str | None,
        messages: list[Message] | None = None,
        current_user_message: str | None = None,
    ) -> tuple[str, str | None, list | None, str | None]:
        """Replace basic BSS registration URLs with Jackrabbit pre-filled URLs.

        For BSS (tenant 3), the bot is instructed to use basic britishswimschool.com URLs
        in its prompts, but we want to send Jackrabbit pre-filled URLs to users for a
        better experience when we have customer info. If we don't have any customer info,
        we keep the basic BSS URL.

        Args:
            tenant_id: Tenant ID (should be 3 for BSS)
            conversation_id: Conversation ID
            response: Bot's response text
            phone: User's phone number (if available)
            name: User's name (if available)
            messages: Conversation messages for student info extraction
            current_user_message: The current turn's user message (not yet in messages list)

        Returns:
            Tuple of (response, enriched_name, students, class_id) — enriched data
            is also returned so promise fulfillment can use the same data.
        """
        _empty = (response, None, None, None)

        # Only process for tenant 3 (BSS)
        if tenant_id != 3:
            return _empty

        # Pattern to match BSS registration URLs
        bss_url_pattern = re.compile(
            r'https?://britishswimschool\.com/cypress-spring/register/\?[^\s<>"\']+',
            re.IGNORECASE
        )

        # Check if response contains a BSS registration URL
        bss_match = bss_url_pattern.search(response)
        if not bss_match:
            return _empty

        # Extract class_id from the BSS URL if the bot included it
        # (the LLM has class schedule data with class_id=XXXXX in its context)
        url_class_id = None
        cid_match = re.search(r'class_id=(\d+)', bss_match.group(0))
        if cid_match:
            url_class_id = cid_match.group(1)
            logger.info(f"Extracted class_id from BSS URL: {url_class_id}")

        try:
            # Get lead to extract customer info
            lead = await self.lead_service.get_lead_by_conversation(tenant_id, conversation_id)

            # Build customer info from lead or provided data
            from app.utils.jackrabbit_url_builder import CustomerInfo, build_jackrabbit_registration_url

            customer_info = CustomerInfo()
            has_customer_info = False

            if lead:
                if lead.name:
                    name_parts = lead.name.strip().split(maxsplit=1)
                    customer_info.first_name = name_parts[0] if name_parts else None
                    customer_info.last_name = name_parts[1] if len(name_parts) > 1 else None
                    has_customer_info = True
                if lead.email:
                    customer_info.email = lead.email
                    has_customer_info = True
                if lead.phone or phone:
                    customer_info.phone = lead.phone or phone
                    has_customer_info = True
            elif name or phone:
                # No lead yet, use provided data
                if name:
                    name_parts = name.strip().split(maxsplit=1)
                    customer_info.first_name = name_parts[0] if name_parts else None
                    customer_info.last_name = name_parts[1] if len(name_parts) > 1 else None
                    has_customer_info = True
                if phone:
                    customer_info.phone = phone
                    has_customer_info = True

            # Scan ALL user messages (including current turn) for phone/email/name
            # that may not be in the lead yet. The `messages` list was fetched before
            # the current user message was added, so we include it explicitly.
            if messages or current_user_message:
                parts = [
                    msg.content for msg in (messages or [])
                    if msg.role == "user" and msg.content
                ]
                if current_user_message:
                    parts.append(current_user_message)
                all_user_text = " ".join(parts)
                if not customer_info.phone:
                    regex_phone = self._extract_phone_regex(all_user_text)
                    if regex_phone:
                        customer_info.phone = regex_phone
                        has_customer_info = True
                        logger.info(f"Phone from message scan: {regex_phone}")
                if not customer_info.email:
                    regex_email = self._extract_email_regex(all_user_text)
                    if regex_email:
                        customer_info.email = regex_email
                        has_customer_info = True
                        logger.info(f"Email from message scan: {regex_email}")

                # Name augmentation: if we only have first name, look for last
                # name in conversation (user may provide it in a separate turn)
                if customer_info.first_name and not customer_info.last_name and messages:
                    for idx, msg in enumerate(messages):
                        if msg.role != "assistant" or not msg.content:
                            continue
                        asks_last_name = re.search(
                            r'last name|family name|surname',
                            msg.content, re.IGNORECASE,
                        )
                        if asks_last_name:
                            # Next user message is the last name — check messages first
                            found = False
                            for j in range(idx + 1, len(messages)):
                                if messages[j].role == "user" and messages[j].content:
                                    candidate = messages[j].content.strip()
                                    if 1 <= len(candidate.split()) <= 2 and len(candidate) < 30:
                                        customer_info.last_name = candidate.title()
                                        found = True
                                        logger.info(f"Last name from message scan: {customer_info.last_name}")
                                    break
                            # If bot asked last name in the LAST message and user
                            # just replied, the answer is in current_user_message
                            if not found and idx == len(messages) - 1 and current_user_message:
                                candidate = current_user_message.strip()
                                if 1 <= len(candidate.split()) <= 2 and len(candidate) < 30:
                                    customer_info.last_name = candidate.title()
                                    logger.info(f"Last name from current message: {customer_info.last_name}")

            # Only replace with Jackrabbit URL if we have at least some customer info
            # Otherwise keep the basic BSS URL so they can fill it out themselves
            if not has_customer_info:
                logger.info(
                    f"No customer info available, keeping basic BSS URL - "
                    f"tenant_id={tenant_id}, conversation_id={conversation_id}"
                )
                return _empty

            # Extract student/swimmer info and class selection from conversation
            students = []
            class_id = None
            if messages:
                try:
                    students, class_id = self._extract_student_info_from_conversation(
                        messages
                    )
                except Exception as e:
                    logger.warning(f"Student info extraction failed, continuing without: {e}")

            # Build Jackrabbit URL with customer + student prefill
            # Prefer class_id from the BSS URL (bot's current response) over message scan
            final_class_id = url_class_id or class_id
            jackrabbit_url = build_jackrabbit_registration_url(
                customer=customer_info,
                students=students or None,
                class_id=final_class_id,
            )

            # Replace all BSS URLs with the Jackrabbit URL
            updated_response = bss_url_pattern.sub(jackrabbit_url, response)

            # Build enriched name string for downstream (promise fulfillment)
            enriched_name = None
            if customer_info.first_name:
                parts = [customer_info.first_name]
                if customer_info.last_name:
                    parts.append(customer_info.last_name)
                enriched_name = " ".join(parts)

            logger.info(
                f"Replaced BSS URL with Jackrabbit URL in chat response - "
                f"tenant_id={tenant_id}, conversation_id={conversation_id}, "
                f"has_name={bool(customer_info.first_name)}, has_email={bool(customer_info.email)}, "
                f"has_phone={bool(customer_info.phone)}, "
                f"students={len(students)}, class_id={final_class_id} (url={url_class_id}, scan={class_id})"
            )

            return (updated_response, enriched_name, students, final_class_id)

        except Exception as e:
            logger.error(
                f"Failed to replace BSS URL with Jackrabbit URL: {e}",
                exc_info=True
            )
            # Return original response if replacement fails
            return _empty
