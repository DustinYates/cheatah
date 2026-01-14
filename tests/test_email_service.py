"""Tests for email service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.email_service import EmailService, EmailResult


@pytest.fixture
def email_service():
    """Create EmailService with mocked LLM dependencies."""
    mock_session = MagicMock()
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        service = EmailService(mock_session)
        service.chat_service.llm_orchestrator = MagicMock()
        service.chat_service.llm_orchestrator.generate = AsyncMock(return_value="Mock response")
        return service


@pytest.mark.asyncio
async def test_email_service_disabled_tenant(email_service):
    """Test email service returns error when disabled for tenant."""
    # Mock the email config repository to return None (no config)
    email_service.email_config_repo.get_by_tenant_id = AsyncMock(return_value=None)

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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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
async def test_email_service_extract_contact_info_form_submission():
    """Test that form submission emails use form data, not sender headers.

    When a form submission email arrives (e.g., from a registration form),
    the contact info should come from the form fields in the body, not from
    the email sender headers. This is critical because form submissions often
    come from automated systems with different sender info than the actual
    form submitter.
    """
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        email_service = EmailService(None)

        # Simulate a form submission email where:
        # - Sender is the location/system email: "goswimcypressspring@britishswimschool.com"
        # - Sender name is the location contact: "Dustin Yates"
        # - But the actual form data has different info:
        #   - Student Name: "Olawunmi Ayodele"
        #   - Email: "wunta23@yahoo.com"
        #   - Phone: "(972) 464-6277"
        form_submission_body = """
        Location Email: goswimcypressspring@britishswimschool.com
        HubSpot Cookie: 51576c37b8f4ee3899fcbf08c807ef5f
        UTM Source: google
        UTM Medium: performancemax
        UTM Campaign: campaignname
        Class ID: 20845810
        Student Name: Olawunmi Ayodele
        Email: wunta23@yahoo.com
        Phone: (972) 464-6277
        How did you hear about us?: Rackcard / Flyer
        """

        result = email_service._extract_contact_info(
            from_email="goswimcypressspring@britishswimschool.com",
            sender_name="Dustin Yates",
            body=form_submission_body,
        )

        assert result is not None
        # Should use form data, NOT sender info
        assert result["name"] == "Olawunmi Ayodele"  # From form, not "Dustin Yates"
        assert result["email"] == "wunta23@yahoo.com"  # From form, not location email
        assert result["phone"] == "+19724646277"  # From form
        # Should have additional fields from the form
        assert "additional_fields" in result
        assert result["additional_fields"]["location email"] == "goswimcypressspring@britishswimschool.com"
        assert result["additional_fields"]["class id"] == "20845810"


@pytest.mark.asyncio
async def test_email_service_extract_contact_info_table_format():
    """Test extraction from table format (HTML table converted to plain text).

    Some form submissions arrive as HTML tables that get converted to plain text
    where labels and values are on separate lines.
    """
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        email_service = EmailService(None)

        # Table format where labels and values are on separate lines
        table_format_body = """
Student Name
Olawunmi Ayodele
Email
wunta23@yahoo.com
Phone
(972) 464-6277
Location Email
goswimcypressspring@britishswimschool.com
Franchise Code
545911
        """

        result = email_service._extract_contact_info(
            from_email="goswimcypressspring@britishswimschool.com",
            sender_name="Dustin Yates",
            body=table_format_body,
        )

        assert result is not None
        # Should use form data from table format, NOT sender info
        assert result["name"] == "Olawunmi Ayodele"  # From form
        assert result["email"] == "wunta23@yahoo.com"  # From form
        assert result["phone"] == "+19724646277"  # From form
        # Should have additional fields
        assert "additional_fields" in result
        assert result["additional_fields"]["franchise code"] == "545911"


@pytest.mark.asyncio
async def test_email_service_preprocess_body():
    """Test email body preprocessing."""
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        email_service = EmailService(None)

        # Test signature removal (-- must be at start of line for pattern to match)
        body_with_signature = """Hello,

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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
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

