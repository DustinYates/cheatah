"""Intent detection for SMS messages."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class IntentResult:
    """Result of intent detection."""

    intent: Literal["info_request", "pricing", "scheduling", "human_handoff", "general", "unknown"]
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Keywords that triggered the intent


@dataclass
class EnrollmentIntentResult:
    """Result of enrollment intent detection."""

    is_high_intent: bool
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Keywords that triggered the intent
    boost_factors: list[str]  # Factors that increased confidence (e.g., "has_phone", "has_child_age")


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

    ENROLLMENT_KEYWORDS = [
        "sign up", "register", "enroll", "enrollment", "join",
        "start class", "trial class", "free trial", "book trial",
        "ready to sign", "want to register", "when can we start",
        "schedule trial", "reserve spot", "sign my kid", "sign my child",
        "start lessons", "begin classes", "how do i sign up", "registration",
        "spot available", "next session", "enroll my", "sign up my",
        "get started", "ready to start", "interested in starting",
        "looking to enroll", "want to sign up", "like to register"
    ]

    # Keywords that indicate child age (boosts enrollment confidence)
    CHILD_AGE_KEYWORDS = [
        "year old", "years old", "months old", "my son", "my daughter",
        "my child", "my kid", "my kids", "toddler", "infant", "baby"
    ]

    # Keywords indicating specific class/time interest (boosts confidence)
    CLASS_INTEREST_KEYWORDS = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "morning", "afternoon", "evening", "weekend", "weekday",
        "beginner", "intermediate", "advanced", "level 1", "level 2"
    ]

    # Default threshold for high intent
    ENROLLMENT_CONFIDENCE_THRESHOLD = 0.7

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

    def detect_enrollment_intent(
        self,
        message: str,
        conversation_history: list[str] | None = None,
        has_phone: bool = False,
        has_email: bool = False,
    ) -> EnrollmentIntentResult:
        """Detect high enrollment intent from message and conversation context.

        Args:
            message: Current user message
            conversation_history: Optional list of previous messages for context
            has_phone: Whether the lead has provided a phone number
            has_email: Whether the lead has provided an email

        Returns:
            EnrollmentIntentResult with confidence score and triggering factors
        """
        # Combine current message with recent history for analysis
        text_to_analyze = message.lower()
        if conversation_history:
            # Include last 5 messages for context
            recent_history = " ".join(conversation_history[-5:]).lower()
            text_to_analyze = f"{recent_history} {text_to_analyze}"

        found_keywords = []
        boost_factors = []
        base_score = 0.0

        # Check for enrollment keywords
        for keyword in self.ENROLLMENT_KEYWORDS:
            if keyword in text_to_analyze:
                base_score += 0.25
                found_keywords.append(keyword)

        # Cap keyword-based score at 0.6
        base_score = min(base_score, 0.6)

        # Apply confidence boosts
        if has_phone:
            base_score += 0.15
            boost_factors.append("has_phone")

        if has_email:
            base_score += 0.10
            boost_factors.append("has_email")

        # Check for child age mentions
        for keyword in self.CHILD_AGE_KEYWORDS:
            if keyword in text_to_analyze:
                base_score += 0.10
                boost_factors.append("has_child_age")
                break  # Only count once

        # Check for specific class/time interest
        for keyword in self.CLASS_INTEREST_KEYWORDS:
            if keyword in text_to_analyze:
                base_score += 0.10
                boost_factors.append("has_class_interest")
                break  # Only count once

        # Cap total confidence at 1.0
        confidence = min(base_score, 1.0)

        return EnrollmentIntentResult(
            is_high_intent=confidence >= self.ENROLLMENT_CONFIDENCE_THRESHOLD,
            confidence=confidence,
            keywords=list(set(found_keywords)),
            boost_factors=boost_factors,
        )

