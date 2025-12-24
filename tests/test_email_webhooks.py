"""Tests for email webhook endpoints."""

import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status


@pytest.mark.asyncio
async def test_gmail_pubsub_webhook_valid_notification(test_client, db_session):
    """Test Gmail Pub/Sub webhook with valid notification."""
    # Create a mock Gmail push notification
    notification_data = {
        "emailAddress": "test@example.com",
        "historyId": "12345",
    }
    encoded_data = base64.urlsafe_b64encode(
        json.dumps(notification_data).encode()
    ).decode()
    
    payload = {
        "message": {
            "data": encoded_data,
            "messageId": "msg_123456",
            "publishTime": "2024-01-01T00:00:00Z",
        },
        "subscription": "projects/test/subscriptions/gmail-push",
    }
    
    # Mock Cloud Tasks so we don't actually queue tasks
    with patch("app.api.routes.email_webhooks.settings") as mock_settings:
        mock_settings.cloud_tasks_email_worker_url = None  # Disable async processing
        mock_settings.environment = "development"
        
        with patch("app.api.routes.email_webhooks.EmailService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.process_gmail_notification = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service
            
            response = test_client.post(
                "/api/v1/email/pubsub",
                json=payload,
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_gmail_pubsub_webhook_invalid_data(test_client):
    """Test Gmail Pub/Sub webhook with invalid notification data."""
    payload = {
        "message": {
            "data": "invalid_base64!!!",
            "messageId": "msg_123456",
        },
        "subscription": "projects/test/subscriptions/gmail-push",
    }
    
    response = test_client.post(
        "/api/v1/email/pubsub",
        json=payload,
    )
    
    # Should return 200 but with ignored status
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_gmail_pubsub_webhook_queues_task(test_client, db_session):
    """Test Gmail Pub/Sub webhook queues task when Cloud Tasks URL is set."""
    notification_data = {
        "emailAddress": "test@example.com",
        "historyId": "12345",
    }
    encoded_data = base64.urlsafe_b64encode(
        json.dumps(notification_data).encode()
    ).decode()
    
    payload = {
        "message": {
            "data": encoded_data,
            "messageId": "msg_123456",
        },
        "subscription": "projects/test/subscriptions/gmail-push",
    }
    
    with patch("app.api.routes.email_webhooks.settings") as mock_settings:
        mock_settings.cloud_tasks_email_worker_url = "https://example.com/workers/email"
        
        with patch("app.api.routes.email_webhooks.CloudTasksClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_task_async = AsyncMock()
            mock_client_class.return_value = mock_client
            
            response = test_client.post(
                "/api/v1/email/pubsub",
                json=payload,
            )
            
            assert response.status_code == 200
            mock_client.create_task_async.assert_called_once()


@pytest.mark.asyncio
async def test_email_webhook_health(test_client):
    """Test email webhook health endpoint."""
    response = test_client.get("/api/v1/email/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "email-webhooks"

