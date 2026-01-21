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

    # Patterns that indicate a promise to send something (English)
    PROMISE_PATTERNS_EN = [
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
        # Passive "get...sent" constructions (bot says "I'll get that link sent over to you")
        r"(?:i'll|i will)\s+get\s+(?:that|the|this)\s+(?:link|info|information|text)\s+sent",
        r"(?:link|info|text)\s+sent\s+(?:over\s+)?to\s+you",
        r"sent\s+(?:over\s+)?to\s+you\s+(?:at|right\s+away|now)",
        r"get\s+(?:that|this|the)\s+(?:sent|over)\s+to\s+you",
        # Email promise patterns
        r"(?:i'll|i will|let me)\s+(?:email|e-mail)\s+(?:you|that)",
        r"(?:i'll|i will)\s+send\s+(?:you\s+)?(?:an\s+)?email",
        r"(?:emailing|email)\s+(?:you|that)\s+(?:the|a|our)",
        r"(?:you'll receive|you will receive)\s+(?:an\s+)?email",
        r"(?:i'll|i will)\s+(?:get|send)\s+(?:that|this)\s+(?:to\s+)?(?:your\s+)?(?:email|inbox)",
    ]

    # Spanish patterns for promise detection
    PROMISE_PATTERNS_ES = [
        # Direct promise patterns - "I can/will send you"
        r"(?:puedo|voy a|te voy a|le voy a)\s+(?:enviar|mandar|textear)",
        r"(?:te|le)\s+(?:envío|envio|mando)\s+(?:el|la|un|una|ese|esa|esto|eso)",
        r"(?:te|le)\s+(?:envío|envio|mando)\s+(?:ahora|ya|enseguida)",
        # "enviándote" / "mandándote" patterns
        r"(?:enviándote|enviandote|mandándote|mandandote)\s+(?:el|la|un|una)",
        # "I just sent it" patterns
        r"(?:te|le)\s+(?:lo|la)\s+(?:acabo de|acabe de)\s+(?:enviar|mandar)",
        r"(?:ya|acabo de)\s+(?:enviarte|enviarlo|enviarle|mandarte|mandarlo|mandarle)",
        # "let me send you" patterns
        r"(?:déjame|dejame|permíteme|permiteme)\s+(?:enviarte|mandarte)",
        # Registration-specific Spanish patterns
        r"(?:te|le)\s+(?:envío|envio|mando)\s+(?:el\s+)?(?:enlace|link)\s+(?:de\s+)?(?:registro|inscripción|inscripcion)",
        r"(?:puedo|voy a)\s+(?:enviarte|mandarte)\s+(?:el\s+)?(?:enlace|link)",
        # "I'll text you" variations
        r"(?:te|le)\s+(?:envío|envio|mando)\s+(?:un\s+)?(?:mensaje|texto|sms)",
        # Implicit promise patterns - "you will receive"
        r"(?:vas a|va a)\s+(?:recibir)\s+(?:un|una|el|la)",
        r"(?:recibirás|recibiras|recibirá|recibira)\s+(?:un|una|el|la)",
        # "I'm sending" patterns
        r"(?:estoy|le estoy|te estoy)\s+(?:enviando|mandando)",
    ]

    # Combined patterns (checked in order)
    PROMISE_PATTERNS = PROMISE_PATTERNS_EN + PROMISE_PATTERNS_ES

    # Keywords that identify what type of asset is being promised (English + Spanish)
    ASSET_KEYWORDS = {
        "registration_link": [
            # English
            "registration",
            "register",
            "sign up",
            "signup",
            "enroll",
            "enrollment",
            "link",
            # Spanish
            "registro",
            "registrar",
            "inscripción",
            "inscripcion",
            "inscribir",
            "enlace",
        ],
        "schedule": [
            # English
            "schedule",
            "class times",
            "hours",
            "timetable",
            "calendar",
            "availability",
            # Spanish
            "horario",
            "horarios",
            "disponibilidad",
            "calendario",
            "clases",
        ],
        "pricing": [
            # English
            "pricing",
            "prices",
            "rates",
            "cost",
            "tuition",
            "fee",
            "fees",
            "package",
            # Spanish
            "precios",
            "precio",
            "costo",
            "costos",
            "tarifa",
            "tarifas",
            "paquete",
            "paquetes",
        ],
        "info": [
            # English
            "information",
            "details",
            "brochure",
            "info",
            "more about",
            "learn more",
            # Spanish
            "información",
            "informacion",
            "detalles",
            "folleto",
            "más sobre",
            "mas sobre",
        ],
        "email_promise": [
            "email",
            "e-mail",
            "inbox",
            # Spanish
            "correo",
            "correo electrónico",
            "correo electronico",
        ],
    }

    def detect_promise(
        self, ai_response: str, conversation_context: str | None = None
    ) -> DetectedPromise | None:
        """Detect if AI response contains a promise to send information.

        Args:
            ai_response: The AI's response text
            conversation_context: Optional full conversation text to help classify asset type

        Returns:
            DetectedPromise if a promise was found, None otherwise
        """
        if not ai_response:
            return None

        response_lower = ai_response.lower()
        # Include conversation context for asset type classification
        context_for_classification = response_lower
        if conversation_context:
            context_for_classification = conversation_context.lower() + " " + response_lower

        # Check if response contains any promise patterns
        promise_match = None
        for pattern in self.PROMISE_PATTERNS:
            match = re.search(pattern, response_lower)
            if match:
                promise_match = match
                break

        if not promise_match:
            return None

        # Determine the asset type from surrounding context (including conversation history)
        asset_type = self._identify_asset_type(context_for_classification)
        if not asset_type:
            # Default to "info" if we detected a promise but can't identify the asset
            asset_type = "info"

        # Calculate confidence based on pattern match quality
        # Use full context for confidence calculation if available
        confidence = self._calculate_confidence(context_for_classification, promise_match, asset_type)

        # Boost confidence if we're using conversation context and found a registration URL
        if conversation_context and asset_type == "registration_link":
            if "britishswimschool.com" in conversation_context.lower():
                confidence = max(confidence, 0.75)  # Ensure high confidence when URL is in context

        # Boost confidence significantly if a phone number is in the conversation
        # If someone provides a phone number, they definitely want to receive a text
        phone_pattern = r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
        if conversation_context and re.search(phone_pattern, conversation_context):
            confidence = max(confidence, 0.85)  # High confidence when phone number provided
            logger.info("Phone number detected in conversation - boosting confidence to 0.85")

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

        # Boost confidence for explicit promise patterns (English)
        if "i'll send" in text or "i will send" in text:
            confidence += 0.2
        if "i'd be happy to" in text or "happy to text" in text or "glad to text" in text:
            confidence += 0.2

        # Boost confidence for explicit promise patterns (Spanish)
        if "te envío" in text or "te envio" in text or "te mando" in text:
            confidence += 0.2
        if "puedo enviarte" in text or "voy a enviarte" in text:
            confidence += 0.2
        if "te lo acabo de enviar" in text or "ya te lo envié" in text or "ya te lo envie" in text:
            confidence += 0.2

        # Boost confidence for multiple asset keywords
        keyword_count = sum(
            1
            for keyword in self.ASSET_KEYWORDS.get(asset_type, [])
            if keyword in text
        )
        confidence += min(keyword_count * 0.1, 0.2)

        # Boost confidence if "you" is mentioned (direct address) - English
        if "send you" in text or "text you" in text:
            confidence += 0.1

        # Boost confidence for Spanish direct address patterns
        if "enviarte" in text or "mandarte" in text:
            confidence += 0.1

        return min(confidence, 1.0)
