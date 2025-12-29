"""SMS service for customer service flow."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.compliance_handler import ComplianceHandler
from app.domain.services.customer_lookup_service import CustomerLookupService
from app.domain.services.customer_service_agent import CustomerServiceAgent
from app.domain.services.opt_in_service import OptInService
from app.domain.services.sms_service import SmsService
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository

logger = logging.getLogger(__name__)


@dataclass
class CustomerServiceSmsResult:
    """Result of customer service SMS processing."""
    response_message: str
    customer_type: str  # "existing", "lead", "unknown"
    message_sid: str | None = None
    jackrabbit_customer_id: str | None = None
    routed_to_lead_capture: bool = False


class CustomerServiceSmsService:
    """SMS service specifically for customer service flow."""

    # SMS constraints
    MAX_SMS_LENGTH = 1600  # For concatenated messages

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lookup_service = CustomerLookupService(session)
        self.customer_agent = CustomerServiceAgent(session)
        self.sms_service = SmsService(session)  # Fallback for lead capture
        self.compliance_handler = ComplianceHandler()
        self.opt_in_service = OptInService(session)
        self.config_repo = CustomerServiceConfigRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.telephony_factory = TelephonyProviderFactory(session)

    async def process_inbound_sms(
        self,
        tenant_id: int,
        phone_number: str,
        message_body: str,
        twilio_message_sid: str | None = None,
    ) -> CustomerServiceSmsResult:
        """Process inbound SMS through customer service flow.

        1. Check if customer service is enabled for tenant
        2. Check compliance (STOP/HELP)
        3. Look up customer in Jackrabbit via Zapier
        4. If customer found: route to CustomerServiceAgent
        5. If not found: route to existing lead capture flow

        Args:
            tenant_id: Tenant ID
            phone_number: Sender phone number
            message_body: Message text
            twilio_message_sid: Twilio message SID

        Returns:
            CustomerServiceSmsResult with response
        """
        # Check if customer service is enabled
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.is_enabled:
            # Fall back to regular SMS service
            logger.info(
                f"Customer service not enabled, routing to lead capture",
                extra={"tenant_id": tenant_id},
            )
            sms_result = await self.sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=phone_number,
                message_body=message_body,
                twilio_message_sid=twilio_message_sid,
            )
            return CustomerServiceSmsResult(
                response_message=sms_result.response_message,
                message_sid=sms_result.message_sid,
                customer_type="lead",
                routed_to_lead_capture=True,
            )

        # Check SMS routing is enabled
        routing_rules = config.routing_rules or {}
        if not routing_rules.get("enable_sms", True):
            # SMS not enabled for customer service, use regular flow
            sms_result = await self.sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=phone_number,
                message_body=message_body,
                twilio_message_sid=twilio_message_sid,
            )
            return CustomerServiceSmsResult(
                response_message=sms_result.response_message,
                message_sid=sms_result.message_sid,
                customer_type="lead",
                routed_to_lead_capture=True,
            )

        # Check compliance (STOP, HELP, etc.)
        compliance_result = self.compliance_handler.check_compliance(message_body)
        if compliance_result.action == "stop":
            await self.opt_in_service.opt_out(tenant_id, phone_number, method="STOP")
            return CustomerServiceSmsResult(
                response_message=compliance_result.response_message or "You have been unsubscribed.",
                customer_type="unknown",
            )
        if compliance_result.action == "opt_in":
            await self.opt_in_service.opt_in(tenant_id, phone_number, method="keyword")
            return CustomerServiceSmsResult(
                response_message=compliance_result.response_message or "You have been subscribed.",
                customer_type="unknown",
            )
        if compliance_result.action == "help":
            return CustomerServiceSmsResult(
                response_message=compliance_result.response_message or "Reply STOP to unsubscribe.",
                customer_type="unknown",
            )

        # Get or create conversation for context
        conversation = await self._get_or_create_conversation(
            tenant_id=tenant_id,
            phone_number=phone_number,
        )

        # Store user message
        await self._add_message(conversation, "user", message_body, twilio_message_sid)

        # Look up customer in Jackrabbit
        lookup_result = await self.lookup_service.lookup_by_phone(
            tenant_id=tenant_id,
            phone_number=phone_number,
            conversation_id=conversation.id,
        )

        if not lookup_result.found:
            # Customer not found - route to lead capture or handle gracefully
            if routing_rules.get("fallback_to_lead_capture", True):
                logger.info(
                    f"Customer not found, routing to lead capture",
                    extra={
                        "tenant_id": tenant_id,
                        "phone": phone_number,
                        "lookup_time_ms": lookup_result.lookup_time_ms,
                    },
                )
                sms_result = await self.sms_service.process_inbound_sms(
                    tenant_id=tenant_id,
                    phone_number=phone_number,
                    message_body=message_body,
                    twilio_message_sid=twilio_message_sid,
                )
                return CustomerServiceSmsResult(
                    response_message=sms_result.response_message,
                    message_sid=sms_result.message_sid,
                    customer_type="lead",
                    routed_to_lead_capture=True,
                )
            else:
                # No lead capture fallback - send generic message
                response = "I couldn't find your account. Please contact us directly for assistance."
                await self._add_message(conversation, "assistant", response)
                message_sid = await self._send_sms(tenant_id, phone_number, response)
                return CustomerServiceSmsResult(
                    response_message=response,
                    message_sid=message_sid,
                    customer_type="unknown",
                )

        # Customer found - process through CustomerServiceAgent
        customer = lookup_result.jackrabbit_customer
        logger.info(
            f"Customer found, processing inquiry",
            extra={
                "tenant_id": tenant_id,
                "phone": phone_number,
                "jackrabbit_id": customer.jackrabbit_id,
                "from_cache": lookup_result.from_cache,
            },
        )

        # Process inquiry
        agent_result = await self.customer_agent.process_inquiry(
            tenant_id=tenant_id,
            jackrabbit_customer=customer,
            user_message=message_body,
            conversation_id=conversation.id,
            channel="sms",
        )

        # Truncate response for SMS if needed
        response = self._truncate_for_sms(agent_result.response_message)

        # Store response
        await self._add_message(conversation, "assistant", response)

        # Send SMS
        message_sid = await self._send_sms(tenant_id, phone_number, response)

        logger.info(
            f"Customer service response sent",
            extra={
                "tenant_id": tenant_id,
                "phone": phone_number,
                "jackrabbit_id": customer.jackrabbit_id,
                "source": agent_result.source,
                "latency_ms": agent_result.latency_ms,
            },
        )

        return CustomerServiceSmsResult(
            response_message=response,
            message_sid=message_sid,
            customer_type="existing",
            jackrabbit_customer_id=customer.jackrabbit_id,
        )

    async def _get_or_create_conversation(
        self,
        tenant_id: int,
        phone_number: str,
    ) -> Conversation:
        """Get or create SMS conversation for phone number.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number

        Returns:
            Conversation
        """
        # Try to find existing conversation
        conversation = await self.conversation_repo.get_by_phone_number(
            tenant_id, phone_number, channel="sms"
        )

        if conversation:
            return conversation

        # Create new conversation
        conversation = Conversation(
            tenant_id=tenant_id,
            phone_number=phone_number,
            channel="sms",
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
        twilio_sid: str | None = None,
    ) -> Message:
        """Add message to conversation.

        Args:
            conversation: Conversation
            role: Message role (user/assistant)
            content: Message content
            twilio_sid: Optional Twilio message SID

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
            metadata={"twilio_message_sid": twilio_sid} if twilio_sid else None,
        )
        self.session.add(message)
        await self.session.commit()
        return message

    async def _send_sms(
        self,
        tenant_id: int,
        to_number: str,
        message: str,
    ) -> str | None:
        """Send SMS response.

        Args:
            tenant_id: Tenant ID
            to_number: Recipient phone number
            message: Message content

        Returns:
            Message SID or None if failed
        """
        try:
            provider = await self.telephony_factory.get_sms_provider(tenant_id)
            if not provider:
                logger.error(f"No SMS provider for tenant {tenant_id}")
                return None

            config = await self.telephony_factory.get_config(tenant_id)
            if not config:
                return None

            from_number = config.twilio_phone_number or config.telnyx_phone_number
            if not from_number:
                logger.error(f"No phone number configured for tenant {tenant_id}")
                return None

            result = await provider.send_sms(
                to=to_number,
                from_=from_number,
                body=message,
            )

            return result.message_sid if result.success else None

        except Exception as e:
            logger.exception(f"Failed to send SMS: {e}")
            return None

    def _truncate_for_sms(self, message: str) -> str:
        """Truncate message for SMS if needed.

        Args:
            message: Full message

        Returns:
            Truncated message
        """
        if len(message) <= self.MAX_SMS_LENGTH:
            return message

        # Truncate and add ellipsis
        return message[: self.MAX_SMS_LENGTH - 3] + "..."
