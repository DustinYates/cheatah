"""Twilio client wrapper for sending and receiving SMS."""

from typing import Any

from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioException

from app.settings import settings


class TwilioSmsClient:
    """Twilio client wrapper for SMS operations."""

    def __init__(self, account_sid: str | None = None, auth_token: str | None = None) -> None:
        """Initialize Twilio client.
        
        Args:
            account_sid: Twilio account SID (defaults to settings)
            auth_token: Twilio auth token (defaults to settings)
        """
        self.account_sid = account_sid or settings.twilio_account_sid
        self.auth_token = auth_token or settings.twilio_auth_token
        
        if not self.account_sid or not self.auth_token:
            raise ValueError("Twilio account SID and auth token must be provided")
        
        self.client = TwilioClient(self.account_sid, self.auth_token)

    def send_sms(
        self,
        to: str,
        from_: str,
        body: str,
        status_callback: str | None = None,
    ) -> dict[str, Any]:
        """Send an SMS message.
        
        Args:
            to: Recipient phone number (E.164 format)
            from_: Sender phone number (E.164 format or Twilio number)
            body: Message body
            status_callback: Optional callback URL for delivery status
            
        Returns:
            Dictionary with message SID and status
            
        Raises:
            TwilioException: If sending fails
        """
        try:
            message = self.client.messages.create(
                to=to,
                from_=from_,
                body=body,
                status_callback=status_callback,
            )
            
            return {
                "sid": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "body": message.body,
                "date_created": message.date_created.isoformat() if message.date_created else None,
            }
        except TwilioException as e:
            raise Exception(f"Twilio SMS send failed: {str(e)}") from e

    def validate_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        """Validate Twilio webhook signature.
        
        Args:
            url: The webhook URL
            params: Request parameters
            signature: X-Twilio-Signature header value
            
        Returns:
            True if signature is valid
        """
        try:
            validator = self.client.validate(
                url=url,
                params=params,
                signature=signature,
            )
            return validator
        except Exception:
            return False

    def get_message(self, message_sid: str) -> dict[str, Any] | None:
        """Get message details by SID.
        
        Args:
            message_sid: Twilio message SID
            
        Returns:
            Message details or None if not found
        """
        try:
            message = self.client.messages(message_sid).fetch()
            return {
                "sid": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "body": message.body,
                "date_created": message.date_created.isoformat() if message.date_created else None,
                "date_sent": message.date_sent.isoformat() if message.date_sent else None,
                "date_updated": message.date_updated.isoformat() if message.date_updated else None,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioException:
            return None

