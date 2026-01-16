"""Chat service for processing web chat requests."""

import json
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.conversation_service import ConversationService
from app.domain.services.escalation_service import EscalationService
from app.domain.services.lead_service import LeadService
from app.domain.services.contact_service import ContactService
from app.domain.services.promise_detector import PromiseDetector, DetectedPromise
from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
from app.domain.services.user_request_detector import UserRequestDetector
from app.domain.services.prompt_service import PromptService
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from app.utils.name_validator import validate_name, extract_name_from_explicit_statement
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.tenant_repository import TenantRepository
from app.settings import settings

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for better performance
# These are compiled once at module load instead of on each function call
_EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.IGNORECASE)
_PHONE_PATTERN = re.compile(r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})')
_EXPLICIT_NAME_PATTERN = re.compile(r"\b(?:I'?m|I am|my name is|this is|im|name's|call me|it's|its)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", re.IGNORECASE)
_CAPITALIZED_NAME_PATTERN = re.compile(r"([A-Z][a-z]+\s+[A-Z][a-z]+)")
_DRAFT_PREFIX_PATTERN = re.compile(r'^draft\s+\d+:\s*', re.IGNORECASE)
_TRAILING_WORD_PATTERN = re.compile(r"([A-Za-z]+)$")
_LOWERCASE_ENDING_PATTERN = re.compile(r"[a-z]$")


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
        self.prompt_service = PromptService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.tenant_repo = TenantRepository(session)

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
        collected_name = False
        collected_email = False
        collected_phone = False
        
        if existing_lead:
            collected_name = bool(existing_lead.name)
            collected_email = bool(existing_lead.email)
            collected_phone = bool(existing_lead.phone)
        elif lead_captured:
            # Just captured in this turn
            if user_name:
                collected_name = True
            if user_email:
                collected_email = True
            if user_phone:
                collected_phone = True
        
        # Determine if we should suggest collecting contact info
        # (but let the prompt handle it naturally, not with hardcoded messages)
        # DISABLED: Contact form popup feature disabled per user request
        # Code preserved for future use but never triggered
        requires_contact_info = False
        # Legacy logic (disabled):
        # if not (collected_email or collected_phone) and turn_count >= self.FOLLOW_UP_NUDGE_TURN:
        #     requires_contact_info = True
        
        # Build prompt context with contact info status
        prompt_context = {
            "collected_name": collected_name,
            "collected_email": collected_email,
            "collected_phone": collected_phone,
            "turn_count": turn_count,
        }
        
        # Use core chat processing logic with chat-specific prompt method
        llm_response, llm_latency_ms = await self._process_chat_core(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=user_message,
            messages=messages,
            system_prompt_method=self.prompt_service.compose_prompt_chat,
            prompt_context=prompt_context,
        )

        # Add assistant response
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "assistant", llm_response
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
        
        # Extract contact info from conversation messages
        extracted_info = await self._extract_contact_info_from_conversation(
            messages, user_message
        )
        
        logger.debug(
            f"Extracted contact info: name={extracted_info.get('name')}, "
            f"email={extracted_info.get('email')}, phone={extracted_info.get('phone')}"
        )
        
        extracted_name = extracted_info.get("name")
        extracted_email = extracted_info.get("email")
        extracted_phone = extracted_info.get("phone")
        name_is_explicit = extracted_info.get("name_is_explicit", False)

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

        # Check for user requests and AI promises to send information (registration links, schedules, etc.)
        # Get phone number from user input, extracted info, or existing lead
        customer_phone = (
            user_phone
            or extracted_phone
            or (existing_lead.phone if existing_lead else None)
        )
        customer_name = (
            user_name
            or extracted_name
            or (existing_lead.name if existing_lead else None)
        )

        if customer_phone:
            # Import qualification validator for registration link validation
            from app.domain.services.registration_qualification_validator import (
                RegistrationQualificationValidator,
            )
            qualification_validator = RegistrationQualificationValidator(self.session)

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
            else:
                # Check for AI promises to send information
                promise = self.promise_detector.detect_promise(llm_response)
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
                    else:
                        # For registration links, validate qualification first
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
                                # Fulfill the promise immediately (send SMS with promised content)
                                fulfillment_result = await self.promise_fulfillment_service.fulfill_promise(
                                    tenant_id=tenant_id,
                                    conversation_id=conversation.id,
                                    promise=promise,
                                    phone=customer_phone,
                                    name=customer_name,
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

        # No hardcoded contact info nudge - let the LLM handle it naturally through the prompt
        final_response = llm_response

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
        }

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
                words = name.lower().split()
                if not (words[0] in common_words and words[1] in common_words):
                    return (name, False)  # False = not an explicit introduction

        return (None, False)

    async def _extract_contact_info_from_conversation(
        self,
        messages: list[Message],
        current_user_message: str,
    ) -> dict[str, str | None | bool]:
        """Extract contact information from conversation messages using LLM with regex fallback.

        Args:
            messages: Previous messages in conversation
            current_user_message: Current user message

        Returns:
            Dictionary with 'name', 'email', 'phone' keys (values may be None),
            and 'name_is_explicit' bool indicating if name came from explicit introduction
        """
        # First, try regex extraction from the current message as a quick fallback
        all_text = current_user_message
        for msg in messages:
            if msg.role == "user":
                all_text += " " + msg.content

        regex_email = self._extract_email_regex(all_text)
        regex_phone = self._extract_phone_regex(all_text)
        regex_name, name_is_explicit = self._extract_name_regex(all_text)
        
        logger.debug(
            f"Regex extraction results - name={regex_name}, email={regex_email}, phone={regex_phone}"
        )
        
        # Build conversation text for LLM extraction
        # Include BOTH user and assistant messages for context
        # This is critical for name extraction - the LLM needs to see that
        # the bot asked "what is your name?" to know that "chuck" is a name
        conversation_text = []
        for msg in messages:
            if msg.role == "user":
                conversation_text.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                conversation_text.append(f"Assistant: {msg.content}")
        conversation_text.append(f"User: {current_user_message}")
        
        # Limit to recent messages to avoid large prompts
        # Increased limit since we now include both user and assistant messages
        recent_messages = conversation_text[-15:]  # Last 15 messages (user + assistant)
        
        extraction_prompt = """Analyze the following conversation messages and extract any contact information the user has provided.

Conversation:
{}

Extract the following information if present:
- name: The user's full name or first name
- email: The user's email address
- phone: The user's phone number (any format)

NAME EXTRACTION RULES (IMPORTANT):
- Look for names in ALL these patterns:
  * Direct introductions: "I'm John", "my name is Sarah", "I am Mike", "this is Jane"
  * Casual introductions: "im ralph", "im John Anthony", "John here", "it's Sarah"
  * Names stated alone when asked: If asked "what's your name?" and they reply "John Anthony", extract "John Anthony"
  * Names in context: "You can call me Mike", "My friends call me Sam"
- Extract the COMPLETE name including first and last name if provided
- Do NOT extract business names, product names, or other non-person names
- If multiple names are mentioned, extract the most recent or most clearly stated one
- CRITICAL: Do NOT include pronouns (he, she, they, him, her, them) as part of the name!
  * If one message says "Ashley" and the next says "He loves to swim", the name is ONLY "Ashley", NOT "Ashley He"
  * Pronouns at the start of messages refer to someone being discussed, not the user's last name

GENERAL RULES:
- Only extract information explicitly stated by the user
- Do not make up or infer contact details
- Return null for any field not found

Respond with ONLY a valid JSON object in this exact format, no other text:
{{"name": null, "email": null, "phone": null}}""".format("\n".join(recent_messages))

        result = {"name": regex_name, "email": regex_email, "phone": regex_phone, "name_is_explicit": name_is_explicit}
        
        try:
            logger.debug(f"Attempting LLM extraction with prompt length: {len(extraction_prompt)}")
            response = await self.llm_orchestrator.generate(
                extraction_prompt,
                context={"temperature": 0.0, "max_tokens": 200},  # Very deterministic
            )
            
            logger.debug(f"LLM extraction response: {response[:200]}...")
            
            # Parse JSON response
            # Clean up response - sometimes LLM adds extra text
            response = response.strip()
            
            # Try to find JSON in response
            if response.startswith("{"):
                json_end = response.rfind("}") + 1
                response = response[:json_end]
            else:
                # Try to extract JSON from response
                start = response.find("{")
                end = response.rfind("}") + 1
                if start != -1 and end > start:
                    response = response[start:end]
                else:
                    logger.warning(f"Could not find JSON in LLM response: {response}")
                    # Use regex results as fallback
                    return result
            
            extracted = json.loads(response)
            
            # Merge LLM results with regex fallback (LLM takes precedence for name)
            llm_name = extracted.get("name")
            llm_email = extracted.get("email")
            llm_phone = extracted.get("phone")

            # If LLM found a name, it's ALWAYS considered explicit because the LLM
            # only extracts names when users clearly state their name in conversation.
            # This allows LLM-extracted names to override previously captured (possibly
            # incorrect) names like generic placeholders or misextracted text.
            final_name = llm_name if llm_name and llm_name != "null" else regex_name
            # Always mark LLM-extracted names as explicit to allow name updates
            final_name_is_explicit = True if (llm_name and llm_name != "null") else name_is_explicit

            logger.info(
                f"Name extraction result: llm_name={llm_name}, regex_name={regex_name}, "
                f"final_name={final_name}, is_explicit={final_name_is_explicit}"
            )

            result = {
                "name": final_name,
                "email": llm_email if llm_email and llm_email != "null" else regex_email,
                "phone": llm_phone if llm_phone and llm_phone != "null" else regex_phone,
                "name_is_explicit": final_name_is_explicit,
            }
            
            # Clean up empty strings (skip boolean fields)
            for key in ['name', 'email', 'phone']:
                if result[key] == "" or result[key] == "null":
                    result[key] = None

            # Validate the extracted name using strict validation
            if result["name"]:
                validated_name = validate_name(
                    result["name"],
                    require_explicit=result.get("name_is_explicit", False)
                )
                if validated_name != result["name"]:
                    logger.info(
                        f"Name validation changed: '{result['name']}' -> '{validated_name}'"
                    )
                result["name"] = validated_name

            logger.debug(f"Final extracted contact info: {result}")
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse contact extraction response: {e}, response: {response[:200]}"
            )
            # Validate regex result before returning as fallback
            if result["name"]:
                result["name"] = validate_name(
                    result["name"],
                    require_explicit=result.get("name_is_explicit", False)
                )
            return result
        except Exception as e:
            logger.error(f"Contact extraction failed: {e}", exc_info=True)
            # Validate regex result before returning as fallback
            if result["name"]:
                result["name"] = validate_name(
                    result["name"],
                    require_explicit=result.get("name_is_explicit", False)
                )
            return result

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
        """Fix URLs in the response by encoding spaces and removing line breaks.

        This ensures all URLs are properly formatted and clickable.

        Args:
            text: Text that may contain URLs

        Returns:
            Text with fixed URLs
        """
        if not text:
            return text

        # Pattern to find URLs (including incomplete ones that might span lines)
        # Matches http:// or https:// followed by any characters until whitespace or end
        url_pattern = re.compile(
            r'(https?://[^\s<>"\']+)',
            re.IGNORECASE
        )

        def fix_url(match: re.Match) -> str:
            url = match.group(1)

            # Remove any trailing punctuation that's not part of the URL
            trailing = ""
            while url and url[-1] in '.,;:!?)':
                # Keep trailing ) only if there's a matching ( in the URL
                if url[-1] == ')' and '(' in url:
                    break
                trailing = url[-1] + trailing
                url = url[:-1]

            try:
                # Parse the URL
                parsed = urlparse(url)

                # If there's a query string, properly encode it
                if parsed.query:
                    # Parse existing query params
                    # Note: parse_qs returns lists, we need to flatten them
                    params = parse_qs(parsed.query, keep_blank_values=True)

                    # Rebuild params, properly encoding values with spaces
                    fixed_params = {}
                    for key, values in params.items():
                        # Take the first value (query params shouldn't have multiple values here)
                        value = values[0] if values else ""
                        # The value might already be partially encoded or have spaces
                        # urlencode will handle encoding properly
                        fixed_params[key] = value

                    # Rebuild the URL with properly encoded query string
                    fixed_query = urlencode(fixed_params, safe='')
                    fixed_url = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        fixed_query,
                        parsed.fragment
                    ))
                    return fixed_url + trailing
                else:
                    # No query string, return as-is with trailing punctuation
                    return url + trailing

            except Exception as e:
                logger.warning(f"Failed to fix URL '{url}': {e}")
                return match.group(0)  # Return original if parsing fails

        # Apply URL fixing
        fixed_text = url_pattern.sub(fix_url, text)

        # Also check for URLs that might have line breaks in the middle
        # Pattern: URL followed by newline and continuation of URL-like content
        multiline_url_pattern = re.compile(
            r'(https?://\S+)\s*\n\s*([^\s<>"\']+(?:\S*))',
            re.IGNORECASE
        )

        def fix_multiline_url(match: re.Match) -> str:
            url_part1 = match.group(1).rstrip()
            url_part2 = match.group(2).strip()

            # Check if the second part looks like a URL continuation
            # (starts with query params or path segments)
            if url_part2.startswith(('&', '?', '/', '%')):
                # Rejoin the URL parts
                combined = url_part1 + url_part2
                # Process through the URL fixer
                return url_pattern.sub(fix_url, combined)

            # Not a continuation, return original with parts separated
            return match.group(0)

        fixed_text = multiline_url_pattern.sub(fix_multiline_url, fixed_text)

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
