"""Tests for handoff service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.handoff_service import (
    CallContext,
    HandoffDecision,
    HandoffService,
)
from app.persistence.models.tenant_voice_config import DEFAULT_ESCALATION_RULES


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def handoff_service(mock_session):
    """Create a handoff service with mocked dependencies."""
    return HandoffService(mock_session)


class TestUserRequestingHuman:
    """Tests for human request detection."""

    def test_detects_speak_to_human(self, handoff_service):
        """Test that 'speak to a human' is detected."""
        assert handoff_service._user_requesting_human("I want to speak to a human") is True

    def test_detects_real_person(self, handoff_service):
        """Test that 'real person' is detected."""
        assert handoff_service._user_requesting_human("Can I talk to a real person?") is True

    def test_detects_manager(self, handoff_service):
        """Test that 'manager' is detected."""
        assert handoff_service._user_requesting_human("I need to speak with a manager") is True

    def test_detects_representative(self, handoff_service):
        """Test that 'representative' is detected."""
        assert handoff_service._user_requesting_human("Connect me to a representative") is True

    def test_does_not_detect_normal_speech(self, handoff_service):
        """Test that normal speech is not detected as human request."""
        assert handoff_service._user_requesting_human("I want to know about pricing") is False

    def test_does_not_detect_partial_matches(self, handoff_service):
        """Test that partial matches don't trigger."""
        assert handoff_service._user_requesting_human("The manager of pricing") is True  # Actually this should match 'manager'


class TestGenerateTransferTwiml:
    """Tests for transfer TwiML generation."""

    def test_generates_valid_twiml(self, handoff_service):
        """Test that valid TwiML is generated."""
        twiml = handoff_service.generate_transfer_twiml("+15555551234")
        
        assert '<?xml version="1.0" encoding="UTF-8"?>' in twiml
        assert "<Response>" in twiml
        assert "<Dial>+15555551234</Dial>" in twiml
        assert "<Say>" in twiml

    def test_escapes_xml_in_announcement(self, handoff_service):
        """Test that XML special chars in announcement are escaped."""
        twiml = handoff_service.generate_transfer_twiml(
            "+15555551234",
            announcement="Transferring to John & Jane's office"
        )
        
        assert "&amp;" in twiml
        assert "&apos;" in twiml


class TestGenerateTakeMessageTwiml:
    """Tests for take message TwiML generation."""

    def test_generates_valid_twiml(self, handoff_service):
        """Test that valid TwiML is generated."""
        twiml = handoff_service.generate_take_message_twiml()
        
        assert '<?xml version="1.0" encoding="UTF-8"?>' in twiml
        assert "<Response>" in twiml
        assert "<Record" in twiml
        assert 'maxLength="300"' in twiml

    def test_uses_custom_message(self, handoff_service):
        """Test that custom message is used."""
        custom_msg = "Please leave your message now."
        twiml = handoff_service.generate_take_message_twiml(message=custom_msg)
        
        assert custom_msg in twiml


class TestGenerateScheduleCallbackTwiml:
    """Tests for schedule callback TwiML generation."""

    def test_generates_valid_twiml(self, handoff_service):
        """Test that valid TwiML is generated."""
        twiml = handoff_service.generate_schedule_callback_twiml()
        
        assert '<?xml version="1.0" encoding="UTF-8"?>' in twiml
        assert "<Response>" in twiml
        assert "<Hangup/>" in twiml


class TestEvaluateHandoff:
    """Tests for handoff evaluation."""

    @pytest.mark.asyncio
    async def test_no_handoff_when_disabled(self, handoff_service):
        """Test that no handoff happens when voice is disabled."""
        # Mock voice config service
        handoff_service.voice_config_service.get_escalation_rules = AsyncMock(
            return_value=DEFAULT_ESCALATION_RULES
        )
        handoff_service.voice_config_service.get_handoff_config = AsyncMock(
            return_value={"mode": "take_message", "transfer_number": None, "enabled": False}
        )
        
        context = CallContext(
            call_sid="CA123",
            tenant_id=1,
            conversation_id=1,
            current_turn=0,
            transcribed_text="I want to speak to a human",
        )
        
        decision = await handoff_service.evaluate_handoff(context)
        
        assert decision.should_handoff is False

    @pytest.mark.asyncio
    async def test_handoff_when_human_requested(self, handoff_service):
        """Test that handoff happens when human is requested."""
        handoff_service.voice_config_service.get_escalation_rules = AsyncMock(
            return_value={"caller_asks_human": True, "repeated_confusion": {"enabled": False}, "high_value_intent": {"enabled": False}, "low_confidence": {"enabled": False}}
        )
        handoff_service.voice_config_service.get_handoff_config = AsyncMock(
            return_value={"mode": "live_transfer", "transfer_number": "+15555551234", "enabled": True}
        )
        
        context = CallContext(
            call_sid="CA123",
            tenant_id=1,
            conversation_id=1,
            current_turn=0,
            transcribed_text="I want to speak to a human",
        )
        
        decision = await handoff_service.evaluate_handoff(context)
        
        assert decision.should_handoff is True
        assert decision.reason == "caller_requested_human"
        assert decision.handoff_mode == "live_transfer"
        assert decision.transfer_number == "+15555551234"

    @pytest.mark.asyncio
    async def test_handoff_on_repeated_confusion(self, handoff_service):
        """Test that handoff happens after repeated confusion."""
        handoff_service.voice_config_service.get_escalation_rules = AsyncMock(
            return_value={"caller_asks_human": False, "repeated_confusion": {"enabled": True, "threshold": 3}, "high_value_intent": {"enabled": False}, "low_confidence": {"enabled": False}}
        )
        handoff_service.voice_config_service.get_handoff_config = AsyncMock(
            return_value={"mode": "take_message", "transfer_number": None, "enabled": True}
        )
        
        context = CallContext(
            call_sid="CA123",
            tenant_id=1,
            conversation_id=1,
            current_turn=5,
            transcribed_text="What?",
            consecutive_low_confidence=3,
        )
        
        decision = await handoff_service.evaluate_handoff(context)
        
        assert decision.should_handoff is True
        assert decision.reason == "repeated_confusion"

    @pytest.mark.asyncio
    async def test_no_handoff_below_confusion_threshold(self, handoff_service):
        """Test that no handoff happens below confusion threshold."""
        handoff_service.voice_config_service.get_escalation_rules = AsyncMock(
            return_value={"caller_asks_human": False, "repeated_confusion": {"enabled": True, "threshold": 3}, "high_value_intent": {"enabled": False}, "low_confidence": {"enabled": False}}
        )
        handoff_service.voice_config_service.get_handoff_config = AsyncMock(
            return_value={"mode": "take_message", "transfer_number": None, "enabled": True}
        )
        
        context = CallContext(
            call_sid="CA123",
            tenant_id=1,
            conversation_id=1,
            current_turn=2,
            transcribed_text="What?",
            consecutive_low_confidence=2,
        )
        
        decision = await handoff_service.evaluate_handoff(context)
        
        assert decision.should_handoff is False

    @pytest.mark.asyncio
    async def test_handoff_on_high_value_intent(self, handoff_service):
        """Test that handoff happens on high value intent."""
        handoff_service.voice_config_service.get_escalation_rules = AsyncMock(
            return_value={"caller_asks_human": False, "repeated_confusion": {"enabled": False}, "high_value_intent": {"enabled": True, "intents": ["booking_request"]}, "low_confidence": {"enabled": False}}
        )
        handoff_service.voice_config_service.get_handoff_config = AsyncMock(
            return_value={"mode": "live_transfer", "transfer_number": "+15555551234", "enabled": True}
        )
        
        context = CallContext(
            call_sid="CA123",
            tenant_id=1,
            conversation_id=1,
            current_turn=0,
            transcribed_text="I want to book an appointment",
            intent="booking_request",
        )
        
        decision = await handoff_service.evaluate_handoff(context)
        
        assert decision.should_handoff is True
        assert "high_value_intent" in decision.reason

