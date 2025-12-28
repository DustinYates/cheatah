"""Twilio telephony provider implementation."""

from typing import Any

from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioException

from app.infrastructure.telephony.base import (
    SmsProviderProtocol,
    VoiceProviderProtocol,
    SmsResult,
    PhoneNumberResult,
)
from app.settings import settings


class TwilioSmsProvider(SmsProviderProtocol):
    """Twilio SMS provider implementation."""

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
    ) -> None:
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

    async def send_sms(
        self,
        to: str,
        from_: str,
        body: str,
        status_callback: str | None = None,
    ) -> SmsResult:
        """Send an SMS message via Twilio.

        Args:
            to: Recipient phone number (E.164 format)
            from_: Sender phone number (E.164 format)
            body: Message body
            status_callback: Optional callback URL for delivery status

        Returns:
            SmsResult with message SID and status
        """
        try:
            message = self.client.messages.create(
                to=to,
                from_=from_,
                body=body,
                status_callback=status_callback,
            )

            return SmsResult(
                message_id=message.sid,
                status=message.status,
                to=message.to,
                from_=message.from_,
                provider="twilio",
                raw_response={
                    "sid": message.sid,
                    "status": message.status,
                    "date_created": message.date_created.isoformat() if message.date_created else None,
                },
            )
        except TwilioException as e:
            raise Exception(f"Twilio SMS send failed: {str(e)}") from e

    def validate_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
        raw_body: bytes | None = None,
    ) -> bool:
        """Validate Twilio webhook signature.

        Args:
            url: The webhook URL
            params: Request parameters
            signature: X-Twilio-Signature header value
            raw_body: Not used for Twilio (uses form params)

        Returns:
            True if signature is valid
        """
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(self.auth_token)
            return validator.validate(url, params, signature)
        except Exception:
            return False

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Get message details by SID.

        Args:
            message_id: Twilio message SID

        Returns:
            Message details or None if not found
        """
        try:
            message = self.client.messages(message_id).fetch()
            return {
                "id": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "body": message.body,
                "date_created": message.date_created.isoformat() if message.date_created else None,
                "date_sent": message.date_sent.isoformat() if message.date_sent else None,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioException:
            return None


class TwilioVoiceProvider(VoiceProviderProtocol):
    """Twilio Voice provider implementation using TwiML."""

    DEFAULT_VOICE = "Polly.Joanna"

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
    ) -> None:
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

    async def provision_phone_number(
        self,
        area_code: str | None = None,
        phone_number: str | None = None,
    ) -> PhoneNumberResult:
        """Provision a phone number via Twilio.

        Args:
            area_code: Area code to search for numbers
            phone_number: Specific phone number to purchase

        Returns:
            PhoneNumberResult with provisioned number details
        """
        try:
            if phone_number:
                incoming_phone_number = self.client.incoming_phone_numbers.create(
                    phone_number=phone_number
                )
            elif area_code:
                available_numbers = self.client.available_phone_numbers("US").local.list(
                    area_code=area_code, limit=1
                )
                if not available_numbers:
                    raise ValueError(f"No phone numbers available for area code {area_code}")
                incoming_phone_number = self.client.incoming_phone_numbers.create(
                    phone_number=available_numbers[0].phone_number
                )
            else:
                available_numbers = self.client.available_phone_numbers("US").local.list(limit=1)
                if not available_numbers:
                    raise ValueError("No phone numbers available")
                incoming_phone_number = self.client.incoming_phone_numbers.create(
                    phone_number=available_numbers[0].phone_number
                )

            return PhoneNumberResult(
                phone_number=incoming_phone_number.phone_number,
                phone_number_id=incoming_phone_number.sid,
                provider="twilio",
                capabilities=["voice", "sms"],
                raw_response={
                    "sid": incoming_phone_number.sid,
                    "friendly_name": incoming_phone_number.friendly_name,
                },
            )
        except TwilioException as e:
            raise Exception(f"Twilio phone number provisioning failed: {str(e)}") from e

    async def configure_phone_webhook(
        self,
        phone_number_id: str,
        voice_url: str,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Configure webhook URL for a Twilio phone number.

        Args:
            phone_number_id: Twilio phone number SID
            voice_url: Webhook URL for inbound calls
            status_callback_url: Optional callback URL for call status

        Returns:
            Configuration result
        """
        try:
            update_params: dict[str, Any] = {
                "voice_url": voice_url,
                "voice_method": "POST",
            }
            if status_callback_url:
                update_params["status_callback"] = status_callback_url
                update_params["status_callback_method"] = "POST"

            incoming_phone_number = self.client.incoming_phone_numbers(phone_number_id).update(
                **update_params
            )

            return {
                "phone_number_id": incoming_phone_number.sid,
                "phone_number": incoming_phone_number.phone_number,
                "voice_url": incoming_phone_number.voice_url,
                "status_callback": incoming_phone_number.status_callback,
            }
        except TwilioException as e:
            raise Exception(f"Twilio phone number configuration failed: {str(e)}") from e

    def generate_say(self, text: str, voice: str | None = None) -> str:
        """Generate TwiML Say element.

        Args:
            text: Text to speak
            voice: Voice to use

        Returns:
            TwiML Say element string
        """
        voice = voice or self.DEFAULT_VOICE
        escaped_text = self._escape_xml(text)
        return f'<Say voice="{voice}">{escaped_text}</Say>'

    def generate_gather(
        self,
        action_url: str,
        prompt_text: str,
        input_type: str = "speech",
        timeout: int = 3,
        voice: str | None = None,
    ) -> str:
        """Generate TwiML Gather element.

        Args:
            action_url: URL to call with gathered input
            prompt_text: Text to speak as prompt
            input_type: Input type ('speech', 'dtmf', or 'speech dtmf')
            timeout: Seconds to wait for input
            voice: Voice to use for prompt

        Returns:
            TwiML Gather element string
        """
        voice = voice or self.DEFAULT_VOICE
        escaped_url = self._escape_xml(action_url)

        return f'''<Gather input="{input_type}" action="{escaped_url}" method="POST" speechTimeout="{timeout}" language="en-US">
    {self.generate_say(prompt_text, voice)}
</Gather>'''

    def generate_hangup(self, message: str | None = None) -> str:
        """Generate TwiML to end call.

        Args:
            message: Optional message to speak before hanging up

        Returns:
            TwiML Hangup element string
        """
        if message:
            return f"""{self.generate_say(message)}
<Hangup/>"""
        return "<Hangup/>"

    def generate_record(
        self,
        action_url: str | None = None,
        max_length: int = 300,
    ) -> str:
        """Generate TwiML Record element.

        Args:
            action_url: URL to call when recording completes
            max_length: Maximum recording length in seconds

        Returns:
            TwiML Record element string
        """
        parts = [f'<Record maxLength="{max_length}" finishOnKey="#"']
        if action_url:
            parts.append(f' action="{self._escape_xml(action_url)}"')
        parts.append("/>")
        return "".join(parts)

    def generate_dial(
        self,
        phone_number: str,
        caller_id: str | None = None,
        timeout: int = 30,
    ) -> str:
        """Generate TwiML Dial element.

        Args:
            phone_number: Number to dial
            caller_id: Caller ID to display
            timeout: Seconds to wait for answer

        Returns:
            TwiML Dial element string
        """
        parts = [f'<Dial timeout="{timeout}"']
        if caller_id:
            parts.append(f' callerId="{self._escape_xml(caller_id)}"')
        parts.append(f">{self._escape_xml(phone_number)}</Dial>")
        return "".join(parts)

    def wrap_response(self, *elements: str) -> str:
        """Wrap TwiML elements in Response tags.

        Args:
            elements: TwiML element strings

        Returns:
            Complete TwiML response string
        """
        content = "\n    ".join(elements)
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {content}
</Response>'''

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    # Additional Twilio-specific methods for backwards compatibility

    def get_recording(self, recording_sid: str) -> dict[str, Any] | None:
        """Get recording details by SID.

        Args:
            recording_sid: Twilio recording SID

        Returns:
            Recording details or None if not found
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
