"""Escalation service for detecting and handling escalations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.intent_detector import IntentDetector, IntentResult
from app.infrastructure.notifications import NotificationService
from app.persistence.models.escalation import Escalation
from app.persistence.repositories.base import BaseRepository


class EscalationService:
    """Service for managing escalations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize escalation service."""
        self.session = session
        self.intent_detector = IntentDetector()
        self.notification_service = NotificationService(session)
        self.escalation_repo = BaseRepository(Escalation, session)

    async def check_and_escalate(
        self,
        tenant_id: int,
        conversation_id: int | None,
        user_message: str,
        llm_response: str | None = None,
        confidence_score: float | None = None,
    ) -> Escalation | None:
        """Check if escalation is needed and create escalation record.
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID (optional)
            user_message: User message that triggered check
            llm_response: LLM response (for confidence checking)
            confidence_score: Explicit confidence score (if available)
            
        Returns:
            Escalation record if created, None otherwise
        """
        # Detect intent
        intent_result = self.intent_detector.detect_intent(user_message)
        
        # Check if escalation is needed
        should_escalate = False
        reason = "unknown"
        
        # Explicit human handoff request
        if self.intent_detector.requires_escalation(intent_result):
            should_escalate = True
            reason = "explicit_request"
        
        # Low confidence (if provided)
        if confidence_score is not None and confidence_score < 0.5:
            should_escalate = True
            reason = "low_confidence"
        
        # Check for explicit escalation keywords in user message
        escalation_keywords = [
            "speak to human", "talk to person", "real person", "agent",
            "representative", "manager", "supervisor", "escalate"
        ]
        message_lower = user_message.lower()
        if any(keyword in message_lower for keyword in escalation_keywords):
            should_escalate = True
            reason = "explicit_request"
        
        if not should_escalate:
            return None
        
        # Create escalation record
        escalation = await self.escalation_repo.create(
            tenant_id,
            conversation_id=conversation_id,
            reason=reason,
            status="pending",
            confidence_score=str(confidence_score) if confidence_score else None,
            trigger_message=user_message,
        )
        
        # Notify admins
        await self._notify_admins(tenant_id, escalation)
        
        return escalation

    async def _notify_admins(
        self,
        tenant_id: int,
        escalation: Escalation,
    ) -> None:
        """Notify admins of escalation.
        
        Args:
            tenant_id: Tenant ID
            escalation: Escalation record
        """
        subject = f"Escalation Required - Tenant {tenant_id}"
        message = (
            f"An escalation has been requested.\n\n"
            f"Reason: {escalation.reason}\n"
            f"Conversation ID: {escalation.conversation_id}\n"
            f"Trigger Message: {escalation.trigger_message}\n"
            f"Escalation ID: {escalation.id}"
        )
        
        notification_result = await self.notification_service.notify_admins(
            tenant_id=tenant_id,
            subject=subject,
            message=message,
            methods=["email", "sms"],
            metadata={"escalation_id": escalation.id},
        )
        
        # Update escalation with notification status
        escalation.admin_notified_at = datetime.now(timezone.utc)
        escalation.notification_methods = [n["notifications"] for n in notification_result.get("notifications", [])]
        escalation.notification_status = notification_result
        
        await self.session.commit()
        await self.session.refresh(escalation)

    async def resolve_escalation(
        self,
        tenant_id: int,
        escalation_id: int,
        resolved_by: int,
        resolution_notes: str | None = None,
    ) -> Escalation | None:
        """Resolve an escalation.
        
        Args:
            tenant_id: Tenant ID
            escalation_id: Escalation ID
            resolved_by: User ID who resolved it
            resolution_notes: Optional resolution notes
            
        Returns:
            Updated escalation or None if not found
        """
        escalation = await self.escalation_repo.get_by_id(tenant_id, escalation_id)
        if not escalation:
            return None
        
        escalation.status = "resolved"
        escalation.resolved_at = datetime.now(timezone.utc)
        escalation.resolved_by = resolved_by
        escalation.resolution_notes = resolution_notes
        
        await self.session.commit()
        await self.session.refresh(escalation)
        
        return escalation

