"""Notification service for admin alerts (SMS + Email + In-App)."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.notification import Notification, NotificationPriority, NotificationType
from app.persistence.models.tenant import User
from app.persistence.repositories.user_repository import UserRepository
from app.settings import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending admin notifications via multiple channels."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize notification service."""
        self.session = session
        self.user_repo = UserRepository(session)

    async def notify_admins(
        self,
        tenant_id: int,
        subject: str,
        message: str,
        methods: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        notification_type: str = NotificationType.SYSTEM,
        priority: str = NotificationPriority.NORMAL,
        action_url: str | None = None,
    ) -> dict[str, Any]:
        """Notify tenant admins of an event.
        
        Args:
            tenant_id: Tenant ID
            subject: Notification subject
            message: Notification message
            methods: Notification methods (email, sms, in_app). Defaults to ["email", "in_app"]
            metadata: Additional metadata
            notification_type: Type of notification (call_summary, escalation, etc.)
            priority: Priority level (low, normal, high, urgent)
            action_url: Optional deep link URL within the app
            
        Returns:
            Dictionary with notification status for each method
        """
        if methods is None:
            methods = ["email", "in_app"]

        # Load escalation settings to check if enabled and respect quiet_hours
        escalation_settings = await self._get_escalation_settings(tenant_id)

        # If escalation notifications are disabled, skip
        if notification_type in (NotificationType.ESCALATION, NotificationType.HANDOFF):
            if not escalation_settings.get("enabled", True):
                logger.info(f"Escalation notifications disabled for tenant {tenant_id}")
                return {"status": "disabled", "notifications": []}

            # Override methods with escalation-configured methods
            methods = escalation_settings.get("notification_methods", methods)

        # Check quiet hours for escalation notifications
        if notification_type in (NotificationType.ESCALATION, NotificationType.HANDOFF):
            if await self._is_quiet_hours(escalation_settings):
                logger.info(f"Quiet hours active for tenant {tenant_id}, skipping escalation notifications")
                return {"status": "quiet_hours", "notifications": []}

        # Get tenant admins
        users = await self.user_repo.list(tenant_id, skip=0, limit=100)
        admins = [u for u in users if u.role in ("admin", "tenant_admin")]

        if not admins:
            logger.warning(f"No admins found for tenant {tenant_id}")
            return {"status": "no_admins", "notifications": []}

        notification_results = []
        
        for admin in admins:
            admin_notifications = {}
            
            # Create in-app notification
            if "in_app" in methods:
                try:
                    in_app_result = await self._create_in_app_notification(
                        tenant_id=tenant_id,
                        user_id=admin.id,
                        title=subject,
                        message=message,
                        notification_type=notification_type,
                        priority=priority,
                        extra_data=metadata,
                        action_url=action_url,
                    )
                    admin_notifications["in_app"] = {
                        "status": "created" if in_app_result else "failed",
                        "notification_id": in_app_result.id if in_app_result else None,
                    }
                except Exception as e:
                    logger.error(f"Failed to create in-app notification for user {admin.id}: {e}", exc_info=True)
                    admin_notifications["in_app"] = {
                        "status": "error",
                        "error": str(e),
                    }
            
            # Send email notification
            if "email" in methods and admin.email:
                try:
                    email_result = await self._send_email(
                        to=admin.email,
                        subject=subject,
                        body=message,
                        metadata=metadata,
                    )
                    admin_notifications["email"] = {
                        "status": "sent" if email_result else "failed",
                        "address": admin.email,
                    }
                except Exception as e:
                    logger.error(f"Failed to send email to {admin.email}: {e}", exc_info=True)
                    admin_notifications["email"] = {
                        "status": "error",
                        "address": admin.email,
                        "error": str(e),
                    }
            
            # Send SMS notification
            if "sms" in methods:
                try:
                    sms_result = await self._send_sms_notification(
                        tenant_id=tenant_id,
                        user_id=admin.id,
                        message=f"{subject}: {message[:140]}",  # Truncate for SMS
                    )
                    admin_notifications["sms"] = sms_result
                except Exception as e:
                    logger.error(f"Failed to send SMS to admin {admin.id}: {e}", exc_info=True)
                    admin_notifications["sms"] = {
                        "status": "error",
                        "error": str(e),
                    }
            
            notification_results.append({
                "admin_id": admin.id,
                "admin_email": admin.email,
                "notifications": admin_notifications,
            })
        
        return {
            "status": "sent",
            "notifications": notification_results,
        }

    async def notify_call_summary(
        self,
        tenant_id: int,
        call_id: int,
        summary_text: str,
        intent: str | None,
        outcome: str | None,
        caller_phone: str,
        recording_url: str | None = None,
        methods: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send notification for a completed call summary.
        
        Args:
            tenant_id: Tenant ID
            call_id: Call ID
            summary_text: Summary of the call
            intent: Detected intent
            outcome: Call outcome
            caller_phone: Caller's phone number
            recording_url: URL to call recording
            methods: Notification methods
            
        Returns:
            Notification result
        """
        subject = f"Call Summary - {outcome or 'Completed'}"
        
        message = (
            f"New call from {caller_phone}\n\n"
            f"Summary: {summary_text}\n"
        )
        if intent:
            message += f"Intent: {intent.replace('_', ' ').title()}\n"
        if outcome:
            message += f"Outcome: {outcome.replace('_', ' ').title()}\n"
        if recording_url:
            message += f"\nRecording available at: {recording_url}"
        
        metadata = {
            "call_id": call_id,
            "intent": intent,
            "outcome": outcome,
            "caller_phone": caller_phone,
            "recording_url": recording_url,
        }
        
        # Determine priority based on outcome
        priority = NotificationPriority.NORMAL
        if outcome in ("booking_requested", "lead_created"):
            priority = NotificationPriority.HIGH
        
        return await self.notify_admins(
            tenant_id=tenant_id,
            subject=subject,
            message=message,
            methods=methods,
            metadata=metadata,
            notification_type=NotificationType.CALL_SUMMARY,
            priority=priority,
            action_url=f"/calls/{call_id}",
        )

    async def notify_handoff(
        self,
        tenant_id: int,
        call_id: int,
        reason: str,
        caller_phone: str,
        handoff_mode: str,
        transfer_number: str | None = None,
        caller_name: str | None = None,
        caller_email: str | None = None,
        methods: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send notification for a call handoff.

        Args:
            tenant_id: Tenant ID
            call_id: Call ID
            reason: Reason for handoff
            caller_phone: Caller's phone number
            handoff_mode: Type of handoff (live_transfer, take_message, etc.)
            transfer_number: Number transferred to (if applicable)
            caller_name: Caller's name (if known)
            caller_email: Caller's email (if known)
            methods: Notification methods

        Returns:
            Notification result
        """
        subject = f"[URGENT] Call Handoff - {reason.replace('_', ' ').title()}"

        # Build caller info string
        if caller_name:
            caller_info = f"{caller_name} ({caller_phone})"
        else:
            caller_info = caller_phone

        message = f"A caller is requesting human assistance.\n\n"
        message += f"Caller: {caller_info}\n"
        if caller_email:
            message += f"Email: {caller_email}\n"
        message += f"Phone: {caller_phone}\n"
        message += f"Reason: {reason.replace('_', ' ').title()}\n"
        message += f"Handoff Mode: {handoff_mode.replace('_', ' ').title()}\n"
        if transfer_number:
            message += f"Transferred to: {transfer_number}\n"
        message += "\nPlease respond promptly."

        metadata = {
            "call_id": call_id,
            "reason": reason,
            "caller_phone": caller_phone,
            "caller_name": caller_name,
            "caller_email": caller_email,
            "handoff_mode": handoff_mode,
            "transfer_number": transfer_number,
        }
        
        return await self.notify_admins(
            tenant_id=tenant_id,
            subject=subject,
            message=message,
            methods=methods,
            metadata=metadata,
            notification_type=NotificationType.HANDOFF,
            priority=NotificationPriority.HIGH,
            action_url=f"/calls/{call_id}",
        )

    async def notify_voicemail(
        self,
        tenant_id: int,
        call_id: int,
        caller_phone: str,
        recording_url: str | None = None,
        methods: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send notification for a new voicemail.
        
        Args:
            tenant_id: Tenant ID
            call_id: Call ID
            caller_phone: Caller's phone number
            recording_url: URL to voicemail recording
            methods: Notification methods
            
        Returns:
            Notification result
        """
        subject = "New Voicemail"
        
        message = f"You have a new voicemail from {caller_phone}.\n"
        if recording_url:
            message += f"\nListen at: {recording_url}"
        
        metadata = {
            "call_id": call_id,
            "caller_phone": caller_phone,
            "recording_url": recording_url,
        }
        
        return await self.notify_admins(
            tenant_id=tenant_id,
            subject=subject,
            message=message,
            methods=methods,
            metadata=metadata,
            notification_type=NotificationType.VOICEMAIL,
            priority=NotificationPriority.NORMAL,
            action_url=f"/calls/{call_id}",
        )

    async def notify_email_promise(
        self,
        tenant_id: int,
        customer_name: str | None,
        customer_phone: str | None,
        customer_email: str | None,
        conversation_id: int | None = None,
        channel: str = "chat",
        topic: str | None = None,
    ) -> dict[str, Any]:
        """Alert tenant when bot promises to email a customer.

        Sends SMS to business owner with customer contact info so they
        can follow up manually (since the bot cannot send emails).

        Args:
            tenant_id: Tenant ID
            customer_name: Customer's name (if known)
            customer_phone: Customer's phone number (if known)
            customer_email: Customer's email address (if known)
            conversation_id: Conversation ID for tracking
            channel: Channel where promise was made ("chat", "voice", or "sms")
            topic: What the customer wanted (registration, pricing, schedule, etc.)

        Returns:
            Notification result
        """
        # Build alert message with customer info and what they wanted
        contact_info = customer_email or customer_phone or "Unknown"

        # Format: "John wants registration info emailed to john@email.com"
        # or: "Customer wants pricing emailed to +1234567890"
        customer_label = customer_name or "Customer"
        topic_label = f" {topic}" if topic else ""

        message = f"{customer_label} wants{topic_label} emailed to {contact_info}"

        metadata = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "conversation_id": conversation_id,
            "channel": channel,
            "topic": topic,
        }

        logger.info(
            f"Sending email promise alert - tenant_id={tenant_id}, "
            f"customer={customer_name or 'Unknown'}, contact={contact_info}, "
            f"channel={channel}, topic={topic or 'general'}"
        )

        return await self.notify_admins(
            tenant_id=tenant_id,
            subject="Email Promise Alert",
            message=message,
            methods=["sms"],  # SMS only per requirements
            metadata=metadata,
            notification_type=NotificationType.EMAIL_PROMISE,
            priority=NotificationPriority.HIGH,
        )

    async def notify_high_intent_lead(
        self,
        tenant_id: int,
        customer_name: str | None,
        customer_phone: str | None,
        customer_email: str | None,
        channel: str,
        message_preview: str,
        confidence: float,
        keywords: list[str],
        conversation_id: int | None = None,
        lead_id: int | None = None,
    ) -> dict[str, Any]:
        """Alert tenant when a high enrollment intent lead is detected.

        Sends SMS to business owner or configured notification phone when
        the AI detects strong enrollment signals in a conversation.

        Args:
            tenant_id: Tenant ID
            customer_name: Customer's name (if known)
            customer_phone: Customer's phone number (if known)
            customer_email: Customer's email address (if known)
            channel: Channel where intent was detected ("chat", "voice", "sms", "email")
            message_preview: Snippet of the message showing intent
            confidence: Intent confidence score (0.0 to 1.0)
            keywords: Keywords that triggered the detection
            conversation_id: Conversation ID for tracking
            lead_id: Lead ID if created

        Returns:
            Notification result
        """
        # Deduplicate: only send one lead notification per conversation
        if conversation_id:
            existing = await self.session.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.notification_type == NotificationType.HIGH_INTENT_LEAD,
                    Notification.extra_data["conversation_id"].astext == str(conversation_id),
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                logger.debug(f"Lead notification already sent for conversation {conversation_id}")
                return {"status": "already_sent", "reason": "duplicate_conversation"}

        # Get lead notification settings from SMS config
        lead_notification_settings = await self._get_lead_notification_settings(tenant_id)

        if not lead_notification_settings.get("enabled", False):
            logger.debug(f"Lead notifications disabled for tenant {tenant_id}")
            return {"status": "disabled", "reason": "lead_notifications_disabled"}

        # Check if this channel is being monitored
        monitored_channels = lead_notification_settings.get("channels", ["sms", "chat", "voice", "email"])
        if channel not in monitored_channels:
            logger.debug(f"Channel {channel} not monitored for tenant {tenant_id}")
            return {"status": "skipped", "reason": f"channel_{channel}_not_monitored"}

        # Check quiet hours (9 PM - 8 AM default)
        if lead_notification_settings.get("quiet_hours_enabled", True):
            if await self._is_lead_notification_quiet_hours(tenant_id, lead_notification_settings):
                logger.info(f"Quiet hours active for tenant {tenant_id}, skipping lead notification")
                return {"status": "quiet_hours", "reason": "outside_notification_hours"}

        # Build notification message
        customer_label = customer_name or "Unknown Customer"
        contact_info = customer_phone or customer_email or "No contact info"

        # Format: "Hot Lead! John via Chat: "I want to sign up my 4 year old" Phone: +1234567890"
        message = f"Hot Lead! {customer_label} via {channel.title()}:\n"
        message += f'"{message_preview[:100]}"\n'
        if customer_phone:
            message += f"Phone: {customer_phone}"
        elif customer_email:
            message += f"Email: {customer_email}"

        metadata = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "channel": channel,
            "message_preview": message_preview,
            "confidence": confidence,
            "keywords": keywords,
            "conversation_id": conversation_id,
            "lead_id": lead_id,
        }

        logger.info(
            f"Sending high intent lead alert - tenant_id={tenant_id}, "
            f"customer={customer_name or 'Unknown'}, channel={channel}, "
            f"confidence={confidence:.2f}, keywords={keywords}"
        )

        # Send SMS directly to configured phone (bypass admin lookup)
        result = await self._send_lead_notification_sms(
            tenant_id=tenant_id,
            message=message,
            lead_notification_settings=lead_notification_settings,
        )

        # Create in-app notification record (serves as dedup marker + audit trail)
        try:
            notification = Notification(
                tenant_id=tenant_id,
                user_id=None,  # Tenant-wide, not user-specific
                notification_type=NotificationType.HIGH_INTENT_LEAD,
                title=f"Hot Lead: {customer_label} via {channel.title()}",
                message=message,
                extra_data=metadata,
                priority=NotificationPriority.HIGH,
                is_read=False,
            )
            self.session.add(notification)
            await self.session.commit()
            logger.debug(f"Created lead notification record for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to create lead notification record: {e}", exc_info=True)

        return {
            "status": result.get("status", "error"),
            "notification_type": NotificationType.HIGH_INTENT_LEAD,
            "metadata": metadata,
            "sms_result": result,
        }

    async def notify_booking(
        self,
        tenant_id: int,
        customer_name: str,
        customer_phone: str | None,
        slot_start: "datetime",
        slot_end: "datetime",
        topic: str = "Meeting",
    ) -> dict[str, Any]:
        """Send SMS notification when a customer books a calendar meeting.

        Uses the notification phone and quiet hours settings from SMS Settings
        (lead notification config). The booking_notification_enabled flag is
        checked by the caller (calendar_service) before invoking this.

        Args:
            tenant_id: Tenant ID
            customer_name: Customer's name
            customer_phone: Customer's phone (if known)
            slot_start: Booking start time
            slot_end: Booking end time
            topic: Meeting topic

        Returns:
            Notification result dict
        """
        # Reuse lead notification settings for phone + quiet hours
        lead_settings = await self._get_lead_notification_settings(tenant_id)

        notification_phone = lead_settings.get("phone")
        if not notification_phone:
            # Fall back to checking business profile (same as lead notifications)
            logger.debug(f"No notification phone override for tenant {tenant_id}, will use business profile fallback")

        # Check quiet hours
        if lead_settings.get("quiet_hours_enabled", True):
            if await self._is_lead_notification_quiet_hours(tenant_id, lead_settings):
                logger.info(f"Quiet hours active for tenant {tenant_id}, skipping booking notification")
                return {"status": "quiet_hours", "reason": "outside_notification_hours"}

        # Format booking time for SMS
        try:
            from zoneinfo import ZoneInfo
            from app.persistence.models.tenant_sms_config import TenantSmsConfig as _SmsConfig

            stmt = select(_SmsConfig).where(_SmsConfig.tenant_id == tenant_id)
            result = await self.session.execute(stmt)
            sms_cfg = result.scalar_one_or_none()
            tz_str = (sms_cfg.timezone if sms_cfg else None) or "America/Chicago"
            tz = ZoneInfo(tz_str)
        except Exception:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/Chicago")

        local_start = slot_start.astimezone(tz) if slot_start.tzinfo else slot_start
        time_str = local_start.strftime("%b %d, %I:%M %p")

        # Build SMS message (max 160 chars)
        display_name = customer_name if customer_name and customer_name != "Customer" else "A new customer"
        message = f"New Booking! {display_name} booked {time_str}."
        if topic and topic != "Meeting":
            message += f" Topic: {topic}."
        if customer_phone:
            message += f"\nPhone: {customer_phone}"

        logger.info(
            f"Sending booking notification - tenant_id={tenant_id}, "
            f"customer={customer_name}, time={time_str}"
        )

        sms_result = await self._send_lead_notification_sms(
            tenant_id=tenant_id,
            message=message,
            lead_notification_settings=lead_settings,
        )

        # Create in-app notification record
        try:
            notification = Notification(
                tenant_id=tenant_id,
                user_id=None,
                notification_type=NotificationType.BOOKING_CONFIRMED,
                title=f"New Booking: {customer_name}",
                message=message,
                extra_data={
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "slot_start": slot_start.isoformat(),
                    "slot_end": slot_end.isoformat(),
                    "topic": topic,
                },
                priority=NotificationPriority.HIGH,
                is_read=False,
            )
            self.session.add(notification)
            await self.session.commit()
        except Exception as e:
            logger.error(f"Failed to create booking notification record: {e}", exc_info=True)

        return {
            "status": sms_result.get("status", "error"),
            "notification_type": NotificationType.BOOKING_CONFIRMED,
            "sms_result": sms_result,
        }

    async def _get_lead_notification_settings(self, tenant_id: int) -> dict:
        """Get lead notification settings from tenant SMS config.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dict with lead notification settings (enabled, phone, channels, quiet_hours_enabled)
        """
        from app.persistence.models.tenant_sms_config import TenantSmsConfig

        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        if not sms_config:
            return {"enabled": False}

        # Lead notification settings are stored in the settings JSON column
        settings_json = sms_config.settings or {}
        if isinstance(settings_json, str):
            import json
            settings_json = json.loads(settings_json)

        return {
            "enabled": settings_json.get("lead_notification_enabled", False),
            "phone": settings_json.get("lead_notification_phone"),
            "channels": settings_json.get("lead_notification_channels", ["sms", "chat", "voice", "email"]),
            "quiet_hours_enabled": settings_json.get("lead_notification_quiet_hours_enabled", True),
        }

    async def _is_lead_notification_quiet_hours(
        self,
        tenant_id: int,
        lead_notification_settings: dict,
    ) -> bool:
        """Check if current time is within quiet hours for lead notifications.

        Uses fixed quiet hours: 9 PM - 8 AM in tenant's timezone.

        Args:
            tenant_id: Tenant ID
            lead_notification_settings: Lead notification settings

        Returns:
            True if currently in quiet hours
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Get tenant timezone from SMS config
        from app.persistence.models.tenant_sms_config import TenantSmsConfig

        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        timezone_str = "America/Chicago"  # Default
        if sms_config:
            timezone_str = sms_config.timezone or "America/Chicago"

        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            logger.warning(f"Invalid timezone: {timezone_str}, using America/Chicago")
            tz = ZoneInfo("America/Chicago")

        now = datetime.now(tz)
        current_hour = now.hour

        # Quiet hours: 9 PM (21:00) to 8 AM (08:00)
        # In quiet hours if hour >= 21 OR hour < 8
        return current_hour >= 21 or current_hour < 8

    async def _send_lead_notification_sms(
        self,
        tenant_id: int,
        message: str,
        lead_notification_settings: dict,
    ) -> dict[str, Any]:
        """Send SMS notification to the configured lead notification phone.

        Args:
            tenant_id: Tenant ID
            message: SMS message
            lead_notification_settings: Lead notification settings (contains phone override)

        Returns:
            Result dictionary with status and details
        """
        from app.persistence.models.tenant_sms_config import TenantSmsConfig
        from app.persistence.models.tenant import TenantBusinessProfile
        from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

        # Get SMS config for Telnyx credentials
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        if not sms_config:
            logger.warning(f"No SMS config for tenant {tenant_id}, cannot send lead notification")
            return {"status": "not_configured", "note": "Tenant SMS not configured"}

        # Determine destination phone:
        # 1. First check lead_notification_phone override
        # 2. Fall back to business profile phone
        to_number = lead_notification_settings.get("phone")

        if not to_number:
            # Get business profile phone
            stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
            result = await self.session.execute(stmt)
            business_profile = result.scalar_one_or_none()

            if business_profile:
                to_number = business_profile.phone_number

        if not to_number:
            logger.warning(f"No phone number for lead notification - tenant {tenant_id}")
            return {"status": "no_phone", "note": "No notification phone configured"}

        # Get Telnyx config
        from_number = sms_config.telnyx_phone_number
        api_key = sms_config.telnyx_api_key
        messaging_profile_id = sms_config.telnyx_messaging_profile_id

        if not from_number or not api_key:
            logger.warning(f"No Telnyx config for tenant {tenant_id}, cannot send lead notification")
            return {"status": "not_configured", "note": "Telnyx SMS not configured"}

        # Format destination phone number (ensure E.164 format)
        if not to_number.startswith("+"):
            to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

        try:
            telnyx_provider = TelnyxSmsProvider(
                api_key=api_key,
                messaging_profile_id=messaging_profile_id,
            )

            sms_result = await telnyx_provider.send_sms(
                to=to_number,
                from_=from_number,
                body=message[:160],  # SMS character limit
            )

            logger.info(
                f"Lead notification SMS sent - tenant_id={tenant_id}, "
                f"to={to_number}, message_id={sms_result.message_id}"
            )

            return {
                "status": "sent",
                "message_id": sms_result.message_id,
                "to": to_number,
                "provider": "telnyx",
            }

        except Exception as e:
            logger.error(f"Failed to send lead notification SMS: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "to": to_number}

    async def _create_in_app_notification(
        self,
        tenant_id: int,
        user_id: int,
        title: str,
        message: str,
        notification_type: str = NotificationType.SYSTEM,
        priority: str = NotificationPriority.NORMAL,
        extra_data: dict[str, Any] | None = None,
        action_url: str | None = None,
    ) -> Notification:
        """Create an in-app notification.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            priority: Priority level
            extra_data: Additional data for the notification
            action_url: Optional deep link URL
            
        Returns:
            Created Notification
        """
        notification = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            extra_data=extra_data,
            priority=priority,
            action_url=action_url,
            is_read=False,
        )
        
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        
        logger.info(f"Created in-app notification {notification.id} for user {user_id}")
        return notification

    async def _send_email(
        self,
        to: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send email notification.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            metadata: Additional metadata for templating
            
        Returns:
            True if sent successfully
            
        Note:
            This is a stub implementation. In production, integrate with
            SendGrid, SES, or similar email service.
        """
        # Stub: Log email that would be sent
        logger.info(f"Email notification: To={to}, Subject={subject}, Body={body[:100]}...")
        
        # In production, implement actual email sending:
        # - Use SendGrid, AWS SES, or GCP SendGrid
        # - Handle errors and retries
        # - Track delivery status
        # - Use HTML templates for rich emails
        
        return True

    async def _send_sms_notification(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
    ) -> dict[str, Any]:
        """Send SMS notification to the business owner.

        Uses the tenant's business profile phone number as the destination
        and Telnyx SMS provider to send the notification.

        Args:
            tenant_id: Tenant ID
            user_id: User ID to notify (used for logging)
            message: SMS message (will be truncated to 160 chars)

        Returns:
            Result dictionary with status and details
        """
        from app.persistence.models.tenant_sms_config import TenantSmsConfig
        from app.persistence.models.tenant import TenantBusinessProfile
        from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

        # Get tenant's business profile to get the destination phone number
        stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        business_profile = result.scalar_one_or_none()

        if not business_profile or not business_profile.phone_number:
            logger.warning(f"No business profile phone for tenant {tenant_id}, cannot send SMS notification")
            return {
                "status": "no_phone",
                "note": "Business profile phone number not configured",
            }

        # Get tenant SMS config for Telnyx credentials
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        if not sms_config:
            logger.warning(f"No SMS config for tenant {tenant_id}, cannot send SMS notification")
            return {
                "status": "not_configured",
                "note": "Tenant SMS not configured",
            }

        # Determine the sender phone number and API key (prefer Telnyx)
        from_number = sms_config.telnyx_phone_number
        api_key = sms_config.telnyx_api_key
        messaging_profile_id = sms_config.telnyx_messaging_profile_id

        if not from_number or not api_key:
            logger.warning(f"No Telnyx config for tenant {tenant_id}, cannot send SMS notification")
            return {
                "status": "not_configured",
                "note": "Telnyx SMS not configured for tenant",
            }

        # Check for alert_phone_override in escalation settings
        escalation_settings = await self._get_escalation_settings(tenant_id)
        to_number = escalation_settings.get("alert_phone_override") or business_profile.phone_number

        if not to_number:
            logger.warning(f"No phone number for tenant {tenant_id} SMS notification")
            return {
                "status": "no_phone",
                "note": "No phone number configured (business profile or override)",
            }

        # Format destination phone number (ensure E.164 format)
        if not to_number.startswith("+"):
            # Assume US number if no country code
            to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

        # Send SMS via Telnyx
        try:
            telnyx_provider = TelnyxSmsProvider(
                api_key=api_key,
                messaging_profile_id=messaging_profile_id,
            )

            sms_result = await telnyx_provider.send_sms(
                to=to_number,
                from_=from_number,
                body=message[:160],  # SMS character limit
            )

            logger.info(
                f"SMS notification sent to business owner - tenant_id={tenant_id}, "
                f"to={to_number}, message_id={sms_result.message_id}, status={sms_result.status}"
            )

            return {
                "status": "sent",
                "message_id": sms_result.message_id,
                "to": to_number,
                "provider": "telnyx",
            }

        except Exception as e:
            logger.error(f"Failed to send SMS notification via Telnyx: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "to": to_number,
            }

    async def get_unread_notifications(
        self,
        tenant_id: int,
        user_id: int,
        limit: int = 50,
    ) -> list[Notification]:
        """Get unread notifications for a user.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            limit: Maximum number to return
            
        Returns:
            List of unread Notification objects
        """
        stmt = (
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_notifications(
        self,
        tenant_id: int,
        user_id: int,
        limit: int = 50,
        include_read: bool = True,
    ) -> list[Notification]:
        """Get notifications for a user.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            limit: Maximum number to return
            include_read: Include read notifications
            
        Returns:
            List of Notification objects
        """
        stmt = (
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        
        if not include_read:
            stmt = stmt.where(Notification.is_read == False)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_notification_read(
        self,
        tenant_id: int,
        user_id: int,
        notification_id: int,
    ) -> bool:
        """Mark a notification as read.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            notification_id: Notification ID
            
        Returns:
            True if marked, False if not found
        """
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        notification = result.scalar_one_or_none()
        
        if not notification:
            return False
        
        notification.mark_as_read()
        await self.session.commit()
        return True

    async def mark_all_notifications_read(
        self,
        tenant_id: int,
        user_id: int,
    ) -> int:
        """Mark all notifications as read for a user.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            
        Returns:
            Number of notifications marked as read
        """
        from sqlalchemy import update
        
        stmt = (
            update(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def get_unread_count(
        self,
        tenant_id: int,
        user_id: int,
    ) -> int:
        """Get count of unread notifications for a user.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID
            
        Returns:
            Number of unread notifications
        """
        from sqlalchemy import func
        
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _get_escalation_settings(self, tenant_id: int) -> dict:
        """Get escalation settings for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dict with escalation settings (enabled, notification_methods, quiet_hours, etc.)
        """
        from sqlalchemy import select
        from app.persistence.models.tenant_prompt_config import TenantPromptConfig

        stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        prompt_config = result.scalar_one_or_none()

        if not prompt_config or not prompt_config.config_json:
            # Return defaults
            return {
                "enabled": True,
                "notification_methods": ["email", "sms", "in_app"],
                "quiet_hours": {"enabled": False},
                "alert_phone_override": None,
            }

        config = prompt_config.config_json
        if isinstance(config, str):
            import json
            config = json.loads(config)

        return config.get("escalation_settings", {
            "enabled": True,
            "notification_methods": ["email", "sms", "in_app"],
            "quiet_hours": {"enabled": False},
            "alert_phone_override": None,
        })

    async def _is_quiet_hours(self, escalation_settings: dict) -> bool:
        """Check if current time is within quiet hours.

        Args:
            escalation_settings: Escalation settings dict

        Returns:
            True if currently in quiet hours
        """
        quiet_hours = escalation_settings.get("quiet_hours", {})

        if not quiet_hours.get("enabled", False):
            return False

        from datetime import datetime
        from zoneinfo import ZoneInfo

        timezone_str = quiet_hours.get("timezone", "America/Chicago")
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            logger.warning(f"Invalid timezone: {timezone_str}, using UTC")
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        current_day = now.strftime("%A").lower()

        # Check if today is in quiet_hours days
        quiet_days = quiet_hours.get("days", [])
        if current_day not in [d.lower() for d in quiet_days]:
            return False

        # Parse time strings
        start_time = quiet_hours.get("start_time", "22:00")
        end_time = quiet_hours.get("end_time", "07:00")

        current_time = now.strftime("%H:%M")

        # Handle overnight ranges (e.g., 22:00 to 07:00)
        if start_time > end_time:
            return current_time >= start_time or current_time < end_time
        else:
            return start_time <= current_time < end_time
