"""Service for detecting AI promises to send information via SMS/email."""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DetectedPromise:
    """Represents a detected promise to send information."""

    asset_type: str  # "registration_link", "schedule", "pricing", "info"
    confidence: float  # 0.0 to 1.0
    original_text: str  # The text that triggered detection


class PromiseDetector:
    """Detects when AI promises to send information via SMS."""

    # Patterns that indicate a promise to send something
    PROMISE_PATTERNS = [
        # Direct promise patterns
        r"(?:i'll|i will|let me|i can|i'm going to)\s+(?:text|sms|send)\s+(?:you|that)",
        r"(?:i'd be happy to|happy to|glad to|i'd love to)\s+(?:text|sms|send)\s+(?:you|that)",
        r"(?:sending|send)\s+(?:you|that)\s+(?:the|a|our)",
        r"(?:i'll|i will)\s+(?:get|send)\s+(?:you|that)\s+(?:the|a|our|some)",
        # Implicit promise patterns
        r"(?:you'll receive|you will receive)\s+(?:a|the|an)",
        r"(?:expect|expecting)\s+(?:a|an|the)\s+(?:text|message|sms)",
        # Registration-specific promise patterns
        r"(?:i'll|i will|let me)\s+(?:text|sms|send|get)\s+(?:you|that|over)\s+(?:the\s+)?registration",
        r"(?:sending|send)\s+(?:you|over)\s+(?:the\s+)?registration",
        r"(?:i'll|i will)\s+(?:text|send)\s+(?:you|over)\s+(?:the\s+)?(?:registration|signup|sign\s*up)\s+(?:link|info)",
        r"(?:texting|sending)\s+(?:you|over)\s+(?:the\s+)?(?:registration|signup)\s+(?:link|info)",
        # "send that text" variations (bot says "I'll send that text to you")
        r"(?:i'll|i will)\s+send\s+(?:that|the)\s+text\s+(?:to\s+)?you",
        r"send\s+(?:that|the)\s+text\s+to\s+you\s+(?:now|right now|right away)",
        # Email promise patterns
        r"(?:i'll|i will|let me)\s+(?:email|e-mail)\s+(?:you|that)",
        r"(?:i'll|i will)\s+send\s+(?:you\s+)?(?:an\s+)?email",
        r"(?:emailing|email)\s+(?:you|that)\s+(?:the|a|our)",
        r"(?:you'll receive|you will receive)\s+(?:an\s+)?email",
        r"(?:i'll|i will)\s+(?:get|send)\s+(?:that|this)\s+(?:to\s+)?(?:your\s+)?(?:email|inbox)",
    ]

    # Keywords that identify what type of asset is being promised
    ASSET_KEYWORDS = {
        "registration_link": [
            "registration",
            "register",
            "sign up",
            "signup",
            "enroll",
            "enrollment",
            "link",
        ],
        "schedule": [
            "schedule",
            "class times",
            "hours",
            "timetable",
            "calendar",
            "availability",
        ],
        "pricing": [
            "pricing",
            "prices",
            "rates",
            "cost",
            "tuition",
            "fee",
            "fees",
            "package",
        ],
        "info": [
            "information",
            "details",
            "brochure",
            "info",
            "more about",
            "learn more",
        ],
        "email_promise": [
            "email",
            "e-mail",
            "inbox",
        ],
    }

    def detect_promise(self, ai_response: str) -> DetectedPromise | None:
        """Detect if AI response contains a promise to send information.

        Args:
            ai_response: The AI's response text

        Returns:
            DetectedPromise if a promise was found, None otherwise
        """
        if not ai_response:
            return None

        response_lower = ai_response.lower()

        # Check if response contains any promise patterns
        promise_match = None
        for pattern in self.PROMISE_PATTERNS:
            match = re.search(pattern, response_lower)
            if match:
                promise_match = match
                break

        if not promise_match:
            return None

        # Determine the asset type from surrounding context
        asset_type = self._identify_asset_type(response_lower)
        if not asset_type:
            # Default to "info" if we detected a promise but can't identify the asset
            asset_type = "info"

        # Calculate confidence based on pattern match quality
        confidence = self._calculate_confidence(response_lower, promise_match, asset_type)

        logger.info(
            f"Promise detected: asset_type={asset_type}, confidence={confidence:.2f}, "
            f"match='{promise_match.group()}'"
        )

        return DetectedPromise(
            asset_type=asset_type,
            confidence=confidence,
            original_text=ai_response,
        )

    def _identify_asset_type(self, text: str) -> str | None:
        """Identify the type of asset being promised.

        Args:
            text: Lowercase text to search

        Returns:
            Asset type string or None if not identified
        """
        # Score each asset type based on keyword matches
        scores = {}
        for asset_type, keywords in self.ASSET_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[asset_type] = score

        if not scores:
            return None

        # Return the asset type with the highest score
        return max(scores, key=scores.get)

    def _calculate_confidence(
        self,
        text: str,
        promise_match: re.Match,
        asset_type: str,
    ) -> float:
        """Calculate confidence score for the detected promise.

        Args:
            text: Full response text (lowercase)
            promise_match: The regex match for the promise pattern
            asset_type: The identified asset type

        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence for pattern match

        # Boost confidence for explicit promise patterns
        if "i'll send" in text or "i will send" in text:
            confidence += 0.2
        if "i'd be happy to" in text or "happy to text" in text or "glad to text" in text:
            confidence += 0.2

        # Boost confidence for multiple asset keywords
        keyword_count = sum(
            1
            for keyword in self.ASSET_KEYWORDS.get(asset_type, [])
            if keyword in text
        )
        confidence += min(keyword_count * 0.1, 0.2)

        # Boost confidence if "you" is mentioned (direct address)
        if "send you" in text or "text you" in text:
            confidence += 0.1

        return min(confidence, 1.0)
