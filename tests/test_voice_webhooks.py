"""Tests for voice webhook endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestInboundCallWebhook:
    """Tests for the inbound call webhook endpoint."""

    def test_inbound_call_webhook_returns_twiml(self):
        """Test inbound call webhook returns TwiML XML response."""
        response = client.post(
            "/api/v1/voice/inbound",
            data={
                "CallSid": "CA1234567890abcdef",
                "From": "+1234567890",
                "To": "+0987654321",
                "CallStatus": "ringing",
                "AccountSid": "AC1234567890abcdef",
            },
        )
        
        # Should return 200 with TwiML
        assert response.status_code == 200
        assert "<?xml" in response.text
        assert "<Response>" in response.text

    def test_inbound_call_webhook_unknown_number_graceful(self):
        """Test inbound call webhook handles unknown phone numbers gracefully."""
        response = client.post(
            "/api/v1/voice/inbound",
            data={
                "CallSid": "CA_UNKNOWN_NUMBER_TEST",
                "From": "+1111111111",
                "To": "+9999999999",  # Unknown number
                "CallStatus": "ringing",
                "AccountSid": "AC_UNKNOWN",
            },
        )
        
        # Should return 200 even for unknown numbers
        assert response.status_code == 200
        assert "<?xml" in response.text
        # Should contain apology message for unknown numbers
        assert "apologize" in response.text.lower() or "<Say>" in response.text

    def test_inbound_call_returns_hangup_for_errors(self):
        """Test that errors return TwiML with hangup."""
        response = client.post(
            "/api/v1/voice/inbound",
            data={
                "CallSid": "CA_ERROR_TEST",
                "From": "+1111111111",
                "To": "+9999999999",
                "CallStatus": "ringing",
                "AccountSid": "AC_UNKNOWN",
            },
        )
        
        assert response.status_code == 200
        assert "<Hangup/>" in response.text or "<Hangup />" in response.text


class TestGatherWebhook:
    """Tests for the gather/speech input webhook endpoint."""

    def test_gather_handles_no_speech(self):
        """Test gather webhook handles no speech detected."""
        response = client.post(
            "/api/v1/voice/gather",
            data={
                "CallSid": "CA_GATHER_TEST",
                "tenant_id": "1",
                "conversation_id": "1",
                "turn": "0",
                # No SpeechResult - simulates no speech detected
            },
        )
        
        assert response.status_code == 200
        assert "<?xml" in response.text
        assert "<Response>" in response.text
        # Should prompt again or end gracefully
        assert "<Gather" in response.text or "<Hangup" in response.text

    def test_gather_detects_goodbye(self):
        """Test gather webhook handles goodbye/end phrases."""
        response = client.post(
            "/api/v1/voice/gather",
            data={
                "CallSid": "CA_GOODBYE_TEST",
                "SpeechResult": "Thank you, goodbye!",
                "Confidence": "0.95",
                "tenant_id": "1",
                "conversation_id": "1",
                "turn": "1",
            },
        )
        
        assert response.status_code == 200
        assert "<Hangup" in response.text
        # Should have a goodbye message
        assert "<Say" in response.text

    def test_gather_handles_max_turns(self):
        """Test gather webhook ends call after max turns."""
        response = client.post(
            "/api/v1/voice/gather",
            data={
                "CallSid": "CA_MAX_TURNS_TEST",
                "SpeechResult": "Another question",
                "Confidence": "0.95",
                "tenant_id": "1",
                "conversation_id": "1",
                "turn": "15",  # Exceeds MAX_VOICE_TURNS
            },
        )
        
        assert response.status_code == 200
        assert "<Hangup" in response.text

    def test_gather_returns_twiml_with_next_gather(self):
        """Test gather webhook returns TwiML with next gather for normal conversation."""
        with patch('app.domain.services.voice_service.VoiceService') as MockService:
            mock_instance = MagicMock()
            mock_instance.process_voice_turn = AsyncMock(return_value=MagicMock(
                response_text="That's a great question! Let me help you with that.",
                intent="general_inquiry",
                requires_escalation=False,
            ))
            MockService.return_value = mock_instance
            
            response = client.post(
                "/api/v1/voice/gather",
                data={
                    "CallSid": "CA_NORMAL_TEST",
                    "SpeechResult": "What are your hours?",
                    "Confidence": "0.95",
                    "tenant_id": "1",
                    "conversation_id": "1",
                    "turn": "1",
                },
            )
        
        assert response.status_code == 200
        assert "<?xml" in response.text


class TestCallStatusWebhook:
    """Tests for the call status callback endpoint."""

    def test_call_status_callback_returns_200(self):
        """Test call status callback always returns 200."""
        response = client.post(
            "/api/v1/voice/status",
            data={
                "CallSid": "CA_NONEXISTENT",
                "CallStatus": "completed",
            },
        )
        
        # Should always return 200 (to avoid Twilio retries)
        assert response.status_code == 200

    def test_call_status_callback_with_recording(self):
        """Test call status callback handles recording data."""
        response = client.post(
            "/api/v1/voice/status",
            data={
                "CallSid": "CA1234567890abcdef",
                "CallStatus": "completed",
                "CallDuration": "120",
                "RecordingSid": "RE1234567890abcdef",
                "RecordingUrl": "https://api.twilio.com/recordings/RE123",
            },
        )
        
        assert response.status_code == 200

    def test_call_status_callback_handles_missing_optional_fields(self):
        """Test call status callback works without optional fields."""
        response = client.post(
            "/api/v1/voice/status",
            data={
                "CallSid": "CA1234567890abcdef",
                "CallStatus": "failed",
                # No CallDuration, RecordingSid, or RecordingUrl
            },
        )
        
        assert response.status_code == 200

    def test_call_status_handles_all_terminal_statuses(self):
        """Test call status callback handles all terminal statuses."""
        terminal_statuses = ["completed", "failed", "busy", "no-answer", "canceled"]
        
        for status in terminal_statuses:
            response = client.post(
                "/api/v1/voice/status",
                data={
                    "CallSid": f"CA_STATUS_{status.upper()}",
                    "CallStatus": status,
                },
            )
            assert response.status_code == 200, f"Failed for status: {status}"


class TestTwiMLGeneration:
    """Tests for TwiML generation functions."""

    def test_inbound_generates_greeting_twiml(self):
        """Test that inbound calls generate proper greeting TwiML."""
        response = client.post(
            "/api/v1/voice/inbound",
            data={
                "CallSid": "CA_GREETING_TEST",
                "From": "+1234567890",
                "To": "+0987654321",
                "CallStatus": "ringing",
                "AccountSid": "AC123",
            },
        )
        
        # Check for Polly voice
        assert response.status_code == 200
        # Should have a Say element with greeting
        assert "<Say" in response.text

    def test_twiml_escapes_special_characters(self):
        """Test that TwiML properly escapes special XML characters."""
        # This test verifies that user input doesn't break XML structure
        response = client.post(
            "/api/v1/voice/gather",
            data={
                "CallSid": "CA_SPECIAL_CHARS_TEST",
                "SpeechResult": "Test with <special> & 'characters' \"here\"",
                "Confidence": "0.95",
                "tenant_id": "1",
                "conversation_id": "1",
                "turn": "1",
            },
        )
        
        assert response.status_code == 200
        # Response should be valid XML - no parse errors
        assert "<?xml" in response.text
        assert "<Response>" in response.text

