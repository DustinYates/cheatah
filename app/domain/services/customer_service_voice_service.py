"""Voice service for customer service flow."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.customer_lookup_service import CustomerLookupService
from app.domain.services.customer_service_agent import CustomerServiceAgent
from app.domain.services.handoff_service import HandoffService
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository
from app.persistence.repositories.tenant_repository import TenantRepository

logger = logging.getLogger(__name__)


@dataclass
class CustomerServiceVoiceResult:
    """Result of customer service voice processing."""
    response_text: str
    customer_type: str  # "existing", "lead", "unknown"
    twiml: str | None = None
    jackrabbit_customer_id: str | None = None
    requires_escalation: bool = False
    routed_to_lead_capture: bool = False


class CustomerServiceVoiceService:
    """Voice service specifically for customer service flow."""

    # Voice response constraints
    MAX_RESPONSE_CHARS = 350  # Keep TTS short
    MAX_RESPONSE_SENTENCES = 3

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lookup_service = CustomerLookupService(session)
        self.customer_agent = CustomerServiceAgent(session)
        self.handoff_service = HandoffService(session)
        self.config_repo = CustomerServiceConfigRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.tenant_repo = TenantRepository(session)

    async def handle_inbound_call(
        self,
        tenant_id: int,
        call_sid: str,
        from_number: str,
    ) -> CustomerServiceVoiceResult:
        """Handle initial inbound call - identify customer and generate greeting.

        Args:
            tenant_id: Tenant ID
            call_sid: Twilio call SID
            from_number: Caller phone number

        Returns:
            CustomerServiceVoiceResult with greeting
        """
        # Check if customer service is enabled
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.is_enabled:
            return CustomerServiceVoiceResult(
                response_text="",
                customer_type="unknown",
                routed_to_lead_capture=True,
            )

        # Check voice routing is enabled
        routing_rules = config.routing_rules or {}
        if not routing_rules.get("enable_voice", True):
            return CustomerServiceVoiceResult(
                response_text="",
                customer_type="unknown",
                routed_to_lead_capture=True,
            )

        # Create conversation for the call
        conversation = await self._create_call_conversation(
            tenant_id=tenant_id,
            phone_number=from_number,
            call_sid=call_sid,
        )

        # Look up customer
        lookup_result = await self.lookup_service.lookup_by_phone(
            tenant_id=tenant_id,
            phone_number=from_number,
            conversation_id=conversation.id,
        )

        if not lookup_result.found:
            # Customer not found
            if routing_rules.get("fallback_to_lead_capture", True):
                return CustomerServiceVoiceResult(
                    response_text="",
                    customer_type="lead",
                    routed_to_lead_capture=True,
                )
            else:
                greeting = "Hello! I'm sorry, I couldn't find your account. Please hold while I connect you with a team member."
                return CustomerServiceVoiceResult(
                    response_text=greeting,
                    customer_type="unknown",
                    requires_escalation=True,
                )

        # Customer found - generate personalized greeting
        customer = lookup_result.jackrabbit_customer
        greeting = await self.generate_customer_greeting(tenant_id, customer)

        logger.info(
            f"Customer identified for call",
            extra={
                "tenant_id": tenant_id,
                "call_sid": call_sid,
                "jackrabbit_id": customer.jackrabbit_id,
                "from_cache": lookup_result.from_cache,
            },
        )

        # Store greeting as system message
        await self._add_message(conversation, "assistant", greeting)

        return CustomerServiceVoiceResult(
            response_text=greeting,
            customer_type="existing",
            jackrabbit_customer_id=customer.jackrabbit_id,
        )

    async def process_voice_turn(
        self,
        tenant_id: int,
        call_sid: str,
        from_number: str,
        conversation_id: int,
        transcribed_text: str,
        jackrabbit_customer: JackrabbitCustomer | None = None,
    ) -> CustomerServiceVoiceResult:
        """Process voice turn through customer service flow.

        Args:
            tenant_id: Tenant ID
            call_sid: Twilio call SID
            from_number: Caller phone number
            conversation_id: Conversation ID
            transcribed_text: Transcribed speech
            jackrabbit_customer: Pre-looked-up customer (from initial lookup)

        Returns:
            CustomerServiceVoiceResult with response
        """
        # Get customer if not provided
        if not jackrabbit_customer:
            lookup_result = await self.lookup_service.lookup_by_phone(
                tenant_id=tenant_id,
                phone_number=from_number,
                use_cache=True,
                conversation_id=conversation_id,
            )
            if not lookup_result.found:
                return CustomerServiceVoiceResult(
                    response_text="I'm sorry, I couldn't find your account information.",
                    customer_type="unknown",
                    requires_escalation=True,
                )
            jackrabbit_customer = lookup_result.jackrabbit_customer

        # Get conversation
        conversation = await self.conversation_repo.get_by_id(tenant_id, conversation_id)
        if not conversation:
            logger.error(f"Conversation {conversation_id} not found")
            return CustomerServiceVoiceResult(
                response_text="I'm sorry, there was an error. Please try again.",
                customer_type="existing",
                jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
            )

        # Store user message
        await self._add_message(conversation, "user", transcribed_text)

        # Check for escalation requests
        if self._is_escalation_request(transcribed_text):
            response = "Of course, I'll connect you with a team member right away. Please hold."
            await self._add_message(conversation, "assistant", response)
            return CustomerServiceVoiceResult(
                response_text=response,
                customer_type="existing",
                jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
                requires_escalation=True,
            )

        # Process through customer service agent
        agent_result = await self.customer_agent.process_inquiry(
            tenant_id=tenant_id,
            jackrabbit_customer=jackrabbit_customer,
            user_message=transcribed_text,
            conversation_id=conversation_id,
            channel="voice",
        )

        # Format response for voice
        response = self._format_for_voice(agent_result.response_message)

        # Store response
        await self._add_message(conversation, "assistant", response)

        logger.info(
            f"Customer service voice response",
            extra={
                "tenant_id": tenant_id,
                "call_sid": call_sid,
                "jackrabbit_id": jackrabbit_customer.jackrabbit_id,
                "source": agent_result.source,
                "latency_ms": agent_result.latency_ms,
            },
        )

        return CustomerServiceVoiceResult(
            response_text=response,
            customer_type="existing",
            jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
        )

    async def generate_customer_greeting(
        self,
        tenant_id: int,
        customer: JackrabbitCustomer,
    ) -> str:
        """Generate personalized greeting for known customer.

        Args:
            tenant_id: Tenant ID
            customer: Jackrabbit customer

        Returns:
            Greeting text
        """
        # Get business name from tenant
        tenant = await self.tenant_repo.get_by_id(None, tenant_id)
        business_name = tenant.name if tenant else "our team"

        customer_name = customer.name or "valued customer"

        # Build personalized greeting
        greeting = f"Hello {customer_name}! Thank you for calling {business_name}. How can I help you today?"

        return greeting

    async def _create_call_conversation(
        self,
        tenant_id: int,
        phone_number: str,
        call_sid: str,
    ) -> Conversation:
        """Create conversation for voice call.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            call_sid: Call SID

        Returns:
            Created conversation
        """
        conversation = Conversation(
            tenant_id=tenant_id,
            phone_number=phone_number,
            channel="voice",
            external_id=call_sid,
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def _add_message(
        self,
        conversation: Conversation,
        role: str,
        content: str,
    ) -> Message:
        """Add message to conversation.

        Args:
            conversation: Conversation
            role: Message role
            content: Message content

        Returns:
            Created message
        """
        # Get next sequence number
        sequence = len(conversation.messages) + 1 if conversation.messages else 1

        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            sequence_number=sequence,
        )
        self.session.add(message)
        await self.session.commit()
        return message

    def _is_escalation_request(self, text: str) -> bool:
        """Check if user is requesting to speak to a human.

        Args:
            text: User's transcribed speech

        Returns:
            True if escalation requested
        """
        escalation_phrases = [
            "speak to a human",
            "speak to a person",
            "talk to someone",
            "real person",
            "representative",
            "operator",
            "agent",
            "manager",
            "supervisor",
            "transfer me",
            "live person",
        ]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in escalation_phrases)

    def _format_for_voice(self, text: str) -> str:
        """Format response for voice TTS.

        Keep responses short and conversational for better TTS.

        Args:
            text: Full response text

        Returns:
            Formatted response
        """
        # Truncate if too long
        if len(text) > self.MAX_RESPONSE_CHARS:
            # Try to break at sentence boundary
            sentences = text.split(". ")
            result = []
            total_len = 0

            for i, sentence in enumerate(sentences):
                if i >= self.MAX_RESPONSE_SENTENCES:
                    break
                if total_len + len(sentence) > self.MAX_RESPONSE_CHARS:
                    break
                result.append(sentence)
                total_len += len(sentence) + 2  # +2 for ". "

            if result:
                text = ". ".join(result)
                if not text.endswith("."):
                    text += "."
            else:
                # Just truncate
                text = text[: self.MAX_RESPONSE_CHARS - 3] + "..."

        return text
