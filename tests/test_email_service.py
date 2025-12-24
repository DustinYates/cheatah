"""Tests for email service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.email_service import EmailService, EmailResult


@pytest.mark.asyncio
async def test_email_service_disabled_tenant(db_session):
    """Test email service returns error when disabled for tenant."""
    email_service = EmailService(db_session)
    
    # Mock the email config repository to return None (no config)
    with patch.object(email_service.email_config_repo, 'get_by_tenant_id', return_value=None):
        result = await email_service.process_inbound_email(
            tenant_id=1,
            from_email="customer@example.com",
            to_email="support@company.com",
            subject="Test Subject",
            body="Test body content",
            thread_id="thread_123",
            message_id="msg_123",
        )
        
        assert "not enabled" in result.response_message


@pytest.mark.asyncio
async def test_email_service_automated_email_detection():
    """Test detection of automated/no-reply emails."""
    email_service = EmailService(None)  # No session needed for detection
    
    # Test various automated email patterns
    automated_emails = [
        "noreply@company.com",
        "no-reply@service.com",
        "donotreply@notifications.com",
        "mailer-daemon@gmail.com",
        "notifications@automated.com",
    ]
    
    for email in automated_emails:
        assert email_service._is_automated_email(email, "", "") is True
    
    # Test regular emails
    regular_emails = [
        "customer@example.com",
        "john.doe@company.com",
        "support@business.com",
    ]
    
    for email in regular_emails:
        assert email_service._is_automated_email(email, "", "") is False


@pytest.mark.asyncio
async def test_email_service_automated_subject_detection():
    """Test detection of automated email subjects."""
    email_service = EmailService(None)
    
    automated_subjects = [
        "Auto: Your request has been received",
        "Automatic reply: Out of office",
        "Out of Office: Back next week",
        "Delivery Status Notification (Failure)",
        "Undeliverable: Message blocked",
    ]
    
    for subject in automated_subjects:
        assert email_service._is_automated_email("user@example.com", subject, "") is True


@pytest.mark.asyncio
async def test_email_service_extract_contact_info():
    """Test extraction of contact info from email."""
    email_service = EmailService(None)
    
    # Basic extraction
    result = email_service._extract_contact_info(
        from_email="john.doe@example.com",
        sender_name="John Doe",
        body="",
    )
    
    assert result is not None
    assert result["email"] == "john.doe@example.com"
    assert result["name"] == "John Doe"
    
    # Phone extraction from body
    body_with_phone = """
    Hello,
    Please call me at (555) 123-4567.
    Thanks,
    John
    """
    result = email_service._extract_contact_info(
        from_email="john@example.com",
        sender_name="John",
        body=body_with_phone,
    )
    
    assert result is not None
    assert "phone" in result
    assert "555" in result["phone"]


@pytest.mark.asyncio
async def test_email_service_preprocess_body():
    """Test email body preprocessing."""
    email_service = EmailService(None)
    
    # Test signature removal
    body_with_signature = """
    Hello,
    
    This is my message.
    
    --
    John Doe
    Company Name
    Phone: 555-1234
    """
    
    processed = email_service._preprocess_email_body(body_with_signature)
    assert "Hello" in processed
    assert "This is my message" in processed
    assert "Company Name" not in processed
    
    # Test long body truncation
    long_body = "A" * 15000
    processed = email_service._preprocess_email_body(long_body)
    assert len(processed) <= 10100  # MAX_BODY_LENGTH + truncation note
    assert "[Email truncated" in processed


@pytest.mark.asyncio
async def test_email_service_outgoing_message_detection():
    """Test detection of outgoing messages."""
    email_service = EmailService(None)
    
    our_email = "support@company.com"
    
    # Outgoing message
    outgoing = {"from": "support@company.com"}
    assert email_service._is_outgoing_message(outgoing, our_email) is True
    
    # Incoming message
    incoming = {"from": "customer@example.com"}
    assert email_service._is_outgoing_message(incoming, our_email) is False


@pytest.mark.asyncio
async def test_email_service_build_email_context():
    """Test email context building."""
    email_service = EmailService(None)
    
    context = email_service._build_email_context(
        subject="Question about pricing",
        sender_name="Jane Smith",
        thread_context="Previous: Hello, I have a question.",
    )
    
    assert "Email Subject: Question about pricing" in context
    assert "Sender Name: Jane Smith" in context
    assert "Previous: Hello" in context


@pytest.mark.asyncio
async def test_email_service_format_response():
    """Test email response formatting."""
    email_service = EmailService(None)
    
    # Test without signature
    response = "Thank you for your email. We'll get back to you soon."
    formatted = email_service._format_email_response(response, None)
    assert formatted == response.strip()
    
    # Test with signature
    signature = "Best regards,\nSupport Team"
    formatted = email_service._format_email_response(response, signature)
    assert response.strip() in formatted
    assert signature in formatted

