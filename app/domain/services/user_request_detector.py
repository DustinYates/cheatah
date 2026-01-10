"""Service for detecting user requests to receive information via SMS/email."""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DetectedRequest:
    """Represents a detected user request for information."""

    asset_type: str  # "registration_link", "schedule", "pricing", "info"
    confidence: float  # 0.0 to 1.0
    original_text: str  # The text that triggered detection


class UserRequestDetector:
    """Detects when user requests information that should trigger an automated SMS."""

    # Patterns that indicate a user is requesting registration info
    REGISTRATION_REQUEST_PATTERNS = [
        # Direct requests to send registration
        r"(?:send|text|email)\s+(?:me|us)\s+(?:the\s+)?(?:registration|signup|sign\s*up|enrollment)",
        r"(?:can|could)\s+(?:i|you)\s+(?:get|send|have)\s+(?:the\s+)?(?:registration|signup|sign\s*up)",
        r"(?:can|could)\s+(?:i|you)\s+(?:get|send|have)\s+(?:a|the)\s+(?:link|info)",
        # Questions about how to register
        r"(?:how|where)\s+(?:do|can)\s+(?:i|we)\s+(?:sign\s*up|register|enroll)",
        # Expressions of intent to register
        r"(?:want|like|need|ready)\s+to\s+(?:sign\s*up|register|enroll)",
        r"(?:i'm|i\s+am|we're|we\s+are)\s+(?:interested|ready)\s+(?:in\s+)?(?:signing\s*up|registering|enrolling)",
        r"(?:interested\s+in)\s+(?:signing\s*up|registering|enrolling|classes|lessons)",
        # Registration link/info requests
        r"(?:registration|signup|sign\s*up|enrollment)\s+(?:link|info|information|details)",
        r"(?:get|have|receive)\s+(?:the\s+)?(?:registration|signup|sign\s*up)\s+(?:link|info)",
    ]

    # Patterns for schedule requests
    SCHEDULE_REQUEST_PATTERNS = [
        r"(?:send|text|email)\s+(?:me|us)\s+(?:the\s+)?(?:schedule|class\s+times|timetable)",
        r"(?:can|could)\s+(?:i|you)\s+(?:get|send|have)\s+(?:the\s+)?(?:schedule|class\s+times)",
        r"(?:what|when)\s+(?:are|is)\s+(?:the\s+)?(?:schedule|class\s+times|availability)",
    ]

    # Patterns for pricing requests
    PRICING_REQUEST_PATTERNS = [
        r"(?:send|text|email)\s+(?:me|us)\s+(?:the\s+)?(?:pricing|prices|rates|cost)",
        r"(?:can|could)\s+(?:i|you)\s+(?:get|send|have)\s+(?:the\s+)?(?:pricing|prices|rates)",
        r"(?:how\s+much)\s+(?:does|do|is|are)",
        r"(?:what|how\s+much)\s+(?:is|are)\s+(?:the\s+)?(?:price|cost|rate|fee|tuition)",
    ]

    # Patterns for general info requests
    INFO_REQUEST_PATTERNS = [
        r"(?:send|text|email)\s+(?:me|us)\s+(?:the\s+)?(?:info|information|details|brochure)",
        r"(?:can|could)\s+(?:i|you)\s+(?:get|send|have)\s+(?:more\s+)?(?:info|information|details)",
        r"(?:tell|send)\s+(?:me|us)\s+(?:more\s+)?(?:about|info|information)",
    ]

    def detect_request(self, user_message: str) -> DetectedRequest | None:
        """Detect if user message contains a request for information.

        Args:
            user_message: The user's message text

        Returns:
            DetectedRequest if a request was found, None otherwise
        """
        if not user_message:
            return None

        message_lower = user_message.lower()

        # Check registration patterns first (highest priority)
        for pattern in self.REGISTRATION_REQUEST_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                confidence = self._calculate_confidence(message_lower, match, "registration_link")
                logger.info(
                    f"Registration request detected: confidence={confidence:.2f}, "
                    f"match='{match.group()}'"
                )
                return DetectedRequest(
                    asset_type="registration_link",
                    confidence=confidence,
                    original_text=user_message,
                )

        # Check schedule patterns
        for pattern in self.SCHEDULE_REQUEST_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                confidence = self._calculate_confidence(message_lower, match, "schedule")
                logger.info(
                    f"Schedule request detected: confidence={confidence:.2f}, "
                    f"match='{match.group()}'"
                )
                return DetectedRequest(
                    asset_type="schedule",
                    confidence=confidence,
                    original_text=user_message,
                )

        # Check pricing patterns
        for pattern in self.PRICING_REQUEST_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                confidence = self._calculate_confidence(message_lower, match, "pricing")
                logger.info(
                    f"Pricing request detected: confidence={confidence:.2f}, "
                    f"match='{match.group()}'"
                )
                return DetectedRequest(
                    asset_type="pricing",
                    confidence=confidence,
                    original_text=user_message,
                )

        # Check general info patterns
        for pattern in self.INFO_REQUEST_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                confidence = self._calculate_confidence(message_lower, match, "info")
                logger.info(
                    f"Info request detected: confidence={confidence:.2f}, "
                    f"match='{match.group()}'"
                )
                return DetectedRequest(
                    asset_type="info",
                    confidence=confidence,
                    original_text=user_message,
                )

        return None

    def _calculate_confidence(
        self,
        text: str,
        match: re.Match,
        asset_type: str,
    ) -> float:
        """Calculate confidence score for the detected request.

        Args:
            text: Full message text (lowercase)
            match: The regex match for the request pattern
            asset_type: The identified asset type

        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence for pattern match

        # Boost for explicit send/text requests
        if "send me" in text or "text me" in text or "email me" in text:
            confidence += 0.25

        # Boost for registration-specific keywords
        if asset_type == "registration_link":
            registration_keywords = ["register", "sign up", "signup", "enroll", "enrollment"]
            keyword_count = sum(1 for kw in registration_keywords if kw in text)
            confidence += min(keyword_count * 0.1, 0.2)

        # Boost for explicit link/info request
        if "link" in text or "information" in text:
            confidence += 0.1

        # Boost for ready/interested expressions (stronger intent)
        if "ready to" in text or "interested in" in text or "want to" in text:
            confidence += 0.15

        return min(confidence, 1.0)
