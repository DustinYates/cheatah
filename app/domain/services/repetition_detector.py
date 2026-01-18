"""Repetition detector service for identifying repeated questions and clarifications."""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class RepetitionAnalysis:
    """Analysis of repetition signals in a conversation."""

    has_repetitions: bool
    repeated_question_count: int
    clarification_count: int
    bot_clarification_count: int
    repeated_pairs: list[tuple[str, str]] = field(default_factory=list)
    clarification_messages: list[str] = field(default_factory=list)


@dataclass
class MessagePair:
    """A pair of similar messages."""

    message1: str
    message2: str
    similarity: float
    message1_index: int
    message2_index: int


class RepetitionDetector:
    """Detect repeated questions and clarification requests in conversations."""

    # Patterns indicating user confusion/clarification requests
    USER_CLARIFICATION_PATTERNS = [
        r"(?:i|you)\s+(?:don'?t|didn'?t)\s+understand",
        r"what\s+(?:do\s+you\s+mean|does\s+that\s+mean)",
        r"can\s+you\s+(?:explain|clarify|repeat)",
        r"i'?m\s+(?:not\s+sure|confused)",
        r"sorry,?\s+(?:what|i)",
        r"what\??$",
        r"huh\??",
        r"come\s+again",
        r"i\s+(?:don'?t|didn'?t)\s+(?:get|follow)",
        r"what\s+(?:are\s+you\s+)?(?:talking|asking)\s+about",
    ]

    # Patterns indicating bot clarification requests
    BOT_CLARIFICATION_PATTERNS = [
        r"could\s+you\s+(?:please\s+)?(?:clarify|explain|tell\s+me\s+more)",
        r"i'?m\s+not\s+(?:sure|certain)\s+(?:i\s+understand|what\s+you\s+mean)",
        r"(?:can|could)\s+you\s+(?:be\s+more\s+specific|provide\s+more)",
        r"what\s+(?:exactly|specifically)\s+(?:do\s+you\s+mean|are\s+you)",
        r"i\s+(?:didn'?t|don'?t)\s+(?:quite\s+)?(?:catch|understand)\s+that",
        r"(?:sorry|apologies),?\s+(?:i\s+)?(?:didn'?t|don'?t)\s+understand",
        r"could\s+you\s+(?:please\s+)?repeat",
        r"let\s+me\s+make\s+sure\s+i\s+understand",
    ]

    # Minimum similarity threshold for detecting repeated messages
    SIMILARITY_THRESHOLD = 0.7

    # Minimum message length to consider for similarity
    MIN_MESSAGE_LENGTH = 10

    def analyze_conversation(
        self,
        messages: list[dict],
    ) -> RepetitionAnalysis:
        """
        Analyze a conversation for repetition signals.

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            RepetitionAnalysis with repetition metrics
        """
        user_messages = [
            (i, m["content"])
            for i, m in enumerate(messages)
            if m.get("role") == "user" and m.get("content")
        ]
        assistant_messages = [
            (i, m["content"])
            for i, m in enumerate(messages)
            if m.get("role") == "assistant" and m.get("content")
        ]

        # Find repeated user messages
        repeated_pairs = self._find_similar_messages(user_messages)

        # Count user clarification requests
        user_clarifications = []
        for _, content in user_messages:
            if self._is_clarification_request(content, self.USER_CLARIFICATION_PATTERNS):
                user_clarifications.append(content)

        # Count bot clarification requests
        bot_clarifications = 0
        for _, content in assistant_messages:
            if self._is_clarification_request(content, self.BOT_CLARIFICATION_PATTERNS):
                bot_clarifications += 1

        return RepetitionAnalysis(
            has_repetitions=len(repeated_pairs) > 0 or len(user_clarifications) > 0,
            repeated_question_count=len(repeated_pairs),
            clarification_count=len(user_clarifications),
            bot_clarification_count=bot_clarifications,
            repeated_pairs=[(p.message1, p.message2) for p in repeated_pairs],
            clarification_messages=user_clarifications,
        )

    def _find_similar_messages(
        self,
        messages: list[tuple[int, str]],
    ) -> list[MessagePair]:
        """Find pairs of similar messages."""
        similar_pairs = []

        for i, (idx1, msg1) in enumerate(messages):
            # Skip short messages
            if len(msg1) < self.MIN_MESSAGE_LENGTH:
                continue

            for idx2, msg2 in messages[i + 1 :]:
                if len(msg2) < self.MIN_MESSAGE_LENGTH:
                    continue

                similarity = self._calculate_similarity(msg1, msg2)
                if similarity >= self.SIMILARITY_THRESHOLD:
                    similar_pairs.append(
                        MessagePair(
                            message1=msg1,
                            message2=msg2,
                            similarity=similarity,
                            message1_index=idx1,
                            message2_index=idx2,
                        )
                    )

        return similar_pairs

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using SequenceMatcher."""
        # Normalize texts
        text1_normalized = self._normalize_text(text1)
        text2_normalized = self._normalize_text(text2)

        return SequenceMatcher(None, text1_normalized, text2_normalized).ratio()

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r"[^\w\s]", "", text)
        # Normalize whitespace
        text = " ".join(text.split())
        return text

    def _is_clarification_request(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any clarification pattern."""
        text_lower = text.lower()
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def get_repetition_score(self, analysis: RepetitionAnalysis) -> float:
        """
        Calculate a repetition score for the conversation.

        Higher scores indicate more friction/confusion.

        Returns:
            Score from 0.0 (no issues) to 1.0 (significant issues)
        """
        score = 0.0

        # Weight factors
        repeated_weight = 0.3
        user_clarification_weight = 0.2
        bot_clarification_weight = 0.15

        # Add score for repeated questions (max 0.3)
        score += min(analysis.repeated_question_count * repeated_weight, 0.3)

        # Add score for user clarifications (max 0.4)
        score += min(analysis.clarification_count * user_clarification_weight, 0.4)

        # Add score for bot clarifications (max 0.3)
        score += min(analysis.bot_clarification_count * bot_clarification_weight, 0.3)

        return min(score, 1.0)
