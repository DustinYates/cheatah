"""Twilio client wrapper for sending and receiving SMS and voice calls."""

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


class TwilioVoiceClient:
    """Twilio client wrapper for voice operations."""

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

    def provision_phone_number(
        self,
        area_code: str | None = None,
        phone_number: str | None = None,
    ) -> dict[str, Any]:
        """Purchase/provision a Twilio phone number.
        
        Args:
            area_code: Area code to search for numbers (e.g., "415")
            phone_number: Specific phone number to purchase (E.164 format)
            
        Returns:
            Dictionary with phone number details including SID and number
            
        Raises:
            TwilioException: If provisioning fails
        """
        try:
            if phone_number:
                # Purchase specific number
                incoming_phone_number = self.client.incoming_phone_numbers.create(phone_number=phone_number)
            elif area_code:
                # Search and purchase number with area code
                available_numbers = self.client.available_phone_numbers("US").local.list(area_code=area_code, limit=1)
                if not available_numbers:
                    raise ValueError(f"No phone numbers available for area code {area_code}")
                phone_number_to_buy = available_numbers[0].phone_number
                incoming_phone_number = self.client.incoming_phone_numbers.create(phone_number=phone_number_to_buy)
            else:
                # Search and purchase any available number
                available_numbers = self.client.available_phone_numbers("US").local.list(limit=1)
                if not available_numbers:
                    raise ValueError("No phone numbers available")
                phone_number_to_buy = available_numbers[0].phone_number
                incoming_phone_number = self.client.incoming_phone_numbers.create(phone_number=phone_number_to_buy)
            
            return {
                "sid": incoming_phone_number.sid,
                "phone_number": incoming_phone_number.phone_number,
                "friendly_name": incoming_phone_number.friendly_name,
            }
        except TwilioException as e:
            raise Exception(f"Twilio phone number provisioning failed: {str(e)}") from e

    def configure_phone_webhook(
        self,
        phone_number_sid: str,
        voice_url: str,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Configure webhook URL for a Twilio phone number.
        
        Args:
            phone_number_sid: Twilio phone number SID
            voice_url: Webhook URL for inbound calls (TwiML)
            status_callback_url: Optional callback URL for call status updates
            
        Returns:
            Dictionary with updated phone number details
            
        Raises:
            TwilioException: If configuration fails
        """
        try:
            update_params: dict[str, Any] = {
                "voice_url": voice_url,
                "voice_method": "POST",
            }
            if status_callback_url:
                update_params["status_callback"] = status_callback_url
                update_params["status_callback_method"] = "POST"
            
            incoming_phone_number = self.client.incoming_phone_numbers(phone_number_sid).update(**update_params)
            
            return {
                "sid": incoming_phone_number.sid,
                "phone_number": incoming_phone_number.phone_number,
                "voice_url": incoming_phone_number.voice_url,
                "status_callback": incoming_phone_number.status_callback,
            }
        except TwilioException as e:
            raise Exception(f"Twilio phone number configuration failed: {str(e)}") from e

    def get_phone_number(self, phone_number_sid: str) -> dict[str, Any] | None:
        """Get phone number details by SID.
        
        Args:
            phone_number_sid: Twilio phone number SID
            
        Returns:
            Phone number details or None if not found
        """
        try:
            incoming_phone_number = self.client.incoming_phone_numbers(phone_number_sid).fetch()
            return {
                "sid": incoming_phone_number.sid,
                "phone_number": incoming_phone_number.phone_number,
                "friendly_name": incoming_phone_number.friendly_name,
                "voice_url": incoming_phone_number.voice_url,
                "status_callback": incoming_phone_number.status_callback,
            }
        except TwilioException:
            return None

    def get_recording(self, recording_sid: str) -> dict[str, Any] | None:
        """Get recording details by SID.
        
        Args:
            recording_sid: Twilio recording SID
            
        Returns:
            Recording details including URL, or None if not found
        """
        try:
            recording = self.client.recordings(recording_sid).fetch()
            return {
                "sid": recording.sid,
                "status": recording.status,
                "duration": recording.duration,
                "uri": recording.uri,
                "url": f"https://api.twilio.com{recording.uri}",
                "date_created": recording.date_created.isoformat() if recording.date_created else None,
            }
        except TwilioException:
            return None

    def get_call(self, call_sid: str) -> dict[str, Any] | None:
        """Get call details by SID.
        
        Args:
            call_sid: Twilio call SID
            
        Returns:
            Call details or None if not found
        """
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                "sid": call.sid,
                "status": call.status,
                "from": call.from_,
                "to": call.to,
                "duration": call.duration,
                "start_time": call.start_time.isoformat() if call.start_time else None,
                "end_time": call.end_time.isoformat() if call.end_time else None,
            }
        except TwilioException:
            return None

