"""Intent detection for SMS messages."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class IntentResult:
    """Result of intent detection."""
    
    intent: Literal["info_request", "pricing", "scheduling", "human_handoff", "general", "unknown"]
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Keywords that triggered the intent


class IntentDetector:
    """Intent detector for classifying SMS messages."""

    # Intent keywords (case-insensitive)
    PRICING_KEYWORDS = [
        "price", "cost", "fee", "charge", "pricing", "how much", "afford", "expensive", "cheap",
        "discount", "deal", "offer", "special", "rate", "quote"
    ]
    
    SCHEDULING_KEYWORDS = [
        "schedule", "appointment", "book", "reserve", "available", "when", "time", "date",
        "calendar", "slot", "meeting", "visit", "come in", "open", "hours"
    ]
    
    HUMAN_HANDOFF_KEYWORDS = [
        "human", "person", "agent", "representative", "speak to", "talk to", "real person",
        "customer service", "support", "help me", "escalate", "manager", "supervisor"
    ]
    
    INFO_REQUEST_KEYWORDS = [
        "what", "where", "how", "why", "when", "who", "tell me", "explain", "information",
        "details", "about", "describe", "know", "learn"
    ]

    def detect_intent(self, message: str) -> IntentResult:
        """Detect intent from message text.
        
        Args:
            message: User message text
            
        Returns:
            IntentResult with detected intent and confidence
        """
        message_lower = message.strip().lower()
        found_keywords = []
        intent_scores: dict[str, float] = {
            "pricing": 0.0,
            "scheduling": 0.0,
            "human_handoff": 0.0,
            "info_request": 0.0,
        }
        
        # Check for pricing keywords
        for keyword in self.PRICING_KEYWORDS:
            if keyword in message_lower:
                intent_scores["pricing"] += 1.0
                found_keywords.append(keyword)
        
        # Check for scheduling keywords
        for keyword in self.SCHEDULING_KEYWORDS:
            if keyword in message_lower:
                intent_scores["scheduling"] += 1.0
                found_keywords.append(keyword)
        
        # Check for human handoff keywords
        for keyword in self.HUMAN_HANDOFF_KEYWORDS:
            if keyword in message_lower:
                intent_scores["human_handoff"] += 1.0
                found_keywords.append(keyword)
        
        # Check for info request keywords
        for keyword in self.INFO_REQUEST_KEYWORDS:
            if keyword in message_lower:
                intent_scores["info_request"] += 1.0
                found_keywords.append(keyword)
        
        # Normalize scores (simple approach: divide by max possible matches)
        max_score = max(intent_scores.values()) if intent_scores.values() else 0.0
        
        if max_score == 0.0:
            return IntentResult(
                intent="general",
                confidence=0.5,
                keywords=[],
            )
        
        # Calculate confidence (0.5 to 1.0 based on keyword matches)
        confidence = min(0.5 + (max_score / 5.0), 1.0)
        
        # Determine primary intent
        primary_intent = max(intent_scores.items(), key=lambda x: x[1])[0]
        
        # If human handoff has any matches, prioritize it
        if intent_scores["human_handoff"] > 0:
            primary_intent = "human_handoff"
            confidence = min(0.7 + (intent_scores["human_handoff"] / 3.0), 1.0)
        
        return IntentResult(
            intent=primary_intent,  # type: ignore
            confidence=confidence,
            keywords=list(set(found_keywords)),
        )

    def requires_escalation(self, intent_result: IntentResult) -> bool:
        """Check if intent requires escalation to human.
        
        Args:
            intent_result: Intent detection result
            
        Returns:
            True if escalation is needed
        """
        return intent_result.intent == "human_handoff" and intent_result.confidence >= 0.6

