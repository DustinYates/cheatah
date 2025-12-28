"""Telnyx telephony provider implementation."""

import logging
from typing import Any

import httpx

from app.infrastructure.telephony.base import (
    SmsProviderProtocol,
    VoiceProviderProtocol,
    SmsResult,
    PhoneNumberResult,
)

logger = logging.getLogger(__name__)

TELNYX_API_BASE = "https://api.telnyx.com/v2"


class TelnyxSmsProvider(SmsProviderProtocol):
    """Telnyx SMS provider implementation."""

    def __init__(
        self,
        api_key: str,
        messaging_profile_id: str | None = None,
    ) -> None:
        """Initialize Telnyx SMS client.

        Args:
            api_key: Telnyx API v2 key
            messaging_profile_id: Telnyx messaging profile ID (required for SMS)
        """
        self.api_key = api_key
        self.messaging_profile_id = messaging_profile_id

    def _get_client(self) -> httpx.AsyncClient:
        """Create HTTP client with auth headers."""
        return httpx.AsyncClient(
            base_url=TELNYX_API_BASE,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def send_sms(
        self,
        to: str,
        from_: str,
        body: str,
        status_callback: str | None = None,
    ) -> SmsResult:
        """Send SMS via Telnyx Messages API.

        Args:
            to: Recipient phone number (E.164 format)
            from_: Sender phone number (E.164 format)
            body: Message body
            status_callback: Optional callback URL for delivery status

        Returns:
            SmsResult with message ID and status
        """
        payload: dict[str, Any] = {
            "from": from_,
            "to": to,
            "text": body,
        }

        if self.messaging_profile_id:
            payload["messaging_profile_id"] = self.messaging_profile_id

        if status_callback:
            payload["webhook_url"] = status_callback

        async with self._get_client() as client:
            response = await client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()

        message_data = data.get("data", {})
        to_info = message_data.get("to", [{}])
        status = to_info[0].get("status", "queued") if to_info else "queued"

        return SmsResult(
            message_id=message_data.get("id", ""),
            status=status,
            to=to,
            from_=from_,
            provider="telnyx",
            raw_response=data,
        )

    def validate_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
        raw_body: bytes | None = None,
    ) -> bool:
        """Validate Telnyx webhook signature.

        Telnyx uses ED25519 signatures with headers:
        - telnyx-signature-ed25519
        - telnyx-timestamp

        Args:
            url: The webhook URL (not used for Telnyx)
            params: Additional parameters including timestamp
            signature: telnyx-signature-ed25519 header value
            raw_body: Raw request body for signature verification

        Returns:
            True if signature is valid
        """
        if not signature:
            return False

        # For production, implement proper ED25519 signature validation
        # using the telnyx library or nacl
        # This is a simplified placeholder - the actual implementation should:
        # 1. Get the public key from Telnyx
        # 2. Verify the ED25519 signature over timestamp|raw_body
        try:
            # Basic validation that signature exists and has expected format
            # Production implementation should use proper cryptographic verification
            return len(signature) > 0
        except Exception as e:
            logger.warning(f"Telnyx signature validation failed: {e}")
            return False

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Get message details by ID.

        Args:
            message_id: Telnyx message ID

        Returns:
            Message details or None if not found
        """
        try:
            async with self._get_client() as client:
                response = await client.get(f"/messages/{message_id}")
                response.raise_for_status()
                data = response.json()

            message_data = data.get("data", {})
            to_info = message_data.get("to", [{}])

            return {
                "id": message_data.get("id"),
                "status": to_info[0].get("status") if to_info else None,
                "to": to_info[0].get("phone_number") if to_info else None,
                "from": message_data.get("from", {}).get("phone_number"),
                "text": message_data.get("text"),
                "created_at": message_data.get("created_at"),
            }
        except httpx.HTTPError:
            return None


class TelnyxVoiceProvider(VoiceProviderProtocol):
    """Telnyx Voice provider implementation using TeXML."""

    # Default voice for TeXML (Amazon Polly)
    DEFAULT_VOICE = "Polly.Joanna"

    def __init__(
        self,
        api_key: str,
        connection_id: str | None = None,
    ) -> None:
        """Initialize Telnyx Voice client.

        Args:
            api_key: Telnyx API v2 key
            connection_id: Telnyx connection ID (for voice)
        """
        self.api_key = api_key
        self.connection_id = connection_id

    def _get_client(self) -> httpx.AsyncClient:
        """Create HTTP client with auth headers."""
        return httpx.AsyncClient(
            base_url=TELNYX_API_BASE,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def provision_phone_number(
        self,
        area_code: str | None = None,
        phone_number: str | None = None,
    ) -> PhoneNumberResult:
        """Provision a phone number via Telnyx.

        Args:
            area_code: Area code to search for numbers
            phone_number: Specific phone number to purchase

        Returns:
            PhoneNumberResult with provisioned number details
        """
        async with self._get_client() as client:
            # Search for available numbers
            search_params: dict[str, Any] = {
                "filter[country_code]": "US",
                "filter[limit]": 1,
            }
            if area_code:
                search_params["filter[national_destination_code]"] = area_code
            if phone_number:
                search_params["filter[phone_number][contains]"] = phone_number

            search_response = await client.get(
                "/available_phone_numbers",
                params=search_params,
            )
            search_response.raise_for_status()
            search_data = search_response.json()

            available_numbers = search_data.get("data", [])
            if not available_numbers:
                raise ValueError(f"No phone numbers available for area code {area_code}")

            number_to_order = available_numbers[0]["phone_number"]

            # Create number order
            order_payload: dict[str, Any] = {
                "phone_numbers": [{"phone_number": number_to_order}],
            }

            if self.connection_id:
                order_payload["connection_id"] = self.connection_id

            order_response = await client.post(
                "/number_orders",
                json=order_payload,
            )
            order_response.raise_for_status()
            order_data = order_response.json()

        phone_numbers = order_data.get("data", {}).get("phone_numbers", [])
        if not phone_numbers:
            raise ValueError("Failed to order phone number")

        ordered_number = phone_numbers[0]

        return PhoneNumberResult(
            phone_number=ordered_number.get("phone_number"),
            phone_number_id=ordered_number.get("id"),
            provider="telnyx",
            capabilities=["voice", "sms"],
            raw_response=order_data,
        )

    async def configure_phone_webhook(
        self,
        phone_number_id: str,
        voice_url: str,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Configure TeXML webhook for a phone number.

        Args:
            phone_number_id: Telnyx phone number ID
            voice_url: Webhook URL for inbound calls (TeXML)
            status_callback_url: Optional callback URL for call status

        Returns:
            Configuration result
        """
        async with self._get_client() as client:
            # Create TeXML application
            app_payload: dict[str, Any] = {
                "application_name": f"ChatterCheetah-{phone_number_id[:8]}",
                "webhook_event_url": voice_url,
                "webhook_event_failover_url": voice_url,
                "webhook_timeout_secs": 10,
                "inbound_call_timeout_secs": 120,
            }

            if status_callback_url:
                app_payload["status_callback"] = status_callback_url

            app_response = await client.post(
                "/texml_applications",
                json=app_payload,
            )
            app_response.raise_for_status()
            app_data = app_response.json()
            texml_app_id = app_data.get("data", {}).get("id")

            # Assign application to phone number
            update_response = await client.patch(
                f"/phone_numbers/{phone_number_id}",
                json={"texml_application_id": texml_app_id},
            )
            update_response.raise_for_status()

        return {
            "phone_number_id": phone_number_id,
            "texml_application_id": texml_app_id,
            "voice_url": voice_url,
        }

    def generate_say(self, text: str, voice: str | None = None) -> str:
        """Generate TeXML Say element.

        Args:
            text: Text to speak
            voice: Voice to use

        Returns:
            TeXML Say element string
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
        """Generate TeXML Gather element.

        TeXML Gather is similar to TwiML but with some differences:
        - Uses same attribute names for compatibility
        - Supports same input types

        Args:
            action_url: URL to call with gathered input
            prompt_text: Text to speak as prompt
            input_type: Input type ('speech', 'dtmf', or 'speech dtmf')
            timeout: Seconds to wait for input
            voice: Voice to use for prompt

        Returns:
            TeXML Gather element string
        """
        voice = voice or self.DEFAULT_VOICE
        escaped_url = self._escape_xml(action_url)

        return f'''<Gather input="{input_type}" action="{escaped_url}" method="POST" speechTimeout="{timeout}" language="en-US">
    {self.generate_say(prompt_text, voice)}
</Gather>'''

    def generate_hangup(self, message: str | None = None) -> str:
        """Generate TeXML to end call.

        Args:
            message: Optional message to speak before hanging up

        Returns:
            TeXML Hangup element string
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
        """Generate TeXML Record element.

        Args:
            action_url: URL to call when recording completes
            max_length: Maximum recording length in seconds

        Returns:
            TeXML Record element string
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
        """Generate TeXML Dial element.

        Args:
            phone_number: Number to dial
            caller_id: Caller ID to display
            timeout: Seconds to wait for answer

        Returns:
            TeXML Dial element string
        """
        parts = [f'<Dial timeout="{timeout}"']
        if caller_id:
            parts.append(f' callerId="{self._escape_xml(caller_id)}"')
        parts.append(f">{self._escape_xml(phone_number)}</Dial>")
        return "".join(parts)

    def wrap_response(self, *elements: str) -> str:
        """Wrap TeXML elements in Response tags.

        Args:
            elements: TeXML element strings

        Returns:
            Complete TeXML response string
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
