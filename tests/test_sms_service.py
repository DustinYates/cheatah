"""Tests for SMS service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.sms_service import SmsService


@pytest.fixture
def sms_service():
    """Create SmsService with mocked LLM dependencies."""
    mock_session = AsyncMock()
    # Mock execute to return an enabled SMS config
    mock_sms_config = MagicMock()
    mock_sms_config.is_enabled = True
    mock_sms_config.stop_response = "You have been unsubscribed."
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sms_config
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        service = SmsService(mock_session)
        service.chat_service.llm_orchestrator = MagicMock()
        service.chat_service.llm_orchestrator.generate = AsyncMock(return_value="Mock response")
        return service


@pytest.mark.asyncio
async def test_sms_service_opt_out_handling(sms_service):
    """Test SMS service handles STOP keyword."""
    # Mock DNC service to not block
    with patch('app.domain.services.sms_service.DncService') as MockDnc:
        MockDnc.return_value.is_blocked = AsyncMock(return_value=False)

        # Mock opt-in service - OptInService is created locally in process_inbound_sms
        with patch('app.domain.services.sms_service.OptInService') as MockOptInService:
            mock_instance = MockOptInService.return_value
            mock_instance.opt_out = AsyncMock()
            mock_instance.is_opted_in = AsyncMock(return_value=True)
            mock_instance.opt_in = AsyncMock()  # For auto opt-in

            result = await sms_service.process_inbound_sms(
                tenant_id=1,
                phone_number="+1234567890",
                message_body="STOP",
            )

            # Should call opt_out
            mock_instance.opt_out.assert_called_once()
            assert result.opt_in_status_changed


@pytest.mark.asyncio
async def test_sms_service_format_response():
    """Test SMS response formatting."""
    with patch('app.domain.services.chat_service.LLMOrchestrator'):
        sms_service = SmsService(None)  # No session needed for formatting

        # Test markdown removal
        response = "This is **bold** and *italic* text"
        formatted = sms_service._format_sms_response(response)
        assert "**" not in formatted
        assert "*" not in formatted

        # Test long message truncation
        long_response = "A" * 200
        formatted = sms_service._format_sms_response(long_response)
        assert len(formatted) <= 160 or formatted.endswith("...")

