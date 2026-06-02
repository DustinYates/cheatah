"""Base telephony provider interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Telnyx error code for "Destination banned" — returned when the recipient has
# opted out / been suppressed at the carrier level. Carriers/Telnyx handle STOP
# at the messaging-profile level and reject (or accept-then-fail) every further
# send to that number with this code.
TELNYX_OPT_OUT_ERROR_CODE = "40300"

# Defensive free-text markers for the error `detail` string, since the exact
# wording varies by carrier. Kept narrow to avoid mistaking unrelated failures
# for opt-outs.
_OPT_OUT_ERROR_MARKERS = (
    "opted out",
    "opt-out",
    "opt out",
    "unsubscrib",
    "destination banned",
)


def is_opt_out_send_error(code: str | None, detail: str | None) -> bool:
    """True if a Telnyx send error means the recipient opted out / is suppressed.

    Used by send paths and the delivery-status webhook to decide when a failed
    outbound SMS should sync our opt-out state rather than be retried.
    """
    if code and str(code).strip() == TELNYX_OPT_OUT_ERROR_CODE:
        return True
    if detail:
        d = detail.lower()
        return any(m in d for m in _OPT_OUT_ERROR_MARKERS)
    return False


class RecipientOptedOutError(Exception):
    """Raised by an SMS provider when the recipient has opted out / been
    suppressed at the carrier level (e.g. Telnyx error 40300 "Destination
    banned"). Callers should sync our opt-out state instead of retrying."""

    def __init__(
        self, phone: str, detail: str | None = None, code: str | None = None
    ) -> None:
        self.phone = phone
        self.detail = detail
        self.code = code
        super().__init__(detail or f"Recipient {phone} has opted out")


@dataclass
class SmsResult:
    """Result of SMS send operation."""

    message_id: str
    status: str
    to: str
    from_: str
    provider: str
    raw_response: dict | None = None


@dataclass
class PhoneNumberResult:
    """Result of phone number provisioning."""

    phone_number: str
    phone_number_id: str
    provider: str
    capabilities: list[str]  # ['sms', 'voice', 'mms']
    raw_response: dict | None = None


class SmsProviderProtocol(ABC):
    """Protocol for SMS provider implementations."""

    @abstractmethod
    async def send_sms(
        self,
        to: str,
        from_: str,
        body: str,
        status_callback: str | None = None,
    ) -> SmsResult:
        """Send an SMS message.

        Args:
            to: Recipient phone number (E.164 format)
            from_: Sender phone number (E.164 format)
            body: Message body
            status_callback: Optional callback URL for delivery status

        Returns:
            SmsResult with message ID and status
        """
        pass

    @abstractmethod
    def validate_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
        raw_body: bytes | None = None,
    ) -> bool:
        """Validate incoming webhook signature.

        Args:
            url: The webhook URL
            params: Request parameters
            signature: Signature header value
            raw_body: Raw request body (needed for some providers)

        Returns:
            True if signature is valid
        """
        pass

    @abstractmethod
    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Get message details by ID.

        Args:
            message_id: Provider-specific message ID

        Returns:
            Message details or None if not found
        """
        pass


class VoiceProviderProtocol(ABC):
    """Protocol for Voice provider implementations."""

    @abstractmethod
    async def provision_phone_number(
        self,
        area_code: str | None = None,
        phone_number: str | None = None,
    ) -> PhoneNumberResult:
        """Provision a phone number for voice.

        Args:
            area_code: Area code to search for numbers
            phone_number: Specific phone number to purchase

        Returns:
            PhoneNumberResult with provisioned number details
        """
        pass

    @abstractmethod
    async def configure_phone_webhook(
        self,
        phone_number_id: str,
        voice_url: str,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Configure webhooks for a phone number.

        Args:
            phone_number_id: Provider-specific phone number ID
            voice_url: Webhook URL for inbound calls
            status_callback_url: Optional callback URL for call status

        Returns:
            Configuration result
        """
        pass

    @abstractmethod
    def generate_say(self, text: str, voice: str | None = None) -> str:
        """Generate TwiML/TeXML Say element.

        Args:
            text: Text to speak
            voice: Voice to use (provider-specific)

        Returns:
            XML string for say element
        """
        pass

    @abstractmethod
    def generate_gather(
        self,
        action_url: str,
        prompt_text: str,
        input_type: str = "speech",
        timeout: int = 3,
        voice: str | None = None,
    ) -> str:
        """Generate TwiML/TeXML Gather element.

        Args:
            action_url: URL to call with gathered input
            prompt_text: Text to speak as prompt
            input_type: Input type ('speech', 'dtmf', or 'speech dtmf')
            timeout: Seconds to wait for input
            voice: Voice to use for prompt

        Returns:
            XML string for gather element
        """
        pass

    @abstractmethod
    def generate_hangup(self, message: str | None = None) -> str:
        """Generate TwiML/TeXML to end call.

        Args:
            message: Optional message to speak before hanging up

        Returns:
            XML string for hangup
        """
        pass

    @abstractmethod
    def generate_record(
        self,
        action_url: str | None = None,
        max_length: int = 300,
    ) -> str:
        """Generate TwiML/TeXML Record element for voicemail.

        Args:
            action_url: URL to call when recording completes
            max_length: Maximum recording length in seconds

        Returns:
            XML string for record element
        """
        pass

    @abstractmethod
    def generate_dial(
        self,
        phone_number: str,
        caller_id: str | None = None,
        timeout: int = 30,
    ) -> str:
        """Generate TwiML/TeXML Dial element for call transfer.

        Args:
            phone_number: Number to dial
            caller_id: Caller ID to display
            timeout: Seconds to wait for answer

        Returns:
            XML string for dial element
        """
        pass

    @abstractmethod
    def wrap_response(self, *elements: str) -> str:
        """Wrap XML elements in Response tags.

        Args:
            elements: XML element strings to include

        Returns:
            Complete XML response string
        """
        pass
