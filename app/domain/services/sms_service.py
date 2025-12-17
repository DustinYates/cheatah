"""SMS service for processing SMS messages via Twilio."""

import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.chat_service import ChatService
from app.domain.services.compliance_handler import ComplianceHandler, ComplianceResult
from app.domain.services.escalation_service import EscalationService
from app.domain.services.intent_detector import IntentDetector
from app.domain.services.opt_in_service import OptInService
from app.domain.services.prompt_service import PromptService
from app.infrastructure.twilio_client import TwilioSmsClient
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.tenant_repository import TenantRepository


@dataclass
class SmsResult:
    """Result of SMS processing."""
    
    response_message: str
    message_sid: str | None = None
    requires_escalation: bool = False
    escalation_id: int | None = None
    opt_in_status_changed: bool = False


class SmsService:
    """Service for processing SMS messages."""

    # SMS constraints
    MAX_SMS_LENGTH = 160  # Standard SMS length
    MAX_SMS_LENGTH_LONG = 1600  # For concatenated messages

    def __init__(self, session: AsyncSession) -> None:
        """Initialize SMS service."""
        self.session = session
        self.chat_service = ChatService(session)
        self.compliance_handler = ComplianceHandler()
        self.intent_detector = IntentDetector()
        self.opt_in_service = OptInService(session)
        self.escalation_service = EscalationService(session)
        self.prompt_service = PromptService(session)
        self.tenant_repo = TenantRepository(session)
        self.conversation_repo = ConversationRepository(session)

    async def process_inbound_sms(
        self,
        tenant_id: int,
        phone_number: str,
        message_body: str,
        twilio_message_sid: str | None = None,
    ) -> SmsResult:
        """Process an inbound SMS message.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Sender phone number
            message_body: Message text
            twilio_message_sid: Twilio message SID (for audit trail)
            
        Returns:
            SmsResult with response and metadata
        """
        # Get tenant SMS config
        sms_config = await self._get_sms_config(tenant_id)
        if not sms_config or not sms_config.is_enabled:
            return SmsResult(
                response_message="SMS service is not enabled for this tenant.",
            )
        
        # Check compliance (STOP, HELP, etc.)
        compliance_result = self.compliance_handler.check_compliance(message_body)
        
        # Handle STOP keyword
        if compliance_result.action == "stop":
            await self.opt_in_service.opt_out(tenant_id, phone_number, method="STOP")
            return SmsResult(
                response_message=compliance_result.response_message or "You have been unsubscribed.",
                opt_in_status_changed=True,
            )
        
        # Handle OPT-IN keyword
        if compliance_result.action == "opt_in":
            await self.opt_in_service.opt_in(tenant_id, phone_number, method="keyword")
            return SmsResult(
                response_message=compliance_result.response_message or "You have been subscribed.",
                opt_in_status_changed=True,
            )
        
        # Check opt-in status
        is_opted_in = await self.opt_in_service.is_opted_in(tenant_id, phone_number)
        if not is_opted_in:
            return SmsResult(
                response_message=(
                    "You are not subscribed to receive messages. "
                    "Reply START to subscribe."
                ),
            )
        
        # Handle HELP keyword (return immediately, no LLM)
        if compliance_result.action == "help":
            return SmsResult(
                response_message=compliance_result.response_message or "How can we help you?",
            )
        
        # Check business hours (if enabled)
        if sms_config.business_hours_enabled:
            is_business_hours = await self._is_business_hours(sms_config)
            if not is_business_hours and sms_config.auto_reply_outside_hours:
                return SmsResult(
                    response_message=(
                        sms_config.auto_reply_message or
                        "We're currently outside business hours. We'll respond during business hours."
                    ),
                )
        
        # Get or create conversation
        conversation = await self._get_or_create_sms_conversation(
            tenant_id, phone_number
        )
        
        # Get conversation history
        from app.domain.services.conversation_service import ConversationService
        conversation_service = ConversationService(self.session)
        messages = await conversation_service.get_conversation_history(
            tenant_id, conversation.id
        )
        
        # Add user message with metadata
        user_message = await conversation_service.add_message(
            tenant_id, conversation.id, "user", message_body
        )
        
        # Add Twilio metadata to message
        if twilio_message_sid:
            user_message.message_metadata = {
                "twilio_message_sid": twilio_message_sid,
                "phone_number": phone_number,
            }
            await self.session.commit()
        
        # Detect intent
        intent_result = self.intent_detector.detect_intent(message_body)
        
        # Check for escalation
        escalation = await self.escalation_service.check_and_escalate(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=message_body,
            confidence_score=intent_result.confidence if intent_result.intent == "human_handoff" else None,
        )
        
        # If escalation created, return escalation message
        if escalation:
            return SmsResult(
                response_message=(
                    "Your request has been escalated to our team. "
                    "We'll get back to you shortly."
                ),
                requires_escalation=True,
                escalation_id=escalation.id,
            )
        
        # Process with LLM (reuse ChatService core logic)
        llm_response, llm_latency_ms = await self.chat_service._process_chat_core(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=message_body,
            messages=messages,
            system_prompt_method=self.prompt_service.compose_prompt_sms,
            requires_contact_info=False,  # SMS doesn't need contact info nudge
            additional_context=None,
        )
        
        # Format response for SMS (short, no markdown)
        formatted_response = self._format_sms_response(llm_response)
        
        # Add assistant response
        await conversation_service.add_message(
            tenant_id, conversation.id, "assistant", formatted_response
        )
        
        # Send response via Twilio
        twilio_client = TwilioSmsClient(
            account_sid=sms_config.twilio_account_sid,
            auth_token=sms_config.twilio_auth_token,
        )
        
        # Get webhook base URL from settings
        from app.settings import settings
        status_callback_url = None
        if settings.twilio_webhook_url_base:
            status_callback_url = f"{settings.twilio_webhook_url_base}/api/v1/sms/status"
        
        send_result = twilio_client.send_sms(
            to=phone_number,
            from_=sms_config.twilio_phone_number or "",
            body=formatted_response,
            status_callback=status_callback_url,
        )
        
        return SmsResult(
            response_message=formatted_response,
            message_sid=send_result.get("sid"),
        )

    async def _get_sms_config(self, tenant_id: int) -> TenantSmsConfig | None:
        """Get tenant SMS configuration.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            SMS config or None if not found
        """
        from sqlalchemy import select
        from app.persistence.models.tenant_sms_config import TenantSmsConfig
        
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_or_create_sms_conversation(
        self, tenant_id: int, phone_number: str
    ) -> Conversation:
        """Get or create SMS conversation.
        
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
        from app.domain.services.conversation_service import ConversationService
        conversation_service = ConversationService(self.session)
        conversation = await conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="sms",
            external_id=None,
        )
        # Set phone number
        conversation.phone_number = phone_number
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    def _format_sms_response(self, response: str) -> str:
        """Format response for SMS (remove markdown, shorten if needed).
        
        Args:
            response: LLM response
            
        Returns:
            Formatted SMS response
        """
        # Remove markdown formatting
        # Remove **bold**
        response = re.sub(r'\*\*(.+?)\*\*', r'\1', response)
        # Remove *italic*
        response = re.sub(r'\*(.+?)\*', r'\1', response)
        # Remove links [text](url) -> text
        response = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', response)
        # Remove markdown links
        response = re.sub(r'https?://[^\s]+', '', response)
        
        # Trim whitespace
        response = response.strip()
        
        # Split if too long (basic splitting)
        if len(response) > self.MAX_SMS_LENGTH:
            # Try to split at sentence boundaries
            sentences = re.split(r'([.!?]\s+)', response)
            parts = []
            current_part = ""
            
            for sentence in sentences:
                if len(current_part) + len(sentence) <= self.MAX_SMS_LENGTH:
                    current_part += sentence
                else:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = sentence
            
            if current_part:
                parts.append(current_part.strip())
            
            # If still too long, just truncate
            if len(parts) == 0 or len(parts[0]) > self.MAX_SMS_LENGTH:
                response = response[:self.MAX_SMS_LENGTH - 3] + "..."
            else:
                response = parts[0]  # Return first part (could be enhanced to send multiple)
        
        return response

    async def _is_business_hours(self, sms_config: TenantSmsConfig) -> bool:
        """Check if current time is within business hours.
        
        Args:
            sms_config: SMS configuration
            
        Returns:
            True if within business hours
        """
        # Stub implementation - in production, use proper timezone handling
        # and check against business_hours JSON structure
        try:
            import pytz
            from datetime import datetime
            
            if not sms_config.business_hours:
                return True  # No hours configured, assume always open
            
            tz = pytz.timezone(sms_config.timezone)
            now = datetime.now(tz)
            day_name = now.strftime("%A").lower()  # monday, tuesday, etc.
            
            hours = sms_config.business_hours.get(day_name)
            if not hours:
                return False  # No hours for this day
            
            current_time = now.strftime("%H:%M")
            start_time = hours.get("start", "00:00")
            end_time = hours.get("end", "23:59")
            
            return start_time <= current_time <= end_time
        except Exception:
            # On error, assume business hours
            return True

