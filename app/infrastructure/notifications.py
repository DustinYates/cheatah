"""Notification service for admin alerts (SMS + Email)."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant import User
from app.persistence.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending admin notifications."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize notification service."""
        self.session = session
        self.user_repo = UserRepository(session)

    async def notify_admins(
        self,
        tenant_id: int,
        subject: str,
        message: str,
        methods: list[str] = ["email", "sms"],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Notify tenant admins of an event.
        
        Args:
            tenant_id: Tenant ID
            subject: Notification subject
            message: Notification message
            methods: Notification methods (email, sms)
            metadata: Additional metadata
            
        Returns:
            Dictionary with notification status for each method
        """
        # Get tenant admins
        users = await self.user_repo.list(tenant_id, skip=0, limit=100)
        admins = [u for u in users if u.role in ("admin", "tenant_admin")]
        
        if not admins:
            logger.warning(f"No admins found for tenant {tenant_id}")
            return {"status": "no_admins", "notifications": []}
        
        notification_results = []
        
        for admin in admins:
            admin_notifications = {}
            
            # Send email notification
            if "email" in methods and admin.email:
                try:
                    email_result = await self._send_email(
                        to=admin.email,
                        subject=subject,
                        body=message,
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
            
            # Send SMS notification (if admin has phone number)
            if "sms" in methods:
                # Note: In production, you'd need to store admin phone numbers
                # For now, we'll log that SMS notification would be sent
                logger.info(f"SMS notification would be sent to admin {admin.id} for tenant {tenant_id}")
                admin_notifications["sms"] = {
                    "status": "not_implemented",
                    "note": "Admin phone numbers not stored",
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

    async def _send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send email notification.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            
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
        
        return True

