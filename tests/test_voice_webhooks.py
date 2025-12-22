"""Tests for voice webhook endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_inbound_call_webhook_returns_twiml():
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


def test_inbound_call_webhook_unknown_number_graceful():
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


def test_call_status_callback_returns_200():
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


def test_call_status_callback_with_recording():
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


def test_call_status_callback_handles_missing_optional_fields():
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

