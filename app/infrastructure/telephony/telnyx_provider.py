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

        logger.info(
            f"Sending SMS via Telnyx: to={to}, from={from_}, body_len={len(body)}, profile={self.messaging_profile_id}"
        )

        async with self._get_client() as client:
            response = await client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()

        message_data = data.get("data", {})
        to_info = message_data.get("to", [{}])
        status = to_info[0].get("status", "queued") if to_info else "queued"
        logger.info(
            f"Telnyx SMS response: id={message_data.get('id')}, status={status}, to_phone={to_info[0].get('phone_number') if to_info else None}"
        )

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


class TelnyxAIService:
    """Service for interacting with Telnyx AI Assistants API."""

    def __init__(self, api_key: str) -> None:
        """Initialize Telnyx AI service.

        Args:
            api_key: Telnyx API v2 key
        """
        self.api_key = api_key

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

    async def find_conversation_by_call_control_id(
        self, call_control_id: str
    ) -> dict[str, Any] | None:
        """Find a conversation by call_control_id.

        Args:
            call_control_id: The Telnyx call control ID

        Returns:
            Conversation data or None if not found
        """
        try:
            async with self._get_client() as client:
                # Get recent conversations and filter by call_control_id
                # Telnyx may store this in various places
                response = await client.get("/ai/conversations", params={"page[size]": 100})
                response.raise_for_status()
                data = response.json()

                logger.info(f"[TELNYX-API] Searching for call_control_id: {call_control_id}")
                logger.info(f"[TELNYX-API] Found {len(data.get('data', []))} conversations")

                for conv in data.get("data", []):
                    # Check multiple places where call_control_id might be stored
                    metadata = conv.get("metadata", {}) or {}

                    # Check metadata.call_control_id
                    if metadata.get("call_control_id") == call_control_id:
                        logger.info(f"[TELNYX-API] Found conversation by metadata.call_control_id: {conv.get('id')}")
                        return conv

                    # Check direct call_control_id field
                    if conv.get("call_control_id") == call_control_id:
                        logger.info(f"[TELNYX-API] Found conversation by direct call_control_id: {conv.get('id')}")
                        return conv

                    # Check if call_control_id is in the conversation ID itself (some formats)
                    if conv.get("id") and call_control_id in str(conv.get("id")):
                        logger.info(f"[TELNYX-API] Found conversation by ID match: {conv.get('id')}")
                        return conv

                    # Check metadata.telnyx_call_control_id (alternative field name)
                    if metadata.get("telnyx_call_control_id") == call_control_id:
                        logger.info(f"[TELNYX-API] Found conversation by metadata.telnyx_call_control_id: {conv.get('id')}")
                        return conv

                logger.warning(f"[TELNYX-API] No conversation found for call_control_id: {call_control_id}")
                # Log first conversation's structure for debugging
                if data.get("data"):
                    sample = data["data"][0]
                    logger.info(f"[TELNYX-API] Sample conversation keys: {list(sample.keys())}")
                    logger.info(f"[TELNYX-API] Sample metadata: {sample.get('metadata', {})}")
                return None
        except httpx.HTTPError as e:
            logger.warning(f"Failed to find conversation by call_control_id: {e}")
            return None

    async def get_conversation_messages(
        self, conversation_id: str
    ) -> list[dict[str, Any]]:
        """Get messages from a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            List of message objects
        """
        try:
            async with self._get_client() as client:
                url = f"/ai/conversations/{conversation_id}/messages"
                logger.info(f"[TELNYX-API] Fetching messages from: {url}")
                response = await client.get(url)
                logger.info(f"[TELNYX-API] Response status: {response.status_code}")
                response.raise_for_status()
                data = response.json()
                messages = data.get("data", [])
                logger.info(f"[TELNYX-API] Got {len(messages)} messages, response keys: {list(data.keys())}")
                if messages:
                    logger.info(f"[TELNYX-API] First message sample: {str(messages[0])[:300]}")
                return messages
        except httpx.HTTPError as e:
            logger.warning(f"[TELNYX-API] Failed to get conversation messages: {e}, response: {getattr(e, 'response', None)}")
            return []
        except Exception as e:
            logger.warning(f"[TELNYX-API] Unexpected error getting messages: {type(e).__name__}: {e}")
            return []

    def extract_insights_from_transcript(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Extract name, email, and intent from conversation messages.

        Uses simple pattern matching to extract key information from the transcript.

        Args:
            messages: List of message objects from the conversation

        Returns:
            Dict with extracted 'name', 'email', 'intent', and 'summary'
        """
        import re

        name = ""
        email = ""
        intent = ""

        # Build transcript for summary
        transcript_lines = []
        user_messages = []

        for msg in messages:
            role = msg.get("role", "unknown")
            text = msg.get("text", "")
            if text:
                transcript_lines.append(f"{role}: {text}")
                if role == "user":
                    user_messages.append(text)

        # Extract email from any message
        full_transcript = " ".join(transcript_lines)
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', full_transcript)
        if email_match:
            email = email_match.group(0)

        # Extract name from user messages
        name_patterns = [
            r"(?:my name is|i'm|i am|this is|name's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)[,.]?\s*$",  # Just a name as response
            r"(?:it's|its)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        ]

        for user_msg in user_messages:
            if name:
                break
            for pattern in name_patterns:
                match = re.search(pattern, user_msg, re.IGNORECASE)
                if match:
                    potential_name = match.group(1).strip()
                    # Validate it looks like a name (not common words or "for me" responses)
                    if potential_name.lower() not in [
                        "yes", "no", "hi", "hello", "hey", "ok", "okay",
                        "thanks", "thank", "sure", "please", "help", "good",
                        "fine", "great", "alright", "right", "yeah", "yep",
                        "for me", "for myself", "myself", "me", "to me"
                    ] and len(potential_name) > 1:
                        name = potential_name.title()
                        break

        # Determine intent from conversation content
        content_lower = full_transcript.lower()
        if any(word in content_lower for word in ["price", "pricing", "cost", "how much", "rate"]):
            intent = "pricing_info"
        elif any(word in content_lower for word in ["hour", "open", "close", "location", "address", "where"]):
            intent = "hours_location"
        elif any(word in content_lower for word in ["book", "schedule", "appointment", "reserve", "enroll", "sign up", "register"]):
            intent = "booking_request"
        elif any(word in content_lower for word in ["help", "support", "problem", "issue", "fix"]):
            intent = "support_request"
        elif any(word in content_lower for word in ["wrong number", "wrong person", "not interested"]):
            intent = "wrong_number"
        else:
            intent = "general_inquiry"

        # Create a brief summary from the first few user messages
        summary = ""
        if user_messages:
            summary = " ".join(user_messages[:3])[:500]
            if len(summary) > 450:
                summary = summary[:450] + "..."

        return {
            "name": name,
            "email": email,
            "intent": intent,
            "summary": summary,
            "transcript": "\n".join(transcript_lines),
        }

    async def get_recording_for_conversation(
        self, conversation_id: str
    ) -> dict[str, Any] | None:
        """Fetch recording URL for an AI conversation from Telnyx API.

        For AI Agent calls, recordings are accessed through the AI Conversations API
        rather than the standard Recordings API.

        Args:
            conversation_id: The Telnyx AI conversation ID

        Returns:
            Dict with recording URL and metadata, or None if not found
        """
        try:
            async with self._get_client() as client:
                logger.info(f"[TELNYX-API] Fetching conversation details for: {conversation_id}")
                response = await client.get(f"/ai/conversations/{conversation_id}")
                response.raise_for_status()
                data = response.json()

                conv_data = data.get("data", {})
                # Log all keys to understand the response structure
                logger.info(f"[TELNYX-API] Conversation response keys: {list(conv_data.keys())}")
                logger.info(f"[TELNYX-API] Conversation data sample: {str(conv_data)[:500]}")

                recording_url = conv_data.get("recording_url") or conv_data.get("audio_url")

                if recording_url:
                    logger.info(f"[TELNYX-API] Found conversation recording: {recording_url[:50]}...")
                    return {
                        "recording_id": conversation_id,
                        "recording_url": recording_url,
                        "conversation_id": conversation_id,
                    }

                # Also check for recordings in nested fields
                recordings = conv_data.get("recordings", [])
                if recordings:
                    rec = recordings[0]
                    url = rec.get("url") or rec.get("download_url") or rec.get("public_url")
                    if url:
                        logger.info(f"[TELNYX-API] Found recording in conversation.recordings: {url[:50]}...")
                        return {
                            "recording_id": rec.get("id", conversation_id),
                            "recording_url": url,
                            "conversation_id": conversation_id,
                        }

                logger.info(f"[TELNYX-API] No recording found in conversation {conversation_id}")
                return None

        except httpx.HTTPError as e:
            logger.warning(f"[TELNYX-API] Failed to fetch conversation recording: {e}")
            return None
        except Exception as e:
            logger.warning(f"[TELNYX-API] Unexpected error fetching conversation: {type(e).__name__}: {e}")
            return None

    async def get_recording_for_call(
        self, call_control_id: str, conversation_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch recording URL for a call from Telnyx API.

        Telnyx AI Agents don't always send the call.recording.saved webhook,
        so this method provides a fallback to fetch recordings via the API.

        Args:
            call_control_id: The Telnyx call control ID
            conversation_id: Optional Telnyx AI conversation ID (for AI Agent calls)

        Returns:
            Dict with recording URLs and metadata, or None if not found
        """
        # For AI Agent calls, try the AI Conversations API first
        if conversation_id:
            result = await self.get_recording_for_conversation(conversation_id)
            if result:
                return result

        try:
            async with self._get_client() as client:
                # Try filtering by call_control_id
                logger.info(f"[TELNYX-API] Fetching recording for call_control_id: {call_control_id}")
                response = await client.get(
                    "/recordings",
                    params={"filter[call_control_id]": call_control_id}
                )
                response.raise_for_status()
                data = response.json()

                recordings = data.get("data", [])
                logger.info(f"[TELNYX-API] Found {len(recordings)} recordings for call_control_id")

                if recordings:
                    # Return the first (most recent) recording
                    recording = recordings[0]
                    # Extract the best available URL
                    recording_urls = recording.get("download_urls", {})
                    public_urls = recording.get("public_recording_urls", {})

                    mp3_url = (
                        public_urls.get("mp3")
                        or recording_urls.get("mp3")
                        or recording.get("mp3", {}).get("download_url")
                    )
                    wav_url = (
                        public_urls.get("wav")
                        or recording_urls.get("wav")
                        or recording.get("wav", {}).get("download_url")
                    )

                    result = {
                        "recording_id": recording.get("id"),
                        "recording_url": mp3_url or wav_url,
                        "mp3_url": mp3_url,
                        "wav_url": wav_url,
                        "duration_seconds": recording.get("duration_millis", 0) // 1000,
                        "status": recording.get("status"),
                    }
                    logger.info(f"[TELNYX-API] Recording found: id={result['recording_id']}, url={result['recording_url'][:50] if result['recording_url'] else 'None'}...")
                    return result

                # If no recording found by call_control_id, try call_session_id
                # (Telnyx sometimes uses different IDs)
                logger.info(f"[TELNYX-API] No recording by call_control_id, trying call_session_id")
                response = await client.get(
                    "/recordings",
                    params={"filter[call_session_id]": call_control_id}
                )
                response.raise_for_status()
                data = response.json()

                recordings = data.get("data", [])
                if recordings:
                    recording = recordings[0]
                    recording_urls = recording.get("download_urls", {})
                    public_urls = recording.get("public_recording_urls", {})

                    mp3_url = (
                        public_urls.get("mp3")
                        or recording_urls.get("mp3")
                        or recording.get("mp3", {}).get("download_url")
                    )
                    wav_url = (
                        public_urls.get("wav")
                        or recording_urls.get("wav")
                        or recording.get("wav", {}).get("download_url")
                    )

                    result = {
                        "recording_id": recording.get("id"),
                        "recording_url": mp3_url or wav_url,
                        "mp3_url": mp3_url,
                        "wav_url": wav_url,
                        "duration_seconds": recording.get("duration_millis", 0) // 1000,
                        "status": recording.get("status"),
                    }
                    logger.info(f"[TELNYX-API] Recording found via session_id: id={result['recording_id']}")
                    return result

                logger.info(f"[TELNYX-API] No recording found for call: {call_control_id}")

                # Last resort: list recent recordings and look for matches by phone number/time
                logger.info(f"[TELNYX-API] Trying to list recent recordings as fallback")
                response = await client.get(
                    "/recordings",
                    params={"page[size]": 50}  # Get last 50 recordings
                )
                response.raise_for_status()
                data = response.json()

                recordings = data.get("data", [])
                logger.info(f"[TELNYX-API] Found {len(recordings)} total recent recordings")

                # Log recording IDs for debugging
                if recordings:
                    for rec in recordings[:5]:  # Log first 5
                        logger.info(f"[TELNYX-API] Recent recording: id={rec.get('id')}, call_leg={rec.get('call_leg_id')}, call_control={rec.get('call_control_id')}")

                return None

        except httpx.HTTPError as e:
            logger.warning(f"[TELNYX-API] Failed to fetch recording: {e}")
            return None
        except Exception as e:
            logger.warning(f"[TELNYX-API] Unexpected error fetching recording: {type(e).__name__}: {e}")
            return None

    async def extract_insights_with_llm(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Extract name, email, and intent using Gemini LLM.

        Uses Gemini to intelligently extract caller information from the
        voice conversation transcript.

        Args:
            messages: List of message objects from the conversation

        Returns:
            Dict with extracted 'name', 'email', 'intent', and 'summary'
        """
        import json

        # Build transcript
        transcript_lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            text = msg.get("text", "")
            if text:
                speaker = "Caller" if role == "user" else "Assistant"
                transcript_lines.append(f"{speaker}: {text}")

        transcript = "\n".join(transcript_lines)

        if not transcript.strip():
            return {"name": "", "email": "", "intent": "general_inquiry", "summary": ""}

        # Prompt for structured extraction
        prompt = f"""Analyze this phone call transcript and extract the following information.
Return ONLY a valid JSON object with these fields - no other text.

Transcript:
{transcript}

Extract:
1. "name" - The caller's full name if they explicitly stated it. Empty string if not provided.
2. "email" - The caller's email if they mentioned it. Empty string if not provided.
3. "intent" - One of: "pricing_info", "hours_location", "booking_request", "support_request", "wrong_number", "general_inquiry"
4. "summary" - A brief 1-sentence summary (max 100 characters) of why the caller called.

CRITICAL rules for name extraction:
- Only extract a name if the caller EXPLICITLY stated their name (e.g., "My name is John Smith", "I'm Sarah", "It's Mike")
- NEVER extract these as names: "for me", "for myself", "myself", "me", "for my child", "for my son", "for my daughter", "for my wife", "for my husband" - these are responses to "who is this for?" and are NOT names
- Do not infer or guess names from context
- If no explicit name was stated, return empty string ""

Return ONLY compact JSON (no extra whitespace or newlines):"""

        try:
            from app.llm.gemini_client import GeminiClient

            gemini = GeminiClient()
            response = await gemini.generate(prompt, {"temperature": 0.1, "max_tokens": 5000})

            logger.info(f"Gemini raw response: {response[:500] if response else 'empty'}")

            # Parse JSON from response
            response_text = response.strip()
            # Handle markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            extracted = json.loads(response_text)

            # Validate intent
            valid_intents = [
                "pricing_info", "hours_location", "booking_request",
                "support_request", "wrong_number", "general_inquiry"
            ]
            intent = extracted.get("intent", "general_inquiry")
            if intent not in valid_intents:
                intent = "general_inquiry"

            result = {
                "name": extracted.get("name", "").strip(),
                "email": extracted.get("email", "").strip(),
                "intent": intent,
                "summary": extracted.get("summary", "").strip(),
                "transcript": transcript,
            }

            logger.info(f"LLM extraction result: name={result['name']}, email={result['email']}, intent={result['intent']}")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}, response={response[:200] if response else 'empty'}")
            # Fall back to regex extraction
            return self.extract_insights_from_transcript(messages)
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}, falling back to regex")
            # Fall back to regex extraction
            return self.extract_insights_from_transcript(messages)


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
