"""Tests for SMS service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.sms_service import SmsService


@pytest.mark.asyncio
async def test_sms_service_opt_out_handling(db_session):
    """Test SMS service handles STOP keyword."""
    sms_service = SmsService(db_session)
    
    # Mock opt-in service
    with patch.object(sms_service.opt_in_service, 'opt_out') as mock_opt_out:
        result = await sms_service.process_inbound_sms(
            tenant_id=1,
            phone_number="+1234567890",
            message_body="STOP",
        )
        
        # Should call opt_out
        mock_opt_out.assert_called_once()
        assert result.opt_in_status_changed


@pytest.mark.asyncio
async def test_sms_service_format_response():
    """Test SMS response formatting."""
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

