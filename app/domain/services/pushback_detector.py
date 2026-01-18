"""Pushback detector service for identifying user frustration signals."""

import re
from dataclasses import dataclass


@dataclass
class PushbackSignal:
    """Result of pushback detection."""

    is_pushback: bool
    pushback_type: str  # "impatience", "frustration", "repetition_complaint", "explicit_complaint"
    confidence: float
    trigger_phrase: str
    original_message: str


class PushbackDetector:
    """Detect user pushback/frustration signals in messages."""

    # Patterns organized by pushback type
    PUSHBACK_PATTERNS: dict[str, list[tuple[str, float]]] = {
        "impatience": [
            (r"just\s+(?:send|give)\s+(?:me\s+)?the\s+link", 0.9),
            (r"can\s+you\s+just", 0.7),
            (r"stop\s+asking", 0.9),
            (r"hurry\s+up", 0.8),
            (r"get\s+to\s+the\s+point", 0.8),
            (r"i\s+(?:just\s+)?(?:want|need)\s+the\s+link", 0.8),
            (r"(?:please\s+)?just\s+(?:send|text)\s+(?:it|me)", 0.8),
            (r"skip\s+(?:the|all)\s+(?:this|that|questions)", 0.85),
            (r"i\s+don'?t\s+(?:have|want)\s+(?:time|to)", 0.7),
        ],
        "frustration": [
            (r"i\s+already\s+(?:said|told|mentioned|gave)", 0.9),
            (r"why\s+do\s+you\s+(?:need|keep\s+asking)", 0.85),
            (r"this\s+is\s+(?:frustrating|annoying|ridiculous)", 0.95),
            (r"i\s+(?:don'?t|do\s+not)\s+want\s+to\s+(?:repeat|explain)", 0.85),
            (r"you'?re\s+not\s+(?:listening|understanding|helping)", 0.9),
            (r"i\s+(?:just\s+)?told\s+you", 0.85),
            (r"how\s+many\s+times", 0.85),
            (r"are\s+you\s+(?:even\s+)?listening", 0.9),
            (r"i\s+(?:already\s+)?answered\s+that", 0.85),
        ],
        "repetition_complaint": [
            (r"you\s+(?:already\s+)?asked\s+(?:me\s+)?(?:that|this)", 0.9),
            (r"(?:same|that)\s+question\s+(?:again|twice|already)", 0.9),
            (r"stop\s+(?:asking|repeating)", 0.9),
            (r"we\s+(?:already\s+)?(?:went|talked)\s+(?:over|about)\s+(?:this|that)", 0.85),
            (r"i\s+(?:just\s+)?(?:said|answered)\s+(?:that|this)", 0.85),
        ],
        "explicit_complaint": [
            (r"this\s+(?:bot|ai|chatbot|system)\s+(?:is|isn'?t|sucks|doesn'?t)", 0.9),
            (r"not\s+(?:helpful|useful|working)", 0.8),
            (r"waste\s+of\s+(?:time|my\s+time)", 0.9),
            (r"useless", 0.85),
            (r"terrible\s+(?:service|experience|bot)", 0.9),
            (r"talk\s+to\s+(?:a\s+)?(?:real\s+)?(?:person|human|someone)", 0.7),
            (r"(?:give\s+me\s+)?(?:a\s+)?(?:real|actual)\s+(?:person|human)", 0.75),
        ],
    }

    def detect(self, message: str) -> PushbackSignal | None:
        """
        Detect pushback signals in a message.

        Args:
            message: The user message to analyze

        Returns:
            PushbackSignal if pushback detected, None otherwise
        """
        if not message:
            return None

        message_lower = message.lower().strip()

        # Check each pushback type
        for pushback_type, patterns in self.PUSHBACK_PATTERNS.items():
            for pattern, confidence in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    return PushbackSignal(
                        is_pushback=True,
                        pushback_type=pushback_type,
                        confidence=confidence,
                        trigger_phrase=match.group(0),
                        original_message=message,
                    )

        return None

    def detect_all(self, message: str) -> list[PushbackSignal]:
        """
        Detect all pushback signals in a message (may have multiple).

        Args:
            message: The user message to analyze

        Returns:
            List of all detected PushbackSignal instances
        """
        if not message:
            return []

        message_lower = message.lower().strip()
        signals = []

        for pushback_type, patterns in self.PUSHBACK_PATTERNS.items():
            for pattern, confidence in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    signals.append(
                        PushbackSignal(
                            is_pushback=True,
                            pushback_type=pushback_type,
                            confidence=confidence,
                            trigger_phrase=match.group(0),
                            original_message=message,
                        )
                    )

        return signals

    def get_pushback_type_label(self, pushback_type: str) -> str:
        """Get human-readable label for pushback type."""
        labels = {
            "impatience": "Impatience",
            "frustration": "Frustration",
            "repetition_complaint": "Repetition Complaint",
            "explicit_complaint": "Explicit Complaint",
        }
        return labels.get(pushback_type, pushback_type.replace("_", " ").title())
