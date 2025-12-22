"""Tests for Twilio voice client."""

import pytest
from unittest.mock import MagicMock, patch

from app.infrastructure.twilio_client import TwilioVoiceClient


class TestTwilioVoiceClient:
    """Test cases for TwilioVoiceClient."""

    def test_init_with_settings(self):
        """Test client initialization with default settings."""
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest123"
            mock_settings.twilio_auth_token = "test_token"
            
            client = TwilioVoiceClient()
            
            assert client.account_sid == "ACtest123"
            assert client.auth_token == "test_token"

    def test_init_with_explicit_credentials(self):
        """Test client initialization with explicit credentials."""
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = None
            mock_settings.twilio_auth_token = None
            
            client = TwilioVoiceClient(
                account_sid="ACexplicit",
                auth_token="explicit_token",
            )
            
            assert client.account_sid == "ACexplicit"
            assert client.auth_token == "explicit_token"

    def test_init_raises_without_credentials(self):
        """Test client raises ValueError without credentials."""
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = None
            mock_settings.twilio_auth_token = None
            
            with pytest.raises(ValueError, match="Twilio account SID and auth token must be provided"):
                TwilioVoiceClient()

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_provision_phone_number_with_area_code(self, mock_twilio_client):
        """Test provisioning phone number with area code."""
        # Mock Twilio client
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        # Mock available numbers
        mock_available_number = MagicMock()
        mock_available_number.phone_number = "+14155551234"
        mock_client_instance.available_phone_numbers.return_value.local.list.return_value = [mock_available_number]
        
        # Mock incoming phone number creation
        mock_incoming = MagicMock()
        mock_incoming.sid = "PN123"
        mock_incoming.phone_number = "+14155551234"
        mock_incoming.friendly_name = "Test Number"
        mock_client_instance.incoming_phone_numbers.create.return_value = mock_incoming
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.provision_phone_number(area_code="415")
            
            assert result["sid"] == "PN123"
            assert result["phone_number"] == "+14155551234"

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_provision_phone_number_with_specific_number(self, mock_twilio_client):
        """Test provisioning specific phone number."""
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        mock_incoming = MagicMock()
        mock_incoming.sid = "PN456"
        mock_incoming.phone_number = "+15551234567"
        mock_incoming.friendly_name = "Specific Number"
        mock_client_instance.incoming_phone_numbers.create.return_value = mock_incoming
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.provision_phone_number(phone_number="+15551234567")
            
            assert result["phone_number"] == "+15551234567"
            mock_client_instance.incoming_phone_numbers.create.assert_called_once_with(
                phone_number="+15551234567"
            )

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_configure_phone_webhook(self, mock_twilio_client):
        """Test configuring webhook URL for phone number."""
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        mock_updated = MagicMock()
        mock_updated.sid = "PN123"
        mock_updated.phone_number = "+15551234567"
        mock_updated.voice_url = "https://example.com/voice/inbound"
        mock_updated.status_callback = "https://example.com/voice/status"
        mock_client_instance.incoming_phone_numbers.return_value.update.return_value = mock_updated
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.configure_phone_webhook(
                phone_number_sid="PN123",
                voice_url="https://example.com/voice/inbound",
                status_callback_url="https://example.com/voice/status",
            )
            
            assert result["voice_url"] == "https://example.com/voice/inbound"
            assert result["status_callback"] == "https://example.com/voice/status"

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_get_phone_number(self, mock_twilio_client):
        """Test getting phone number details."""
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        mock_phone = MagicMock()
        mock_phone.sid = "PN123"
        mock_phone.phone_number = "+15551234567"
        mock_phone.friendly_name = "Test Number"
        mock_phone.voice_url = "https://example.com/voice"
        mock_phone.status_callback = "https://example.com/status"
        mock_client_instance.incoming_phone_numbers.return_value.fetch.return_value = mock_phone
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.get_phone_number("PN123")
            
            assert result["sid"] == "PN123"
            assert result["phone_number"] == "+15551234567"
            assert result["voice_url"] == "https://example.com/voice"

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_get_phone_number_not_found(self, mock_twilio_client):
        """Test getting non-existent phone number returns None."""
        from twilio.base.exceptions import TwilioException
        
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        mock_client_instance.incoming_phone_numbers.return_value.fetch.side_effect = TwilioException(404, "Not Found")
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.get_phone_number("PN_NONEXISTENT")
            
            assert result is None

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_get_recording(self, mock_twilio_client):
        """Test getting recording details."""
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        mock_recording = MagicMock()
        mock_recording.sid = "RE123"
        mock_recording.status = "completed"
        mock_recording.duration = "120"
        mock_recording.uri = "/2010-04-01/Accounts/AC/Recordings/RE123"
        mock_recording.date_created = None
        mock_client_instance.recordings.return_value.fetch.return_value = mock_recording
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.get_recording("RE123")
            
            assert result["sid"] == "RE123"
            assert result["status"] == "completed"
            assert result["duration"] == "120"

    @patch('app.infrastructure.twilio_client.TwilioClient')
    def test_get_call(self, mock_twilio_client):
        """Test getting call details."""
        mock_client_instance = MagicMock()
        mock_twilio_client.return_value = mock_client_instance
        
        mock_call = MagicMock()
        mock_call.sid = "CA123"
        mock_call.status = "completed"
        mock_call.from_ = "+1234567890"
        mock_call.to = "+0987654321"
        mock_call.duration = "120"
        mock_call.start_time = None
        mock_call.end_time = None
        mock_client_instance.calls.return_value.fetch.return_value = mock_call
        
        with patch('app.infrastructure.twilio_client.settings') as mock_settings:
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            
            client = TwilioVoiceClient()
            result = client.get_call("CA123")
            
            assert result["sid"] == "CA123"
            assert result["status"] == "completed"
            assert result["from"] == "+1234567890"
            assert result["to"] == "+0987654321"

