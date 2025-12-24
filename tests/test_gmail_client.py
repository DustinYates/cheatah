"""Tests for Gmail client infrastructure."""

import pytest
from unittest.mock import MagicMock, patch

from app.infrastructure.gmail_client import GmailClient, GmailAuthError, GmailAPIError


class TestGmailClientOAuth:
    """Tests for Gmail OAuth functionality."""

    def test_get_authorization_url_requires_credentials(self):
        """Test that get_authorization_url fails without credentials."""
        with patch("app.infrastructure.gmail_client.settings") as mock_settings:
            mock_settings.gmail_client_id = None
            mock_settings.gmail_client_secret = None
            
            with pytest.raises(GmailAuthError) as exc_info:
                GmailClient.get_authorization_url(
                    redirect_uri="http://localhost/callback",
                    state="test_state",
                )
            
            assert "not configured" in str(exc_info.value)

    def test_get_authorization_url_with_credentials(self):
        """Test get_authorization_url with valid credentials."""
        with patch("app.infrastructure.gmail_client.settings") as mock_settings:
            mock_settings.gmail_client_id = "test_client_id"
            mock_settings.gmail_client_secret = "test_secret"
            
            with patch("app.infrastructure.gmail_client.Flow") as mock_flow:
                mock_flow_instance = MagicMock()
                mock_flow_instance.authorization_url.return_value = (
                    "https://accounts.google.com/o/oauth2/auth?...",
                    "returned_state",
                )
                mock_flow.from_client_config.return_value = mock_flow_instance
                
                url, state = GmailClient.get_authorization_url(
                    redirect_uri="http://localhost/callback",
                    state="test_state",
                )
                
                assert url.startswith("https://accounts.google.com")
                assert state == "returned_state"


class TestGmailClientHelpers:
    """Tests for Gmail client helper methods."""

    def test_parse_email_address_name_and_email(self):
        """Test parsing email with name and address."""
        name, email = GmailClient.parse_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_email_address_quoted_name(self):
        """Test parsing email with quoted name."""
        name, email = GmailClient.parse_email_address('"John Doe" <john@example.com>')
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_email_address_email_only(self):
        """Test parsing email address only."""
        name, email = GmailClient.parse_email_address("john@example.com")
        assert name == ""
        assert email == "john@example.com"

    def test_parse_email_address_with_whitespace(self):
        """Test parsing email with extra whitespace."""
        name, email = GmailClient.parse_email_address("  John Doe  <  john@example.com  >  ")
        assert name == "John Doe"
        assert email == "john@example.com"


class TestGmailClientBodyExtraction:
    """Tests for email body extraction."""

    def test_extract_body_simple_text(self):
        """Test extracting body from simple text payload."""
        client = GmailClient()
        
        import base64
        body_text = "Hello, this is a test email."
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
        
        payload = {
            "body": {"data": encoded},
        }
        
        result = client._extract_body(payload)
        assert result == body_text

    def test_extract_body_multipart(self):
        """Test extracting body from multipart payload."""
        client = GmailClient()
        
        import base64
        body_text = "Hello from the text part."
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
        
        payload = {
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<p>HTML</p>").decode()},
                },
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded},
                },
            ],
        }
        
        result = client._extract_body(payload)
        assert result == body_text

    def test_extract_body_empty(self):
        """Test extracting body from empty payload."""
        client = GmailClient()
        
        payload = {}
        result = client._extract_body(payload)
        assert result == ""


class TestGmailClientCredentials:
    """Tests for credential handling."""

    def test_get_credentials_no_refresh_token(self):
        """Test that credentials fail without refresh token."""
        client = GmailClient(refresh_token=None)
        
        with pytest.raises(GmailAuthError) as exc_info:
            client._get_credentials()
        
        assert "No refresh token" in str(exc_info.value)

    def test_get_token_info(self):
        """Test getting token info after refresh."""
        with patch("app.infrastructure.gmail_client.settings") as mock_settings:
            mock_settings.gmail_client_id = "test_client_id"
            mock_settings.gmail_client_secret = "test_secret"
            
            with patch("app.infrastructure.gmail_client.Credentials") as mock_creds:
                mock_cred_instance = MagicMock()
                mock_cred_instance.valid = True
                mock_cred_instance.token = "new_access_token"
                mock_cred_instance.expiry = None
                mock_creds.return_value = mock_cred_instance
                
                client = GmailClient(
                    refresh_token="test_refresh_token",
                    access_token="old_access_token",
                )
                
                token_info = client.get_token_info()
                assert token_info["access_token"] == "new_access_token"

