"""Tests for SMS webhook endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_inbound_sms_webhook_ack():
    """Test inbound SMS webhook returns immediate ACK."""
    response = client.post(
        "/api/v1/sms/inbound",
        data={
            "From": "+1234567890",
            "To": "+0987654321",
            "Body": "Hello",
            "MessageSid": "SM123",
            "AccountSid": "AC123",
        },
    )
    
    # Should return 200 immediately (TwiML)
    assert response.status_code == 200
    assert "<?xml" in response.text


def test_sms_status_callback():
    """Test SMS status callback endpoint."""
    response = client.post(
        "/api/v1/sms/status",
        data={
            "MessageSid": "SM123",
            "MessageStatus": "delivered",
        },
    )
    
    # Should return 200
    assert response.status_code == 200

