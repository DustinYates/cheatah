"""Topic classification for conversation analytics.

Classifies conversations into topics using keyword matching across all channels.
Used by the topic worker to populate conversations.topic for the analytics histogram.
"""

from dataclasses import dataclass


@dataclass
class TopicResult:
    """Result of topic classification."""

    topic: str
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Keywords that triggered the topic


# Unified topic taxonomy with keyword groups
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "pricing": [
        "price", "cost", "fee", "charge", "pricing", "how much", "afford",
        "expensive", "cheap", "discount", "deal", "offer", "special", "rate",
        "quote", "tuition", "payment", "pay", "money", "dollar", "budget",
    ],
    "scheduling": [
        "schedule", "appointment", "book", "reserve", "available", "slot",
        "meeting", "visit", "come in", "reschedule", "cancel appointment",
        "makeup", "make up", "make-up",
    ],
    "hours_location": [
        "hours", "open", "close", "closing", "location", "address",
        "directions", "map", "parking", "where are you", "where is",
        "what time", "when do you",
    ],
    "class_info": [
        "class", "lesson", "level", "beginner", "intermediate", "advanced",
        "swim", "program", "course", "instructor", "teacher", "group size",
        "private lesson", "tadpole", "minnow", "turtle", "starfish",
        "seahorse", "shark", "barracuda", "swimboree",
    ],
    "registration": [
        "register", "enroll", "sign up", "signup", "join", "start",
        "new student", "trial", "first time", "get started", "registration",
        "enrollment", "link",
    ],
    "support_request": [
        "human", "person", "agent", "representative", "speak to", "talk to",
        "real person", "customer service", "support", "help me", "escalate",
        "manager", "supervisor", "complaint", "issue", "problem",
    ],
    "wrong_number": [
        "wrong number", "didn't call", "stop", "unsubscribe", "opt out",
        "remove me", "don't text", "don't call",
    ],
}


class TopicClassifier:
    """Classifies conversation topic from user message content."""

    def classify(self, messages: list[str]) -> TopicResult:
        """Classify a conversation's topic from its user messages.

        Args:
            messages: List of user message content strings.

        Returns:
            TopicResult with the most likely topic.
        """
        combined = " ".join(messages).strip().lower()

        if not combined:
            return TopicResult(topic="general_inquiry", confidence=0.3, keywords=[])

        scores: dict[str, float] = {}
        found_keywords: dict[str, list[str]] = {}

        for topic, keywords in TOPIC_KEYWORDS.items():
            topic_matches = []
            for keyword in keywords:
                if keyword in combined:
                    topic_matches.append(keyword)
            if topic_matches:
                scores[topic] = len(topic_matches)
                found_keywords[topic] = topic_matches

        if not scores:
            return TopicResult(topic="general_inquiry", confidence=0.4, keywords=[])

        # Pick the topic with the most keyword matches
        best_topic = max(scores, key=scores.get)  # type: ignore[arg-type]
        max_score = scores[best_topic]

        # Confidence: 0.5 base + up to 0.5 based on match count
        confidence = min(0.5 + (max_score / 8.0), 1.0)

        return TopicResult(
            topic=best_topic,
            confidence=confidence,
            keywords=found_keywords[best_topic],
        )
