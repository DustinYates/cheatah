"""Tests for voice service - intent detection, extraction, and summary generation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.domain.services.voice_service import (
    VoiceService,
    VoiceIntent,
    CallOutcome,
    VoiceResult,
    ExtractedCallData,
)


class TestIntentDetection:
    """Tests for intent detection from transcribed speech."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        return VoiceService(mock_session)

    def test_detect_pricing_intent(self, voice_service):
        """Test detecting pricing inquiry intent."""
        test_cases = [
            "How much does it cost?",
            "What are your prices?",
            "I want to know the rates",
            "What's the fee for that?",
            "Can you tell me the pricing?",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.PRICING_INFO, f"Failed for: {text}"

    def test_detect_hours_location_intent(self, voice_service):
        """Test detecting hours/location inquiry intent."""
        test_cases = [
            "What are your hours?",
            "When do you open?",
            "What time do you close?",
            "Where are you located?",
            "What's your address?",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.HOURS_LOCATION, f"Failed for: {text}"

    def test_detect_booking_intent(self, voice_service):
        """Test detecting booking request intent."""
        test_cases = [
            "I'd like to book an appointment",
            "Can I schedule a lesson?",
            "I want to reserve a spot",
            "How do I sign up?",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.BOOKING_REQUEST, f"Failed for: {text}"

    def test_detect_support_intent(self, voice_service):
        """Test detecting support request intent."""
        test_cases = [
            "I need help with something",
            "I have a problem",
            "There's an issue with my account",
            "This isn't working",
            "I have a complaint",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.SUPPORT_REQUEST, f"Failed for: {text}"

    def test_detect_wrong_number_intent(self, voice_service):
        """Test detecting wrong number intent."""
        test_cases = [
            "Sorry, wrong number",
            "I think I called the wrong person",
            "Who is this?",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.WRONG_NUMBER, f"Failed for: {text}"

    def test_detect_general_intent_fallback(self, voice_service):
        """Test general inquiry as fallback."""
        test_cases = [
            "Hello, I'm interested in your services",
            "Can you tell me more about what you offer?",
            "Just browsing",
        ]
        
        for text in test_cases:
            result = pytest.run_async(voice_service._detect_intent(text))
            assert result == VoiceIntent.GENERAL_INQUIRY, f"Failed for: {text}"


class TestEscalationDetection:
    """Tests for escalation trigger detection."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        return VoiceService(mock_session)

    def test_escalation_on_human_request(self, voice_service):
        """Test escalation when caller asks for human."""
        test_cases = [
            "I want to speak to a human",
            "Let me talk to someone",
            "Get me a real person",
            "I need to speak with the manager",
            "Can I talk to a supervisor?",
        ]
        
        for text in test_cases:
            result = voice_service._should_escalate(text, VoiceIntent.GENERAL_INQUIRY)
            assert result is True, f"Should escalate for: {text}"

    def test_no_escalation_on_normal_requests(self, voice_service):
        """Test no escalation on normal conversation."""
        test_cases = [
            "What are your hours?",
            "How much does it cost?",
            "I'd like to book an appointment",
            "Thank you for the information",
        ]
        
        for text in test_cases:
            result = voice_service._should_escalate(text, VoiceIntent.GENERAL_INQUIRY)
            assert result is False, f"Should not escalate for: {text}"


class TestResponseGuardrails:
    """Tests for response guardrail application."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        return VoiceService(mock_session)

    def test_removes_markdown(self, voice_service):
        """Test that markdown is removed from responses."""
        response = "Here's **bold** and *italic* text with `code`."
        result = voice_service._apply_response_guardrails(response)
        
        assert "**" not in result
        assert "*" not in result
        assert "`" not in result

    def test_removes_links(self, voice_service):
        """Test that markdown links are converted to text."""
        response = "Check out [our website](https://example.com) for more."
        result = voice_service._apply_response_guardrails(response)
        
        assert "our website" in result
        assert "[" not in result
        assert "(" not in result or "https" not in result

    def test_blocks_payment_content(self, voice_service):
        """Test that payment-related content is blocked."""
        response = "Please provide your credit card number to proceed."
        result = voice_service._apply_response_guardrails(response)
        
        assert "credit card" not in result.lower()
        assert "help" in result.lower() or "looking for" in result.lower()

    def test_blocks_legal_advice(self, voice_service):
        """Test that legal advice content is blocked."""
        response = "Based on my legal advice, you should sue them."
        result = voice_service._apply_response_guardrails(response)
        
        assert "sue" not in result.lower() or "legal advice" not in result.lower()

    def test_blocks_medical_advice(self, voice_service):
        """Test that medical advice content is blocked."""
        response = "Based on my diagnosis, you should take this prescription."
        result = voice_service._apply_response_guardrails(response)
        
        assert "diagnosis" not in result.lower() or "prescription" not in result.lower()

    def test_truncates_long_responses(self, voice_service):
        """Test that overly long responses are truncated."""
        long_response = "This is a sentence. " * 20  # Very long response
        result = voice_service._apply_response_guardrails(long_response)
        
        assert len(result) <= voice_service.MAX_RESPONSE_CHARS


class TestDataExtraction:
    """Tests for structured data extraction from calls."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        return VoiceService(mock_session)

    @pytest.mark.asyncio
    async def test_extracts_email_from_messages(self, voice_service):
        """Test email extraction from conversation messages."""
        from app.persistence.models.conversation import Message
        
        messages = [
            MagicMock(role="user", content="Hi, I'm interested in your services"),
            MagicMock(role="assistant", content="Great! What's your email?"),
            MagicMock(role="user", content="It's john.doe@example.com"),
        ]
        
        with patch.object(voice_service.llm_orchestrator, 'generate', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"reason": "interested in services", "urgency": "medium", "preferred_callback_time": null}'
            
            result = await voice_service._extract_call_data(messages, "+1234567890")
        
        assert result.email == "john.doe@example.com"
        assert result.phone == "+1234567890"

    @pytest.mark.asyncio
    async def test_extracts_name_from_introduction(self, voice_service):
        """Test name extraction from user introduction."""
        messages = [
            MagicMock(role="user", content="Hi, I'm John Smith and I'm calling about your services"),
        ]
        
        with patch.object(voice_service.llm_orchestrator, 'generate', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"reason": "interested in services", "urgency": "medium", "preferred_callback_time": null}'
            
            result = await voice_service._extract_call_data(messages, "+1234567890")
        
        assert result.name == "John Smith"

    @pytest.mark.asyncio
    async def test_caller_phone_always_captured(self, voice_service):
        """Test that caller's phone from caller ID is always captured."""
        messages = [
            MagicMock(role="user", content="Hello?"),
        ]
        
        with patch.object(voice_service.llm_orchestrator, 'generate', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"reason": null, "urgency": "medium", "preferred_callback_time": null}'
            
            result = await voice_service._extract_call_data(messages, "+1987654321")
        
        assert result.phone == "+1987654321"


class TestOutcomeDetermination:
    """Tests for call outcome determination."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        return VoiceService(mock_session)

    @pytest.mark.asyncio
    async def test_booking_intent_returns_booking_requested(self, voice_service):
        """Test that booking intent results in booking_requested outcome."""
        messages = []
        extracted = ExtractedCallData()
        
        result = await voice_service._determine_outcome(
            messages, VoiceIntent.BOOKING_REQUEST, extracted
        )
        
        assert result == CallOutcome.BOOKING_REQUESTED

    @pytest.mark.asyncio
    async def test_wrong_number_returns_dismissed(self, voice_service):
        """Test that wrong number intent results in dismissed outcome."""
        messages = []
        extracted = ExtractedCallData()
        
        result = await voice_service._determine_outcome(
            messages, VoiceIntent.WRONG_NUMBER, extracted
        )
        
        assert result == CallOutcome.DISMISSED

    @pytest.mark.asyncio
    async def test_extracted_name_returns_lead_created(self, voice_service):
        """Test that extracted name results in lead_created outcome."""
        messages = [MagicMock(role="user"), MagicMock(role="user")]
        extracted = ExtractedCallData(name="John Doe")
        
        result = await voice_service._determine_outcome(
            messages, VoiceIntent.GENERAL_INQUIRY, extracted
        )
        
        assert result == CallOutcome.LEAD_CREATED

    @pytest.mark.asyncio
    async def test_multiple_messages_returns_info_provided(self, voice_service):
        """Test that multiple user messages results in info_provided outcome."""
        messages = [
            MagicMock(role="user"),
            MagicMock(role="assistant"),
            MagicMock(role="user"),
        ]
        extracted = ExtractedCallData()
        
        result = await voice_service._determine_outcome(
            messages, VoiceIntent.GENERAL_INQUIRY, extracted
        )
        
        assert result == CallOutcome.INFO_PROVIDED


class TestVoiceResultCreation:
    """Tests for voice turn processing results."""

    @pytest.fixture
    def voice_service(self):
        """Create a VoiceService instance with mocked session."""
        mock_session = MagicMock()
        service = VoiceService(mock_session)
        return service

    @pytest.mark.asyncio
    async def test_returns_error_on_missing_tenant(self, voice_service):
        """Test that missing tenant ID returns error result."""
        result = await voice_service.process_voice_turn(
            tenant_id=None,
            call_sid="CA123",
            conversation_id=1,
            transcribed_text="Hello",
        )
        
        assert "sorry" in result.response_text.lower() or "trouble" in result.response_text.lower()
        assert result.intent == VoiceIntent.UNKNOWN

    @pytest.mark.asyncio
    async def test_returns_error_on_missing_conversation(self, voice_service):
        """Test that missing conversation ID returns error result."""
        result = await voice_service.process_voice_turn(
            tenant_id=1,
            call_sid="CA123",
            conversation_id=None,
            transcribed_text="Hello",
        )
        
        assert "sorry" in result.response_text.lower() or "trouble" in result.response_text.lower()


# Helper function for running async tests with sync fixtures
class PytestHelper:
    @staticmethod
    def run_async(coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

# Monkey-patch pytest
pytest.run_async = PytestHelper.run_async

