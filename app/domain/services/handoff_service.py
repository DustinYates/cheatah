"""Handoff service for managing call transfers and escalations."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.voice_config_service import VoiceConfigService
from app.persistence.models.call import Call
from app.persistence.models.tenant_voice_config import DEFAULT_ESCALATION_RULES

logger = logging.getLogger(__name__)


@dataclass
class CallContext:
    """Context for handoff decision making."""
    call_sid: str
    tenant_id: int
    conversation_id: int | None
    current_turn: int
    transcribed_text: str
    intent: str | None = None
    confidence: float | None = None
    consecutive_low_confidence: int = 0
    user_requested_human: bool = False


@dataclass
class HandoffDecision:
    """Result of handoff evaluation."""
    should_handoff: bool
    reason: str | None = None
    handoff_mode: str | None = None
    transfer_number: str | None = None


class HandoffService:
    """Service for managing call handoffs and escalations."""

    # Phrases that indicate user wants a human
    HUMAN_REQUEST_PHRASES = [
        "speak to a human",
        "talk to someone",
        "real person",
        "manager",
        "supervisor",
        "human please",
        "not a robot",
        "speak with someone",
        "talk to a person",
        "representative",
        "agent",
        "operator",
        "speak to someone real",
        "let me talk to",
    ]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize handoff service.
        
        Args:
            session: Database session
        """
        self.session = session
        self.voice_config_service = VoiceConfigService(session)

    async def evaluate_handoff(self, context: CallContext) -> HandoffDecision:
        """Evaluate whether a call should be handed off.
        
        Args:
            context: Call context with current state
            
        Returns:
            HandoffDecision with handoff details
        """
        # Get tenant escalation rules
        escalation_rules = await self.voice_config_service.get_escalation_rules(context.tenant_id)
        handoff_config = await self.voice_config_service.get_handoff_config(context.tenant_id)
        
        # Check if voice is enabled
        if not handoff_config.get("enabled", False):
            return HandoffDecision(should_handoff=False)
        
        # Check each escalation trigger
        reason = None
        
        # 1. Caller explicitly asks for human
        if escalation_rules.get("caller_asks_human", True):
            if self._user_requesting_human(context.transcribed_text):
                reason = "caller_requested_human"
        
        # 2. Repeated confusion (low confidence multiple times)
        confusion_config = escalation_rules.get("repeated_confusion", {})
        if confusion_config.get("enabled", False) and not reason:
            threshold = confusion_config.get("threshold", 3)
            if context.consecutive_low_confidence >= threshold:
                reason = "repeated_confusion"
        
        # 3. High value intent (booking request, etc.)
        high_value_config = escalation_rules.get("high_value_intent", {})
        if high_value_config.get("enabled", False) and not reason:
            high_value_intents = high_value_config.get("intents", [])
            if context.intent and context.intent in high_value_intents:
                reason = f"high_value_intent:{context.intent}"
        
        # 4. Low confidence on current turn
        low_conf_config = escalation_rules.get("low_confidence", {})
        if low_conf_config.get("enabled", False) and not reason:
            threshold = low_conf_config.get("threshold", 0.5)
            if context.confidence is not None and context.confidence < threshold:
                reason = "low_confidence"
        
        if reason:
            return HandoffDecision(
                should_handoff=True,
                reason=reason,
                handoff_mode=handoff_config.get("mode", "take_message"),
                transfer_number=handoff_config.get("transfer_number"),
            )
        
        return HandoffDecision(should_handoff=False)

    def _user_requesting_human(self, text: str) -> bool:
        """Check if user is requesting to speak with a human.
        
        Args:
            text: Transcribed speech
            
        Returns:
            True if user wants a human
        """
        lower_text = text.lower()
        return any(phrase in lower_text for phrase in self.HUMAN_REQUEST_PHRASES)

    async def record_handoff(
        self,
        call_sid: str,
        handoff_number: str | None,
        reason: str,
    ) -> None:
        """Record that a handoff was attempted.
        
        Args:
            call_sid: Twilio call SID
            handoff_number: Number transferred to (if applicable)
            reason: Reason for handoff
        """
        stmt = select(Call).where(Call.call_sid == call_sid)
        result = await self.session.execute(stmt)
        call = result.scalar_one_or_none()
        
        if call:
            call.handoff_attempted = True
            call.handoff_number = handoff_number
            call.handoff_reason = reason
            await self.session.commit()
            logger.info(f"Recorded handoff for call {call_sid}: reason={reason}")

    def generate_transfer_twiml(
        self,
        transfer_number: str,
        announcement: str | None = None,
    ) -> str:
        """Generate TwiML for live transfer.
        
        Args:
            transfer_number: Phone number to transfer to
            announcement: Optional announcement before transfer
            
        Returns:
            TwiML XML string
        """
        announcement_text = announcement or (
            "I'm connecting you with a team member now. Please hold."
        )
        
        # Escape XML special characters
        escaped_announcement = (
            announcement_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{escaped_announcement}</Say>
    <Dial>{transfer_number}</Dial>
    <Say>I'm sorry, but we couldn't connect you at this time. Please try calling back later. Goodbye.</Say>
    <Hangup/>
</Response>'''

    def generate_take_message_twiml(
        self,
        message: str | None = None,
        max_length: int = 300,
    ) -> str:
        """Generate TwiML for taking a message (voicemail).
        
        Args:
            message: Custom message before recording
            max_length: Maximum recording length in seconds
            
        Returns:
            TwiML XML string
        """
        message_text = message or (
            "I understand you'd like to speak with someone on our team. "
            "Please leave a message after the tone, including your name and phone number, "
            "and we'll get back to you as soon as possible."
        )
        
        # Escape XML special characters
        escaped_message = (
            message_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{escaped_message}</Say>
    <Record maxLength="{max_length}" finishOnKey="#"/>
    <Say>Thank you for your message. We'll contact you soon. Goodbye.</Say>
    <Hangup/>
</Response>'''

    def generate_schedule_callback_twiml(
        self,
        message: str | None = None,
    ) -> str:
        """Generate TwiML for scheduling a callback.
        
        Note: This is a simplified version. Full implementation would
        integrate with a scheduling system.
        
        Args:
            message: Custom message
            
        Returns:
            TwiML XML string
        """
        message_text = message or (
            "I understand you'd like to schedule a callback. "
            "One of our team members will call you back at this number as soon as possible. "
            "Thank you for your patience. Goodbye!"
        )
        
        # Escape XML special characters
        escaped_message = (
            message_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{escaped_message}</Say>
    <Hangup/>
</Response>'''

    async def execute_handoff(
        self,
        call_sid: str,
        decision: HandoffDecision,
        tenant_id: int,
    ) -> str:
        """Execute the handoff based on the decision.
        
        Args:
            call_sid: Twilio call SID
            decision: Handoff decision with mode and details
            tenant_id: Tenant ID
            
        Returns:
            TwiML XML string for the handoff
        """
        # Record the handoff
        await self.record_handoff(
            call_sid=call_sid,
            handoff_number=decision.transfer_number,
            reason=decision.reason or "unknown",
        )
        
        # Get tenant-specific messaging
        greeting_config = await self.voice_config_service.get_greeting_and_disclosure(tenant_id)
        
        # Generate appropriate TwiML based on mode
        if decision.handoff_mode == "live_transfer" and decision.transfer_number:
            return self.generate_transfer_twiml(
                transfer_number=decision.transfer_number,
            )
        elif decision.handoff_mode == "schedule_callback":
            return self.generate_schedule_callback_twiml()
        else:
            # Default to take_message / voicemail
            return self.generate_take_message_twiml()

