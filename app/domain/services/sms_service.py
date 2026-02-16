"""SMS service for processing SMS messages via Twilio."""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.chat_service import ChatService
from app.domain.services.compliance_handler import ComplianceHandler, ComplianceResult
from app.domain.services.dnc_service import DncService
from app.domain.services.escalation_service import EscalationService
from app.domain.services.intent_detector import IntentDetector
from app.domain.services.opt_in_service import OptInService
from app.domain.services.prompt_service import PromptService
from app.domain.services.sms_burst_detector import SmsBurstDetector
from app.utils.name_validator import validate_name
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.lead_repository import LeadRepository
from app.persistence.repositories.tenant_repository import TenantRepository

logger = logging.getLogger(__name__)


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
        logger.info(f"SMS processing started - tenant_id={tenant_id}, phone={phone_number}, message_length={len(message_body)}")

        # Get tenant SMS config
        sms_config = await self._get_sms_config(tenant_id)
        if not sms_config:
            logger.warning(f"No SMS config found for tenant_id={tenant_id}")
            return SmsResult(
                response_message="SMS service is not configured for this tenant.",
            )
        if not sms_config.is_enabled:
            logger.info(f"SMS disabled for tenant_id={tenant_id}")
            return SmsResult(
                response_message="SMS service is not enabled for this tenant.",
            )

        # Check if sender is on Do Not Contact list - if so, silently ignore
        dnc_service = DncService(self.session)
        if await dnc_service.is_blocked(tenant_id, phone=phone_number):
            logger.info(f"DNC block - silently ignoring SMS from {phone_number}")
            return SmsResult(response_message="")  # Silent - no response

        # Auto opt-in: When someone texts us, they're implicitly opting in
        opt_in_service = OptInService(self.session)
        try:
            is_opted_in = await opt_in_service.is_opted_in(tenant_id, phone_number)
            if not is_opted_in:
                await opt_in_service.opt_in(tenant_id, phone_number, method="inbound_sms")
                logger.info(f"Auto opt-in - tenant_id={tenant_id}, phone={phone_number}")
        except Exception as e:
            logger.warning(f"Auto opt-in failed: {e}")
            # Continue processing even if opt-in fails

        # Check compliance (STOP, HELP, START keywords)
        compliance_result = self.compliance_handler.check_compliance(message_body)

        # Handle DNC request - add to Do Not Contact list (blocks ALL communication)
        if compliance_result.action == "dnc":
            try:
                await dnc_service.block(
                    tenant_id=tenant_id,
                    phone=phone_number,
                    source_channel="sms",
                    source_message=message_body[:500],  # Truncate for storage
                )
                # Also opt out of SMS
                await opt_in_service.opt_out(tenant_id, phone_number, method="DNC")
                logger.info(f"DNC block via SMS - tenant_id={tenant_id}, phone={phone_number}")
                # Cancel any active drip campaigns for this phone
                await self._cancel_drip_for_phone(tenant_id, phone_number, "dnc")
            except Exception as e:
                logger.warning(f"DNC block failed: {e}")
            return SmsResult(
                response_message=compliance_result.response_message,
                opt_in_status_changed=True,
            )

        # Handle STOP keyword - opt out and return immediately
        if compliance_result.action == "stop":
            try:
                await opt_in_service.opt_out(tenant_id, phone_number, method="STOP")
                logger.info(f"Opt-out via STOP - tenant_id={tenant_id}, phone={phone_number}")
                # Cancel any active drip campaigns for this phone
                await self._cancel_drip_for_phone(tenant_id, phone_number, "stop_keyword")
            except Exception as e:
                logger.warning(f"Opt-out failed: {e}")
            return SmsResult(
                response_message=compliance_result.response_message,
                opt_in_status_changed=True,
            )

        # Handle START/opt-in keyword - ensure opted in and continue
        if compliance_result.action == "opt_in":
            try:
                await opt_in_service.opt_in(tenant_id, phone_number, method="START")
                logger.info(f"Opt-in via START - tenant_id={tenant_id}, phone={phone_number}")
            except Exception as e:
                logger.warning(f"Opt-in failed: {e}")
            return SmsResult(
                response_message=compliance_result.response_message,
                opt_in_status_changed=True,
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

        # Build handoff context from source web chat if this is a handoff conversation
        handoff_context = None
        if conversation.source_conversation_id:
            handoff_context = await self._build_handoff_context(
                conversation.source_conversation_id
            )
            if handoff_context:
                logger.info(
                    f"Loaded chat handoff context for SMS conversation {conversation.id} "
                    f"from chat {conversation.source_conversation_id}"
                )

        # Check if this is a follow-up conversation and extract qualification data
        lead = await self._get_lead_for_conversation(tenant_id, conversation.id)

        # Check for active drip campaign enrollment — handle response if enrolled
        if lead and lead.extra_data and lead.extra_data.get("drip_enrolled"):
            try:
                from app.domain.services.drip_campaign_service import DripCampaignService
                drip_service = DripCampaignService(self.session)
                drip_result = await drip_service.handle_response(
                    tenant_id, lead.id, message_body
                )
                if drip_result.get("handled"):
                    logger.info(
                        f"Drip campaign handled SMS from {phone_number}: "
                        f"category={drip_result.get('category')}"
                    )
                    return SmsResult(
                        response_message=drip_result.get("reply", ""),
                    )
            except Exception as e:
                logger.error(f"Drip response handling failed: {e}", exc_info=True)
                # Fall through to normal processing

        is_followup = False
        qualification_context = None

        if lead and lead.extra_data:
            followup_conv_id = lead.extra_data.get("followup_conversation_id")
            if followup_conv_id == conversation.id:
                is_followup = True
                # Extract qualification data from the user's message
                extracted = await self._extract_qualification_data(message_body)
                if extracted:
                    await self._update_lead_qualification(lead, extracted)
                # Build context for qualification prompt
                qualification_context = await self._build_qualification_context(lead)

        # Detect intent
        intent_result = self.intent_detector.detect_intent(message_body)

        # Check for escalation - include customer data from phone and lead
        customer_name = lead.name if lead else None
        customer_email = lead.email if lead else None
        escalation = await self.escalation_service.check_and_escalate(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=message_body,
            confidence_score=intent_result.confidence if intent_result.intent == "human_handoff" else None,
            channel="sms",
            customer_phone=phone_number,
            customer_email=customer_email,
            customer_name=customer_name,
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

        # Choose prompt method based on whether this is a follow-up conversation
        logger.info(f"SMS calling LLM - tenant_id={tenant_id}, is_followup={is_followup}")
        if is_followup and qualification_context:
            # Use qualification prompt for follow-up conversations
            llm_response, llm_latency_ms = await self.chat_service._process_chat_core(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=message_body,
                messages=messages,
                system_prompt_method=self.prompt_service.compose_prompt_sms_qualification,
                additional_context=qualification_context,
            )
            # Capture/update lead from follow-up SMS conversation
            await self._capture_sms_lead(
                tenant_id=tenant_id,
                conversation=conversation,
                phone_number=phone_number,
                messages=messages,
                user_message=message_body,
            )
        else:
            # Process with regular SMS prompt (include handoff context if available)
            llm_response, llm_latency_ms = await self.chat_service._process_chat_core(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=message_body,
                messages=messages,
                system_prompt_method=self.prompt_service.compose_prompt_sms,
                additional_context=handoff_context,
            )

        # Capture lead from SMS conversation (we always have phone number)
        await self._capture_sms_lead(
            tenant_id=tenant_id,
            conversation=conversation,
            phone_number=phone_number,
            messages=messages,
            user_message=message_body,
        )

        # Check for user request to receive registration info (or other assets)
        # Pass messages for qualification validation before sending registration links
        await self._check_and_fulfill_request(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=message_body,
            ai_response=llm_response,
            phone=phone_number,
            name=lead.name if lead else None,
            messages=messages,
        )

        # ============================================================
        # HIGH INTENT LEAD NOTIFICATION: Check if this conversation
        # shows high enrollment intent and notify business owner
        # ============================================================
        try:
            # Get updated lead with any newly captured info
            updated_lead = await self._get_lead_for_conversation(tenant_id, conversation.id)
            await self._check_and_notify_high_intent_lead(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message=message_body,
                messages=messages,
                lead=updated_lead,
                phone_number=phone_number,
                channel="sms",
            )
        except Exception as e:
            # Don't let notification failure affect the SMS flow
            logger.error(f"Failed to check/send high intent lead notification: {e}", exc_info=True)

        # Format response for SMS (short, no markdown)
        formatted_response = self._format_sms_response(llm_response)
        logger.info(f"SMS LLM response received - tenant_id={tenant_id}, latency_ms={llm_latency_ms}, response_length={len(formatted_response)}")

        # Add assistant response
        await conversation_service.add_message(
            tenant_id, conversation.id, "assistant", formatted_response
        )

        # Get SMS provider via factory (Twilio or Telnyx based on config)
        factory = TelephonyProviderFactory(self.session)
        sms_provider = await factory.get_sms_provider(tenant_id)

        if not sms_provider:
            logger.error(f"No SMS provider configured for tenant {tenant_id}")
            return SmsResult(
                response_message=formatted_response,
                message_sid=None,
            )

        # Get the correct phone number based on provider
        from_number = factory.get_sms_phone_number(sms_config)
        if not from_number:
            logger.error(f"No SMS phone number configured for tenant {tenant_id}")
            return SmsResult(
                response_message=formatted_response,
                message_sid=None,
            )

        # Get webhook base URL from settings
        from app.settings import settings
        status_callback_url = None
        if settings.twilio_webhook_url_base:
            # Use provider-specific webhook path
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.twilio_webhook_url_base}/api/v1{webhook_prefix}/sms/status"

        # Check for SMS burst/spam pattern before sending
        try:
            burst_detector = SmsBurstDetector(self.session)
            burst_result = await burst_detector.check_outbound_sms(
                tenant_id=tenant_id,
                to_number=phone_number,
                message_content=formatted_response,
            )
            if burst_result.should_block:
                logger.warning(
                    f"SMS BLOCKED by burst detector - tenant_id={tenant_id}, "
                    f"to={phone_number}, incident={burst_result.incident_id}, "
                    f"count={burst_result.message_count}"
                )
                return SmsResult(
                    response_message=formatted_response,
                    message_sid=None,
                )
            if burst_result.is_burst:
                logger.warning(
                    f"SMS burst warning (not blocked) - tenant_id={tenant_id}, "
                    f"to={phone_number}, severity={burst_result.severity}, "
                    f"incident={burst_result.incident_id}"
                )
        except Exception as e:
            logger.error(f"Burst detection failed (allowing send): {e}", exc_info=True)

        # Send via the configured provider
        logger.info(f"SMS sending response - tenant_id={tenant_id}, to={phone_number}, from={from_number}")
        send_result = await sms_provider.send_sms(
            to=phone_number,
            from_=from_number,
            body=formatted_response,
            status_callback=status_callback_url,
        )
        logger.info(f"SMS sent successfully - tenant_id={tenant_id}, message_id={send_result.message_id}")

        return SmsResult(
            response_message=formatted_response,
            message_sid=send_result.message_id,
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

    async def _send_early_response(
        self,
        tenant_id: int,
        sms_config: TenantSmsConfig,
        to_phone: str,
        message: str,
    ) -> str | None:
        """Send an early response SMS (for opt-in, compliance, etc.).

        Used when we need to respond without going through the full LLM flow.

        Args:
            tenant_id: Tenant ID
            sms_config: SMS configuration
            to_phone: Recipient phone number
            message: Message to send

        Returns:
            Message SID or None if failed
        """
        try:
            factory = TelephonyProviderFactory(self.session)
            sms_provider = await factory.get_sms_provider(tenant_id)

            if not sms_provider:
                logger.error(f"No SMS provider configured for tenant {tenant_id}")
                return None

            from_number = factory.get_sms_phone_number(sms_config)
            if not from_number:
                logger.error(f"No SMS phone number configured for tenant {tenant_id}")
                return None

            send_result = await sms_provider.send_sms(
                to=to_phone,
                from_=from_number,
                body=message,
                status_callback=None,
            )
            return send_result.message_id
        except Exception as e:
            logger.error(f"Failed to send early response SMS: {e}", exc_info=True)
            return None

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
        # Remove markdown headings (e.g., ### Title)
        response = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', response)
        # Remove markdown list markers (-, *, +, or numbered lists)
        response = re.sub(r'(?m)^\s*[-*+]\s+', '', response)
        response = re.sub(r'(?m)^\s*\d+\.\s+', '', response)
        # Remove links [text](url) -> text
        response = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', response)
        # Remove markdown links
        response = re.sub(r'https?://[^\s]+', '', response)
        
        # Remove remaining inline markdown characters
        response = response.replace("*", "")
        response = response.replace("_", "")
        response = response.replace("`", "")

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

    async def _get_lead_for_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Lead | None:
        """Get lead associated with a conversation.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Lead or None if not found
        """
        lead_repo = LeadRepository(self.session)
        return await lead_repo.get_by_conversation(tenant_id, conversation_id)

    async def _cancel_drip_for_phone(
        self, tenant_id: int, phone_number: str, reason: str
    ) -> None:
        """Cancel all active drip campaigns for a phone number."""
        try:
            from app.domain.services.drip_campaign_service import DripCampaignService
            lead_repo = LeadRepository(self.session)
            # Find leads by phone
            leads = await lead_repo.find_leads_with_conversation_by_email_or_phone(
                tenant_id, phone=phone_number
            )
            drip_service = DripCampaignService(self.session)
            for lead in leads:
                if lead.extra_data and lead.extra_data.get("drip_enrolled"):
                    count = await drip_service.cancel_all_for_lead(tenant_id, lead.id, reason)
                    if count > 0:
                        logger.info(f"Cancelled {count} drip enrollments for lead {lead.id} ({reason})")
        except Exception as e:
            logger.error(f"Failed to cancel drip for phone {phone_number}: {e}", exc_info=True)

    async def _check_and_notify_high_intent_lead(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        messages: list,
        lead,
        phone_number: str,
        channel: str = "sms",
    ) -> None:
        """Check for high enrollment intent and notify business owner if detected.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            user_message: Current user message
            messages: Full conversation history
            lead: Lead object (if exists)
            phone_number: User's phone number
            channel: Communication channel
        """
        from app.domain.services.intent_detector import IntentDetector
        from app.infrastructure.notifications import NotificationService

        # Build conversation history strings for intent detection
        conversation_history = [msg.content for msg in messages if hasattr(msg, "content")]

        # For SMS, we always have phone
        has_phone = True
        has_email = bool(lead and lead.email)

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
                f"No high intent detected (SMS) - tenant_id={tenant_id}, "
                f"conversation_id={conversation_id}, confidence={intent_result.confidence:.2f}"
            )
            return

        logger.info(
            f"High enrollment intent detected (SMS) - tenant_id={tenant_id}, "
            f"conversation_id={conversation_id}, confidence={intent_result.confidence:.2f}, "
            f"keywords={intent_result.keywords}"
        )

        # Get customer info
        customer_name = lead.name if lead else None
        customer_email = lead.email if lead else None

        # Send notification
        notification_service = NotificationService(self.session)
        result = await notification_service.notify_high_intent_lead(
            tenant_id=tenant_id,
            customer_name=customer_name,
            customer_phone=phone_number,
            customer_email=customer_email,
            channel=channel,
            message_preview=user_message[:150],
            confidence=intent_result.confidence,
            keywords=intent_result.keywords,
            conversation_id=conversation_id,
            lead_id=lead.id if lead else None,
        )

        logger.info(
            f"Lead notification result (SMS) - tenant_id={tenant_id}, "
            f"conversation_id={conversation_id}, status={result.get('status')}"
        )

    async def _build_handoff_context(self, source_conversation_id: int) -> str | None:
        """Build context string from the source chat conversation for handoff continuity.

        Args:
            source_conversation_id: ID of the source web chat conversation

        Returns:
            Context string or None if no messages found
        """
        try:
            from sqlalchemy import select
            from app.persistence.models.conversation import Message

            stmt = (
                select(Message)
                .where(
                    Message.conversation_id == source_conversation_id,
                    Message.role.in_(["user", "assistant"]),
                )
                .order_by(Message.sequence_number.desc())
                .limit(10)
            )
            result = await self.session.execute(stmt)
            messages = list(reversed(result.scalars().all()))

            if not messages:
                return None

            parts = [
                "PREVIOUS WEB CHAT CONTEXT (continue this conversation naturally, "
                "do NOT re-introduce yourself or re-ask questions already answered):"
            ]
            for msg in messages:
                role_label = "Customer" if msg.role == "user" else "Agent"
                content = msg.content[:300] if len(msg.content) > 300 else msg.content
                parts.append(f"{role_label}: {content}")

            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Failed to build handoff context: {e}", exc_info=True)
            return None

    async def _build_qualification_context(self, lead: Lead) -> dict:
        """Build context about what qualification data has been collected.

        Args:
            lead: Lead to check

        Returns:
            Context dictionary for qualification prompt
        """
        qual_data = lead.extra_data.get("qualification_data", {}) if lead.extra_data else {}

        return {
            "collected_name": bool(lead.name or qual_data.get("name")),
            "collected_email": bool(lead.email or qual_data.get("email")),
            "collected_phone": True,  # We always have phone for SMS
            "collected_budget": bool(qual_data.get("budget")),
            "collected_timeline": bool(qual_data.get("timeline")),
            "collected_needs": bool(qual_data.get("needs")),
        }

    async def _extract_qualification_data(self, message: str) -> dict | None:
        """Extract qualification data from user message using LLM.

        Args:
            message: User message to extract from

        Returns:
            Dictionary with extracted data or None
        """
        extraction_prompt = f"""Extract any contact or qualification information from this message.

Message: "{message}"

Extract:
- name: Their name if mentioned
- email: Email address if provided
- budget: Budget or price range mentioned
- timeline: Timeline or urgency mentioned
- needs: Specific services or needs mentioned

Respond with ONLY valid JSON, no explanation:
{{"name": null, "email": null, "budget": null, "timeline": null, "needs": null}}"""

        try:
            response = await self.chat_service.llm_orchestrator.generate(
                extraction_prompt,
                context={"temperature": 0.0, "max_tokens": 150},
            )

            # Parse JSON response
            data = json.loads(response.strip())

            # Filter out null values
            extracted = {k: v for k, v in data.items() if v and v != "null"}
            return extracted if extracted else None

        except Exception as e:
            logger.warning(f"Qualification extraction failed: {e}")
            return None

    async def _update_lead_qualification(self, lead: Lead, extracted: dict) -> None:
        """Update lead with extracted qualification data.

        Args:
            lead: Lead to update
            extracted: Extracted data dictionary
        """
        extra_data = dict(lead.extra_data or {})
        qual_data = extra_data.get("qualification_data", {})

        # Update qualification data (don't overwrite existing values)
        for key, value in extracted.items():
            if key in ["name", "email"]:
                # These go to main lead fields
                if key == "name" and not lead.name and value:
                    # Validate name before setting
                    validated_name = validate_name(value, require_explicit=False)
                    if validated_name:
                        lead.name = validated_name
                        logger.info(f"Updated lead {lead.id} name: {validated_name}")
                    else:
                        logger.info(f"Rejected invalid name for lead {lead.id}: {value}")
                elif key == "email" and not lead.email and value:
                    lead.email = value
                    logger.info(f"Updated lead {lead.id} email: {value}")
            else:
                # Store in qualification_data
                if not qual_data.get(key) and value:
                    qual_data[key] = value
                    logger.info(f"Updated lead {lead.id} {key}: {value}")

        extra_data["qualification_data"] = qual_data
        lead.extra_data = extra_data
        await self.session.commit()

    async def _capture_sms_lead(
        self,
        tenant_id: int,
        conversation: Conversation,
        phone_number: str,
        messages: list[Message],
        user_message: str,
    ) -> None:
        """Capture or update lead from SMS conversation.

        SMS always has the phone number, so we can always create a lead.
        We also extract name/email from conversation if provided.

        Args:
            tenant_id: Tenant ID
            conversation: Conversation object
            phone_number: Sender phone number
            messages: Previous messages in conversation
            user_message: Current user message
        """
        try:
            # Check if lead already exists for this conversation
            lead_repo = LeadRepository(self.session)
            existing_lead = await lead_repo.get_by_conversation(tenant_id, conversation.id)

            # Extract name/email from conversation using chat_service's extraction
            extracted_info = await self.chat_service._extract_contact_info_from_conversation(
                messages, user_message
            )

            extracted_name = extracted_info.get("name")
            extracted_email = extracted_info.get("email")
            name_is_explicit = extracted_info.get("name_is_explicit", False)

            logger.debug(
                f"SMS lead extraction - phone={phone_number}, name={extracted_name}, "
                f"email={extracted_email}, existing_lead={existing_lead is not None}"
            )

            if existing_lead:
                # Update existing lead with new information
                updated = False
                if extracted_name and (not existing_lead.name or name_is_explicit):
                    # Validate name before setting (double-check validation)
                    validated_name = validate_name(extracted_name, require_explicit=name_is_explicit)
                    if validated_name:
                        existing_lead.name = validated_name
                        updated = True
                    else:
                        logger.info(f"Rejected invalid name for existing lead: {extracted_name}")
                if extracted_email and not existing_lead.email:
                    existing_lead.email = extracted_email
                    updated = True
                if updated:
                    await self.session.commit()
                    logger.info(
                        f"SMS lead updated - tenant_id={tenant_id}, lead_id={existing_lead.id}, "
                        f"name={extracted_name}, email={extracted_email}"
                    )

                from app.domain.services.lead_service import LeadService
                lead_service = LeadService(self.session)
                await lead_service.bump_lead_activity(tenant_id, existing_lead.id)
            else:
                # If this is a handoff conversation, try to reuse the chat lead
                from app.domain.services.lead_service import LeadService
                lead_service = LeadService(self.session)

                if conversation.source_conversation_id:
                    source_lead = await lead_repo.get_by_conversation(
                        tenant_id, conversation.source_conversation_id
                    )
                    if source_lead:
                        # Update the source lead with phone + any new info
                        if not source_lead.phone:
                            source_lead.phone = phone_number
                        if extracted_name and not source_lead.name:
                            validated_name = validate_name(extracted_name, require_explicit=name_is_explicit)
                            if validated_name:
                                source_lead.name = validated_name
                        if extracted_email and not source_lead.email:
                            source_lead.email = extracted_email
                        # Track the linked SMS conversation
                        extra_data = dict(source_lead.extra_data or {})
                        extra_data.setdefault("linked_conversations", [])
                        if conversation.id not in extra_data["linked_conversations"]:
                            extra_data["linked_conversations"].append(conversation.id)
                        source_lead.extra_data = extra_data
                        from datetime import datetime
                        source_lead.updated_at = datetime.utcnow()
                        await self.session.commit()
                        await lead_service.bump_lead_activity(tenant_id, source_lead.id)
                        logger.info(
                            f"Unified SMS lead with chat lead - tenant_id={tenant_id}, "
                            f"lead_id={source_lead.id}, sms_conv={conversation.id}"
                        )
                        return

                # Create new lead with phone number (always available) + extracted info
                lead = await lead_service.capture_lead(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    email=extracted_email,
                    phone=phone_number,
                    name=extracted_name,
                    metadata={"source": "sms"},
                )
                logger.info(
                    f"SMS lead captured - tenant_id={tenant_id}, lead_id={lead.id}, "
                    f"phone={phone_number}, name={extracted_name}, email={extracted_email}"
                )

        except Exception as e:
            logger.error(
                f"Failed to capture SMS lead - tenant_id={tenant_id}, "
                f"conversation_id={conversation.id}, error={e}",
                exc_info=True
            )

    async def _check_and_fulfill_request(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        ai_response: str,
        phone: str,
        name: str | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        """Check for user request or AI promise to send info and fulfill it.

        For registration links, validates that qualification questions (age, experience,
        level recommendation) have been answered before sending the link.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            user_message: User's SMS message
            ai_response: AI's response
            phone: User's phone number
            name: User's name (optional)
            messages: Conversation history (for qualification check)
        """
        try:
            from app.domain.services.user_request_detector import UserRequestDetector
            from app.domain.services.promise_detector import PromiseDetector, DetectedPromise
            from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
            from app.domain.services.registration_qualification_validator import (
                RegistrationQualificationValidator,
            )

            fulfillment_service = PromiseFulfillmentService(self.session)
            qualification_validator = RegistrationQualificationValidator(self.session)

            # Check user message for request
            user_detector = UserRequestDetector()
            user_request = user_detector.detect_request(user_message)

            if user_request and user_request.confidence >= 0.6:
                logger.info(
                    f"User request detected in SMS - tenant_id={tenant_id}, "
                    f"asset_type={user_request.asset_type}, confidence={user_request.confidence:.2f}"
                )

                # For registration links, validate qualification first
                if user_request.asset_type == "registration_link" and messages:
                    qualification_status = await qualification_validator.check_qualification(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        messages=messages,
                    )
                    if not qualification_status.is_qualified:
                        logger.info(
                            f"Registration link request blocked - not qualified. "
                            f"tenant_id={tenant_id}, missing={qualification_status.missing_requirements}"
                        )
                        # Don't fulfill - let the LLM continue asking qualification questions
                        return

                promise = DetectedPromise(
                    asset_type=user_request.asset_type,
                    confidence=user_request.confidence,
                    original_text=user_request.original_text,
                )
                result = await fulfillment_service.fulfill_promise(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    promise=promise,
                    phone=phone,
                    name=name,
                    messages=messages,
                    ai_response=ai_response,
                )
                logger.info(
                    f"User request fulfillment result - tenant_id={tenant_id}, "
                    f"status={result.get('status')}, asset_type={user_request.asset_type}"
                )
                return  # Don't double-send if user request detected

            # Check AI response for promise
            # Build conversation context from messages for asset type identification
            # This helps identify "registration_link" when AI says "I'll send that to you"
            # but the registration context is in previous messages
            conversation_text = " ".join(
                m.content for m in messages if hasattr(m, "content") and m.content
            )
            ai_detector = PromiseDetector()
            ai_promise = ai_detector.detect_promise(ai_response, conversation_context=conversation_text)

            if ai_promise and ai_promise.confidence >= 0.6:
                logger.info(
                    f"AI promise detected in SMS - tenant_id={tenant_id}, "
                    f"asset_type={ai_promise.asset_type}, confidence={ai_promise.confidence:.2f}"
                )

                # For registration links, validate qualification first
                if ai_promise.asset_type == "registration_link" and messages:
                    qualification_status = await qualification_validator.check_qualification(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        messages=messages,
                    )
                    if not qualification_status.is_qualified:
                        logger.info(
                            f"Registration link promise blocked - not qualified. "
                            f"tenant_id={tenant_id}, missing={qualification_status.missing_requirements}"
                        )
                        # Don't fulfill - the AI shouldn't have promised without qualification
                        return

                result = await fulfillment_service.fulfill_promise(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    promise=ai_promise,
                    phone=phone,
                    name=name,
                    messages=messages,
                    ai_response=ai_response,
                )
                logger.info(
                    f"AI promise fulfillment result - tenant_id={tenant_id}, "
                    f"status={result.get('status')}, asset_type={ai_promise.asset_type}"
                )

        except Exception as e:
            logger.error(
                f"Error in SMS request/promise fulfillment - tenant_id={tenant_id}, "
                f"conversation_id={conversation_id}, error={e}",
                exc_info=True
            )
