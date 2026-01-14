"""Email service for processing inbound emails via Gmail API."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.chat_service import ChatService
from app.domain.services.conversation_service import ConversationService
from app.domain.services.email_body_parser import EmailBodyParser
from app.domain.services.escalation_service import EscalationService
from app.domain.services.intent_detector import IntentDetector
from app.domain.services.lead_service import LeadService
from app.domain.services.prompt_service import PromptService
from app.infrastructure.gmail_client import GmailAPIError, GmailClient
from app.persistence.models.conversation import Conversation
from app.persistence.models.tenant_email_config import EmailConversation, TenantEmailConfig
from app.persistence.repositories.email_repository import (
    EmailConversationRepository,
    TenantEmailConfigRepository,
)
from app.persistence.repositories.tenant_repository import TenantRepository
from app.infrastructure.pubsub import get_gmail_pubsub_topic

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of email processing."""
    
    response_message: str
    message_id: str | None = None
    thread_id: str | None = None
    requires_escalation: bool = False
    escalation_id: int | None = None
    lead_captured: bool = False
    lead_id: int | None = None


class EmailService:
    """Service for processing inbound emails."""

    # Email constraints
    MAX_THREAD_MESSAGES = 10  # Max messages in thread to use as context
    MAX_BODY_LENGTH = 10000  # Max email body length to process

    # Watch renewal threshold - refresh if expiring within 1 day
    WATCH_RENEWAL_THRESHOLD = timedelta(days=1)

    def __init__(self, session: AsyncSession) -> None:
        """Initialize Email service."""
        self.session = session
        self.chat_service = ChatService(session)
        self.conversation_service = ConversationService(session)
        self.lead_service = LeadService(session)
        self.escalation_service = EscalationService(session)
        self.intent_detector = IntentDetector()
        self.prompt_service = PromptService(session)
        self.tenant_repo = TenantRepository(session)
        self.email_config_repo = TenantEmailConfigRepository(session)
        self.email_conv_repo = EmailConversationRepository(session)
        self.body_parser = EmailBodyParser()

    async def process_inbound_email(
        self,
        tenant_id: int,
        from_email: str,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str,
        message_id: str,
        gmail_client: GmailClient | None = None,
    ) -> EmailResult:
        """Process an inbound email message.
        
        Args:
            tenant_id: Tenant ID
            from_email: Sender email address
            to_email: Recipient email address
            subject: Email subject
            body: Plain text email body
            thread_id: Gmail thread ID
            message_id: Gmail message ID
            gmail_client: Optional pre-configured Gmail client
            
        Returns:
            EmailResult with response and metadata
        """
        # Get tenant email config
        email_config = await self._get_email_config(tenant_id)
        if not email_config or not email_config.is_enabled:
            logger.warning(f"Email service not enabled for tenant {tenant_id}")
            return EmailResult(
                response_message="Email service is not enabled for this tenant.",
            )
        
        # Parse sender information
        sender_name, sender_email = GmailClient.parse_email_address(from_email)

        # Check if this is a lead capture email (should be processed even if from no-reply)
        is_lead_capture = self._should_capture_lead_from_subject(
            subject=subject,
            email_config=email_config,
        )

        # Check if this is a no-reply or automated email (skip unless it's a lead capture email)
        if not is_lead_capture and self._is_automated_email(sender_email, subject, body):
            logger.info(f"Skipping automated email from {sender_email}")
            return EmailResult(
                response_message="Automated email detected, skipping response.",
            )
        
        # Check business hours
        if email_config.business_hours_enabled:
            is_business_hours = await self._is_business_hours(email_config)
            if not is_business_hours and email_config.auto_reply_outside_hours:
                auto_reply = (
                    email_config.auto_reply_message or
                    "Thank you for your email. We're currently outside our business hours. "
                    "We'll respond as soon as possible during our next business day."
                )
                
                # Outbound email replies are disabled - receive only mode
                logger.info(f"Skipping auto-reply to {sender_email} - outbound replies disabled")

                return EmailResult(
                    response_message="Outside business hours - no reply sent (receive-only mode)",
                    thread_id=thread_id,
                )
        
        # Get or create email conversation tracking
        email_conversation = await self._get_or_create_email_conversation(
            tenant_id=tenant_id,
            thread_id=thread_id,
            from_email=sender_email,
            to_email=to_email,
            subject=subject,
            message_id=message_id,
        )
        
        # Get or create internal conversation for LLM context
        conversation = await self._get_or_create_conversation(
            tenant_id=tenant_id,
            email_conversation=email_conversation,
        )
        
        # Get thread history for context
        thread_context = await self._get_thread_context(
            gmail_client=gmail_client,
            thread_id=thread_id,
            max_messages=email_config.max_thread_depth or self.MAX_THREAD_MESSAGES,
        )
        
        # Get conversation history from internal system
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation.id
        )
        
        # Truncate body if too long
        processed_body = self._preprocess_email_body(body)
        
        # Add user message
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "user", processed_body
        )
        
        # Check for escalation keywords
        escalation = await self._check_escalation(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            email_config=email_config,
            subject=subject,
            body=processed_body,
            sender_email=sender_email,
        )
        
        if escalation:
            # Notify about escalation but still generate a response
            logger.info(f"Email escalated for tenant {tenant_id}, conversation {conversation.id}")
            
            # Update email conversation status
            await self.email_conv_repo.update_status(
                tenant_id=tenant_id,
                gmail_thread_id=thread_id,
                status="escalated",
            )
        
        # Check if this email's subject matches lead capture prefixes
        should_capture_lead = self._should_capture_lead_from_subject(
            subject=subject,
            email_config=email_config,
        )

        # Extract lead info from email signature and content
        # Pass should_capture_lead so form submissions use body data only (not sender info)
        lead_captured = False
        lead_id = None
        extracted_info = self._extract_contact_info(
            from_email, sender_name, body, subject=subject, is_lead_capture_email=should_capture_lead
        )
        
        print(f"[LEAD_CAPTURE] subject='{subject}', should_capture={should_capture_lead}, has_extracted_info={extracted_info is not None}, existing_lead_id={email_conversation.lead_id}", flush=True)
        print(f"[LEAD_CAPTURE] extracted_info={extracted_info}", flush=True)
        logger.info(f"Lead capture check: subject='{subject}', should_capture={should_capture_lead}, has_extracted_info={extracted_info is not None}, has_existing_lead={email_conversation.lead_id is not None}")
        
        if extracted_info and should_capture_lead:
            print(f"[LEAD_CAPTURE] All conditions met, attempting to create lead", flush=True)
            # Build metadata for lead (include additional fields and parsing metadata)
            metadata = {"source": "email"}
            if extracted_info.get("additional_fields"):
                metadata.update(extracted_info["additional_fields"])
            if extracted_info.get("metadata"):
                metadata["parsing_metadata"] = extracted_info["metadata"]
            
            # Try to capture lead
            try:
                lead = await self.lead_service.capture_lead(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    email=extracted_info.get("email"),
                    phone=extracted_info.get("phone"),
                    name=extracted_info.get("name"),
                    metadata=metadata if metadata else None,
                )
                if lead:
                    lead_captured = True
                    lead_id = lead.id
                    print(f"[LEAD_CAPTURE] SUCCESS: lead_id={lead.id}, email={extracted_info.get('email')}, name={extracted_info.get('name')}", flush=True)
                    logger.info(f"Lead captured: lead_id={lead.id}, email={extracted_info.get('email')}, name={extracted_info.get('name')}")
                    # Link to email conversation
                    await self.email_conv_repo.link_to_contact(
                        tenant_id=tenant_id,
                        gmail_thread_id=thread_id,
                        lead_id=lead.id,
                    )
                else:
                    print(f"[LEAD_CAPTURE] FAILED: lead_service.capture_lead returned None", flush=True)
            except Exception as e:
                print(f"[LEAD_CAPTURE] ERROR: {type(e).__name__}: {e}", flush=True)
                logger.error(f"Error capturing lead: {e}", exc_info=True)
        elif not should_capture_lead:
            print(f"[LEAD_CAPTURE] SKIP: subject '{subject}' does not match prefixes", flush=True)
            logger.info(f"Skipping lead capture for email with subject '{subject}' - does not match configured prefixes")
        elif not extracted_info:
            print(f"[LEAD_CAPTURE] SKIP: no extracted_info", flush=True)

        # For lead capture emails, just capture the lead and return without sending a response
        # This prevents auto-replies to form submission emails
        if should_capture_lead:
            print(f"[LEAD_CAPTURE] Lead capture email - skipping LLM response and email reply", flush=True)
            logger.info(f"Lead capture email processed - not sending automated response")
            return EmailResult(
                response_message="Lead captured from form submission (no response sent)",
                thread_id=thread_id,
                lead_captured=lead_captured,
                lead_id=lead_id,
            )

        # Compose prompt with email-specific context
        additional_context = self._build_email_context(
            subject=subject,
            sender_name=sender_name,
            thread_context=thread_context,
        )
        
        # Process with LLM
        llm_response, llm_latency_ms = await self.chat_service._process_chat_core(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=processed_body,
            messages=messages,
            system_prompt_method=self._get_email_prompt,
            additional_context=additional_context,
        )
        
        # Format response for email
        formatted_response = self._format_email_response(
            response=llm_response,
            signature=email_config.response_signature,
        )
        
        # Add assistant response
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "assistant", formatted_response
        )
        
        # Update email conversation
        await self.email_conv_repo.create_or_update(
            tenant_id=tenant_id,
            gmail_thread_id=thread_id,
            gmail_message_id=message_id,
            last_response_at=datetime.utcnow(),
        )
        
        # Outbound email replies are disabled - receive only mode
        # Email data is captured but no reply is sent
        sent_message_id = None
        logger.info(f"Skipping email reply to {sender_email} - outbound replies disabled (receive-only mode)")
        
        return EmailResult(
            response_message=formatted_response,
            message_id=sent_message_id,
            thread_id=thread_id,
            requires_escalation=escalation is not None,
            escalation_id=escalation.id if escalation else None,
            lead_captured=lead_captured,
            lead_id=lead_id,
        )

    async def process_gmail_notification(
        self,
        email_address: str,
        history_id: str,
    ) -> list[EmailResult]:
        """Process Gmail push notification for new messages.
        
        Args:
            email_address: Gmail address that received the notification
            history_id: Gmail history ID from notification
            
        Returns:
            List of EmailResult for each processed message
        """
        print(f"[EMAIL_SERVICE] process_gmail_notification: email={email_address}, history_id={history_id}", flush=True)
        logger.info(f"Processing Gmail notification: email={email_address}, history_id={history_id}")
        
        # Get email config by Gmail address
        email_config = await self.email_config_repo.get_by_email(email_address)
        if not email_config:
            print(f"[EMAIL_SERVICE] No email config found for {email_address}", flush=True)
            logger.warning(f"No email config found for {email_address}")
            return []
        
        print(f"[EMAIL_SERVICE] Found config for tenant_id={email_config.tenant_id}, enabled={email_config.is_enabled}", flush=True)
        
        if not email_config.is_enabled:
            print(f"[EMAIL_SERVICE] Email processing disabled for {email_address}", flush=True)
            logger.info(f"Email processing disabled for {email_address}")
            return []
        
        # Initialize Gmail client
        gmail_client = GmailClient(
            refresh_token=email_config.gmail_refresh_token,
            access_token=email_config.gmail_access_token,
            token_expires_at=email_config.gmail_token_expires_at,
        )

        # Auto-refresh Gmail watch if expiring soon (prevents need for manual refresh)
        await self._maybe_refresh_watch(email_config, gmail_client)

        # Get history since last sync
        start_history_id = email_config.last_history_id or history_id
        
        try:
            history = gmail_client.get_history(
                start_history_id=start_history_id,
                history_types=["messageAdded"],
            )
            
            # Update last history ID
            new_history_id = history.get("history_id")
            if new_history_id:
                await self.email_config_repo.update_history_id(
                    tenant_id=email_config.tenant_id,
                    history_id=new_history_id,
                )
            
            # Update tokens if refreshed
            token_info = gmail_client.get_token_info()
            if token_info.get("access_token") != email_config.gmail_access_token:
                await self.email_config_repo.update_tokens(
                    tenant_id=email_config.tenant_id,
                    access_token=token_info["access_token"],
                    token_expires_at=token_info["token_expires_at"],
                )
            
            # Process new messages
            results = []
            history_messages = history.get("messages", [])
            print(f"[EMAIL_SERVICE] Gmail history retrieved: {len(history_messages)} messages", flush=True)
            logger.info(f"Gmail history retrieved: {len(history_messages)} messages")
            
            for msg_info in history_messages:
                message_id = msg_info.get("id")
                if not message_id:
                    continue
                
                # Fetch full message (skip if deleted/unavailable)
                try:
                    message = gmail_client.get_message(message_id)
                except GmailAPIError as e:
                    logger.warning(f"Message {message_id} not found (may have been deleted): {e}")
                    continue

                # Skip messages sent by us
                if self._is_outgoing_message(message, email_address):
                    continue
                
                print(f"[EMAIL_SERVICE] Processing inbound email: subject='{message.get('subject', '')}', from='{message.get('from', '')}'", flush=True)
                logger.info(f"Processing inbound email: subject='{message.get('subject', '')}', from='{message.get('from', '')}'")

                subject = message.get("subject", "")
                if not self._should_capture_lead_from_subject(
                    subject=subject,
                    email_config=email_config,
                ):
                    logger.info(f"Skipping email due to subject filter: subject='{subject}'")
                    continue
                
                # Process the inbound email
                result = await self.process_inbound_email(
                    tenant_id=email_config.tenant_id,
                    from_email=message.get("from", ""),
                    to_email=message.get("to", ""),
                    subject=subject,
                    body=message.get("body", ""),
                    thread_id=message.get("thread_id", ""),
                    message_id=message_id,
                    gmail_client=gmail_client,
                )
                results.append(result)
                
                # Mark as read
                gmail_client.mark_as_read(message_id)
            
            return results
            
        except GmailAPIError as e:
            print(f"[EMAIL_SERVICE] GmailAPIError: {e}", flush=True)
            logger.error(f"Failed to process Gmail notification: {e}")
            return []

    async def _get_email_config(self, tenant_id: int) -> TenantEmailConfig | None:
        """Get tenant email configuration."""
        return await self.email_config_repo.get_by_tenant_id(tenant_id)

    async def _maybe_refresh_watch(
        self,
        email_config: TenantEmailConfig,
        gmail_client: GmailClient,
    ) -> bool:
        """Check if Gmail watch is expiring soon and refresh if needed.

        Gmail watches expire after 7 days. This method automatically refreshes
        the watch if it's within 1 day of expiring, ensuring continuous email
        notifications without manual intervention.

        Args:
            email_config: Tenant email configuration
            gmail_client: Authenticated Gmail client

        Returns:
            True if watch was refreshed, False otherwise
        """
        # Check if watch needs renewal
        if not email_config.watch_expiration:
            # No watch expiration set - needs refresh
            needs_refresh = True
        else:
            time_until_expiry = email_config.watch_expiration - datetime.utcnow()
            needs_refresh = time_until_expiry < self.WATCH_RENEWAL_THRESHOLD

        if not needs_refresh:
            return False

        # Get Pub/Sub topic for watch
        topic = get_gmail_pubsub_topic()
        if not topic:
            logger.warning(f"Cannot refresh watch for tenant {email_config.tenant_id}: no Pub/Sub topic configured")
            return False

        try:
            logger.info(f"Auto-refreshing Gmail watch for tenant {email_config.tenant_id} (expiring soon or not set)")
            watch_result = gmail_client.watch_mailbox(topic)

            # Update watch expiration in database
            await self.email_config_repo.update_watch_expiration(
                tenant_id=email_config.tenant_id,
                watch_expiration=watch_result["expiration"],
                history_id=watch_result.get("history_id"),
            )

            logger.info(f"Gmail watch refreshed for tenant {email_config.tenant_id}, new expiration: {watch_result['expiration']}")
            return True

        except GmailAPIError as e:
            logger.error(f"Failed to refresh Gmail watch for tenant {email_config.tenant_id}: {e}")
            return False

    async def _get_or_create_email_conversation(
        self,
        tenant_id: int,
        thread_id: str,
        from_email: str,
        to_email: str,
        subject: str,
        message_id: str,
    ) -> EmailConversation:
        """Get or create email conversation tracking."""
        return await self.email_conv_repo.create_or_update(
            tenant_id=tenant_id,
            gmail_thread_id=thread_id,
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            gmail_message_id=message_id,
        )

    async def _get_or_create_conversation(
        self,
        tenant_id: int,
        email_conversation: EmailConversation,
    ) -> Conversation:
        """Get or create internal conversation for email."""
        if email_conversation.conversation_id:
            # Return existing conversation
            from app.persistence.repositories.conversation_repository import ConversationRepository
            conv_repo = ConversationRepository(self.session)
            conversation = await conv_repo.get_by_id(tenant_id, email_conversation.conversation_id)
            if conversation:
                return conversation
        
        # Create new conversation
        conversation = await self.conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="email",
            external_id=email_conversation.gmail_thread_id,
        )
        
        # Link to email conversation
        email_conversation.conversation_id = conversation.id
        await self.session.commit()
        
        return conversation

    async def _get_thread_context(
        self,
        gmail_client: GmailClient | None,
        thread_id: str,
        max_messages: int,
    ) -> str:
        """Get email thread context for LLM."""
        if not gmail_client:
            return ""
        
        try:
            thread = gmail_client.get_thread(thread_id)
            messages = thread.get("messages", [])[-max_messages:]
            
            context_parts = []
            for msg in messages:
                sender = msg.get("from", "Unknown")
                date = msg.get("date", "")
                body = msg.get("body", "")[:500]  # Truncate for context
                context_parts.append(f"From: {sender}\nDate: {date}\n{body}\n---")
            
            return "\n".join(context_parts)
        except GmailAPIError:
            return ""

    async def _check_escalation(
        self,
        tenant_id: int,
        conversation_id: int,
        email_config: TenantEmailConfig,
        subject: str,
        body: str,
        sender_email: str | None = None,
    ):
        """Check for escalation triggers."""
        escalation_rules = email_config.escalation_rules or {}
        keywords = escalation_rules.get("keywords", [])

        combined_text = f"{subject} {body}".lower()

        for keyword in keywords:
            if keyword.lower() in combined_text:
                return await self.escalation_service.check_and_escalate(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    user_message=body,
                    confidence_score=0.9,
                    channel="email",
                    customer_email=sender_email,
                )

        # Check for handoff intent
        intent_result = self.intent_detector.detect_intent(body)
        if intent_result.intent == "human_handoff":
            return await self.escalation_service.check_and_escalate(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_message=body,
                confidence_score=intent_result.confidence,
                channel="email",
                customer_email=sender_email,
            )

        return None

    def _should_capture_lead_from_subject(
        self,
        subject: str,
        email_config: TenantEmailConfig,
    ) -> bool:
        """Check if email subject matches configured lead capture prefixes.
        
        Args:
            subject: Email subject line
            email_config: Tenant email configuration
            
        Returns:
            True if lead should be captured, False otherwise
        """
        # Only use tenant-specified prefixes; no defaults.
        prefixes = email_config.lead_capture_subject_prefixes
        print(f"[LEAD_CAPTURE] Prefixes from config: {prefixes}", flush=True)
        logger.debug(f"Lead capture prefixes from config: {prefixes}")

        if prefixes is None:
            print("[LEAD_CAPTURE] No prefixes configured - skipping capture", flush=True)
            return False

        if len(prefixes) == 0:
            print("[LEAD_CAPTURE] Empty prefix list - skipping capture", flush=True)
            return False
        
        # Strip common email prefixes (Fwd:, Re:, etc.) before checking
        subject_lower = (subject or "").lower().strip()

        # Remove common email prefixes (can be stacked, e.g., "Re: Fwd: ")
        email_prefixes = ['fwd:', 're:', 'fw:', 'fyi:']
        cleaned_subject = subject_lower
        while True:
            changed = False
            for email_prefix in email_prefixes:
                if cleaned_subject.startswith(email_prefix):
                    cleaned_subject = cleaned_subject[len(email_prefix):].strip()
                    changed = True
                    break
            if not changed:
                break

        print(f"[LEAD_CAPTURE] Checking subject '{cleaned_subject}' against prefixes", flush=True)
        if cleaned_subject != subject_lower:
            print(f"[LEAD_CAPTURE] Original subject: '{subject_lower}'", flush=True)

        for prefix in prefixes:
            # Strip whitespace from prefix to handle any trailing spaces in database
            prefix_lower = (prefix or "").lower().strip()
            if cleaned_subject.startswith(prefix_lower):
                print(f"[LEAD_CAPTURE] MATCH: Subject '{subject}' matches prefix '{prefix}'", flush=True)
                logger.debug(f"Subject '{subject}' matches prefix '{prefix}'")
                return True

        print(f"[LEAD_CAPTURE] NO MATCH: Subject '{subject}' does not match any prefixes: {prefixes}", flush=True)
        logger.debug(f"Subject '{subject}' does not match any prefixes: {prefixes}")
        return False

    def _parse_booking_page_subject(self, subject: str) -> dict[str, str] | None:
        """Parse contact info from 'Email Capture from Booking Page' subject line.

        Subject format: "Email Capture from Booking Page - email@example.com - ClassName - 1234567890"

        Args:
            subject: Email subject line

        Returns:
            Dictionary with email and phone if found, or None if not a booking page email
        """
        if not subject:
            return None

        # Check if this is a booking page email
        subject_lower = subject.lower().strip()
        if not subject_lower.startswith("email capture from booking page"):
            return None

        # Split by " - " to get the parts after the prefix
        parts = subject.split(" - ")
        if len(parts) < 2:
            return None

        result = {}

        # Look for email pattern in parts
        email_pattern = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
        # Look for phone pattern (10 digits, possibly with formatting)
        phone_pattern = re.compile(r'\b(\d{10})\b|\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b')

        for part in parts[1:]:  # Skip the "Email Capture from Booking Page" prefix
            part = part.strip()

            # Check for email
            email_match = email_pattern.search(part)
            if email_match and "email" not in result:
                result["email"] = email_match.group(0).lower()
                logger.debug(f"Found email in booking page subject: {result['email']}")
                continue

            # Check for phone (10 digits)
            phone_match = phone_pattern.search(part)
            if phone_match and "phone" not in result:
                # Get the matched phone number and clean it
                raw_phone = phone_match.group(0)
                digits = re.sub(r'\D', '', raw_phone)
                if len(digits) == 10:
                    result["phone"] = f"+1{digits}"  # E.164 format
                    logger.debug(f"Found phone in booking page subject: {result['phone']}")

        if result:
            logger.info(f"Parsed booking page subject: {result}")
            return result

        return None

    def _extract_contact_info(
        self,
        from_email: str,
        sender_name: str,
        body: str,
        subject: str = "",
        is_lead_capture_email: bool = False,
    ) -> dict[str, Any] | None:
        """Extract contact info from email content using structured parser.

        Args:
            from_email: Sender email address
            sender_name: Sender name
            body: Email body text
            subject: Email subject line (used for booking page emails)
            is_lead_capture_email: If True, treat as form submission (use body data only, never sender info)

        Returns:
            Dictionary with name, email, phone, and metadata, or None if no info found
        """
        # Parse structured data from email body
        parsed = self.body_parser.parse(body)

        # For "Email Capture from Booking Page" emails, also parse the subject line
        # Subject format: "Email Capture from Booking Page - email@example.com - ClassName - 1234567890"
        subject_data = self._parse_booking_page_subject(subject)
        if subject_data:
            # Merge subject data with body parsed data (subject takes precedence for email/phone)
            if subject_data.get("email") and not parsed.get("email"):
                parsed["email"] = subject_data["email"]
            if subject_data.get("phone") and not parsed.get("phone"):
                parsed["phone"] = subject_data["phone"]
            logger.info(f"Extracted from booking page subject: email={subject_data.get('email')}, phone={subject_data.get('phone')}")
        
        # Check if we found structured form data
        # Look for form-specific fields that indicate this is a form submission
        parsed_fields = parsed.get("metadata", {}).get("parsed_fields", [])
        additional_fields = parsed.get("additional_fields", {})
        
        # Form submission indicators (fields that only appear in form submissions, not regular emails)
        form_indicators = [
            'location email', 'franchise code', 'location code', 'class code',
            'class id', 'utm source', 'utm medium', 'utm campaign',
            'hubspot cookie', 'how did you hear about us', 'type of lessons',
            'marketing opt-in', 'address'
        ]
        
        # Check if any form indicator fields are present
        has_form_indicators = any(
            indicator in parsed_fields or indicator in additional_fields
            for indicator in form_indicators
        )
        
        # Also check if we have additional fields or multiple parsed fields (suggests structured data)
        # If is_lead_capture_email is True, always treat as structured data (form submission)
        has_structured_data = bool(
            is_lead_capture_email or  # Lead capture emails are always form submissions
            has_form_indicators or
            (additional_fields and len(additional_fields) > 0) or
            (parsed_fields and len(parsed_fields) > 3)  # More than just name/email/phone
        )
        
        print(f"[EMAIL_EXTRACT] has_form_indicators={has_form_indicators}, has_structured_data={has_structured_data}", flush=True)
        print(f"[EMAIL_EXTRACT] sender_name={sender_name}, from_email={from_email}", flush=True)
        
        # Log for debugging
        logger.debug(
            f"Email parsing: has_structured_data={has_structured_data}, "
            f"has_form_indicators={has_form_indicators}, "
            f"parsed_name={parsed.get('name')}, parsed_email={parsed.get('email')}, "
            f"sender_name={sender_name}, sender_email={from_email}, "
            f"parsed_fields={parsed_fields}, additional_fields_keys={list(additional_fields.keys())}"
        )
        
        # Build result dictionary
        info: dict[str, Any] = {}
        
        # For name: Only use structured form data if found, otherwise fall back to sender name
        # This ensures form submissions use the form's name field, not the email sender's name
        if has_structured_data or has_form_indicators:
            # If we have structured form data or form indicators, only use the parsed name (don't fall back to sender)
            # This is critical: form submissions should NEVER use sender name, even if the name field wasn't found
            info["name"] = parsed.get("name")
            
            # Check if "student name" might be in additional_fields (shouldn't happen, but check just in case)
            if not info["name"] and has_form_indicators and "student name" in additional_fields:
                from app.domain.services.email_body_parser import EmailBodyParser
                temp_parser = EmailBodyParser()
                cleaned_name = temp_parser._clean_name(additional_fields["student name"])
                if cleaned_name:
                    info["name"] = cleaned_name
                    logger.info(f"Found name in additional_fields['student name']: {cleaned_name}")
            
            if not info["name"] and has_form_indicators:
                logger.warning(
                    f"Form submission detected but name field not found. "
                    f"Parsed name={parsed.get('name')}, Parsed fields: {parsed_fields}, "
                    f"Additional fields: {list(additional_fields.keys())}"
                )
        else:
            # If no structured data, use parsed name or sender name as fallback
            info["name"] = parsed.get("name") or sender_name or None
        
        # For email: Only use structured form data if found, otherwise fall back to sender email
        # This ensures form submissions use the form's email field, not the email sender's address
        if has_structured_data or has_form_indicators:
            # If we have structured form data or form indicators, only use the parsed email (don't fall back to sender)
            # This is critical: form submissions should NEVER use sender email, even if the email field wasn't found
            info["email"] = parsed.get("email")
            
            # Make absolutely sure we're not accidentally using "Location Email" - that's a different field
            # Check if "email" (without "location") is in additional_fields (shouldn't happen, but check)
            if not info["email"] and has_form_indicators:
                # Look for "email" key (not "location email")
                for key in additional_fields:
                    if key.lower() == "email" and "location" not in key.lower():
                        from app.domain.services.email_body_parser import EmailBodyParser
                        temp_parser = EmailBodyParser()
                        cleaned_email = temp_parser._clean_email(additional_fields[key])
                        if cleaned_email:
                            info["email"] = cleaned_email
                            logger.info(f"Found email in additional_fields['{key}']: {cleaned_email}")
                        break
            
            if not info["email"] and has_form_indicators:
                logger.warning(
                    f"Form submission detected but email field not found. "
                    f"Parsed email={parsed.get('email')}, Parsed fields: {parsed_fields}, "
                    f"Additional fields: {list(additional_fields.keys())}"
                )
        else:
            # If no structured data, use parsed email or sender email as fallback
            info["email"] = parsed.get("email") or from_email or None
        
        # Phone is always from parsed data (already formatted to E.164)
        info["phone"] = parsed.get("phone")
        
        # Store additional fields and metadata
        if parsed.get("additional_fields"):
            info["additional_fields"] = parsed["additional_fields"]
        if parsed.get("metadata"):
            info["metadata"] = parsed["metadata"]
        
        # Only return if we have at least one piece of contact info
        if info.get("name") or info.get("email") or info.get("phone"):
            return info
        
        return None

    def _build_email_context(
        self,
        subject: str,
        sender_name: str,
        thread_context: str,
    ) -> str:
        """Build additional context for email prompt."""
        context_parts = []
        
        if subject:
            context_parts.append(f"Email Subject: {subject}")
        
        if sender_name:
            context_parts.append(f"Sender Name: {sender_name}")
        
        if thread_context:
            context_parts.append(f"\nPrevious thread messages:\n{thread_context}")
        
        return "\n".join(context_parts)

    async def _get_email_prompt(self, tenant_id: int, context: dict | None = None) -> str:
        """Get system prompt for email responses."""
        base_prompt = await self.prompt_service.compose_prompt(tenant_id, context)
        
        email_instructions = """

## Email Response Guidelines:
1. Write in a professional email format
2. Keep responses concise but thorough
3. Address the sender by name if known
4. Do not use excessive formatting or emojis
5. End with an appropriate closing
6. If you cannot fully answer, acknowledge the question and offer to connect them with a team member
"""
        
        return base_prompt + email_instructions

    def _format_email_response(
        self,
        response: str,
        signature: str | None,
    ) -> str:
        """Format response for email."""
        # Clean up any chat-like formatting
        formatted = response.strip()
        
        # Add signature if configured
        if signature:
            formatted += f"\n\n{signature}"
        
        return formatted

    async def _send_email_response(
        self,
        gmail_client: GmailClient,
        to_email: str,
        subject: str,
        body: str,
        thread_id: str,
        email_config: TenantEmailConfig,
    ) -> dict[str, Any]:
        """Send email response via Gmail API."""
        return gmail_client.send_message(
            to=to_email,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )

    def _is_automated_email(
        self,
        sender_email: str,
        subject: str,
        body: str,
    ) -> bool:
        """Check if email is automated/no-reply."""
        # Check for common automated patterns
        automated_patterns = [
            r"noreply@",
            r"no-reply@",
            r"do-not-reply@",
            r"donotreply@",
            r"automated@",
            r"notifications@",
            r"mailer-daemon@",
            r"postmaster@",
        ]
        
        sender_lower = sender_email.lower()
        for pattern in automated_patterns:
            if re.search(pattern, sender_lower):
                return True
        
        # Check subject for auto-response patterns
        auto_subject_patterns = [
            r"auto:\s*",
            r"automatic reply",
            r"out of office",
            r"delivery status notification",
            r"undeliverable:",
            r"delivery failure",
        ]
        
        subject_lower = subject.lower()
        for pattern in auto_subject_patterns:
            if re.search(pattern, subject_lower):
                return True
        
        return False

    def _is_outgoing_message(
        self,
        message: dict[str, Any],
        our_email: str,
    ) -> bool:
        """Check if message was sent by us (and not received in INBOX).

        For self-sent emails (like booking page forms), we check if the message
        is in INBOX - if it is, we should process it even if it's from our address.
        """
        label_ids = message.get("label_ids", [])

        # If message is in INBOX, it's an incoming message we should process
        # This handles self-sent emails (from and to same address)
        if "INBOX" in label_ids:
            return False

        # If only in SENT (not INBOX), it's outgoing
        if "SENT" in label_ids:
            return True

        # Fallback: check if from our email
        from_email = message.get("from", "").lower()
        return our_email.lower() in from_email

    def _preprocess_email_body(self, body: str) -> str:
        """Preprocess email body for LLM."""
        # Truncate if too long
        if len(body) > self.MAX_BODY_LENGTH:
            body = body[:self.MAX_BODY_LENGTH] + "\n[Email truncated...]"
        
        # Remove excessive whitespace
        body = re.sub(r'\n{3,}', '\n\n', body)
        body = re.sub(r' {2,}', ' ', body)
        
        # Remove email signature delimiters and content after
        signature_patterns = [
            r'\n--\s*\n.*',  # -- signature
            r'\n_{3,}\n.*',  # ___ separator
            r'\nSent from my (?:iPhone|iPad|Android).*',
            r'\nGet Outlook for .*',
        ]
        
        for pattern in signature_patterns:
            body = re.sub(pattern, '', body, flags=re.DOTALL | re.IGNORECASE)
        
        return body.strip()

    async def _is_business_hours(self, email_config: TenantEmailConfig) -> bool:
        """Check if current time is within business hours."""
        # Reuse tenant business profile hours
        # For now, return True (implement full logic as needed)
        try:
            from datetime import datetime
            import pytz
            
            # Get tenant business profile for timezone and hours
            tenant = await self.tenant_repo.get_by_id(None, email_config.tenant_id)
            if not tenant or not tenant.business_profile:
                return True
            
            # TODO: Implement full business hours check using tenant profile
            return True
        except Exception:
            return True
