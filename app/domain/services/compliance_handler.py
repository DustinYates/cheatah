"""Compliance handler for SMS hard rules (STOP, HELP, DNC, etc.)."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class ComplianceResult:
    """Result of compliance check."""

    is_compliant: bool
    action: Literal["allow", "stop", "help", "opt_in", "dnc"] | None
    response_message: str | None = None


class ComplianceHandler:
    """Handler for SMS compliance keywords and hard rules."""

    # Compliance keywords (case-insensitive)
    STOP_KEYWORDS = ["stop", "stopall", "unsubscribe", "cancel", "end", "quit"]
    HELP_KEYWORDS = ["help", "info", "assistance"]
    OPT_IN_KEYWORDS = ["start", "yes", "subscribe", "begin", "join"]

    # Do Not Contact phrases - stronger than STOP, blocks ALL communication
    # These are phrase patterns that indicate the person wants no contact at all
    DNC_PHRASES = [
        r"don'?t contact me",
        r"do not contact me",
        r"stop contacting me",
        r"leave me alone",
        r"remove me from your list",
        r"take me off your list",
        r"never contact me again",
        r"don'?t call me",
        r"don'?t text me",
        r"don'?t email me",
        r"don'?t message me",
        r"remove my number",
        r"remove my info",
        r"delete my info",
        r"delete my number",
        r"stop messaging me",
        r"stop texting me",
        r"stop calling me",
        r"stop emailing me",
        r"i don'?t want to hear from you",
        r"i don'?t want any messages",
        r"please don'?t contact",
        r"no more contact",
        r"no more messages",
        r"no more texts",
        r"block me",
        r"opt me out",
        r"opt out of everything",
    ]

    # Compiled regex patterns for efficiency
    _dnc_patterns = None

    @classmethod
    def _get_dnc_patterns(cls) -> list[re.Pattern]:
        """Get compiled DNC regex patterns (lazy loaded)."""
        if cls._dnc_patterns is None:
            cls._dnc_patterns = [
                re.compile(pattern, re.IGNORECASE) for pattern in cls.DNC_PHRASES
            ]
        return cls._dnc_patterns

    def _is_dnc_request(self, message: str) -> bool:
        """Check if message is a Do Not Contact request.

        Args:
            message: User message text

        Returns:
            True if DNC phrase found
        """
        for pattern in self._get_dnc_patterns():
            if pattern.search(message):
                return True
        return False

    def check_compliance(self, message: str) -> ComplianceResult:
        """Check message for compliance keywords.

        Checks in order of priority:
        1. DNC phrases (strongest - blocks ALL channels)
        2. STOP keywords (blocks SMS only)
        3. HELP keywords
        4. OPT-IN keywords

        Args:
            message: User message text

        Returns:
            ComplianceResult with action and response
        """
        message_lower = message.strip().lower()

        # Check DNC phrases FIRST (highest priority - blocks all communication)
        if self._is_dnc_request(message):
            return ComplianceResult(
                is_compliant=False,
                action="dnc",
                response_message=(
                    "We've removed you from our contact list. "
                    "You will not receive any further communications from us."
                ),
            )

        # Check STOP keywords (SMS opt-out only)
        if any(keyword in message_lower for keyword in self.STOP_KEYWORDS):
            return ComplianceResult(
                is_compliant=False,
                action="stop",
                response_message=(
                    "You have been unsubscribed. You will no longer receive messages. "
                    "Reply START to opt back in."
                ),
            )
        
        # Check HELP keywords
        if any(keyword in message_lower for keyword in self.HELP_KEYWORDS):
            return ComplianceResult(
                is_compliant=True,
                action="help",
                response_message=(
                    "Reply STOP to unsubscribe, START to subscribe, or HELP for assistance. "
                    "Send your question and we'll help you."
                ),
            )
        
        # Check OPT-IN keywords
        if any(keyword in message_lower for keyword in self.OPT_IN_KEYWORDS):
            return ComplianceResult(
                is_compliant=True,
                action="opt_in",
                response_message="You have been subscribed. How can we help you?",
            )
        
        # Default: allow message
        return ComplianceResult(
            is_compliant=True,
            action="allow",
            response_message=None,
        )

    def is_stop_keyword(self, message: str) -> bool:
        """Check if message contains STOP keyword.
        
        Args:
            message: User message text
            
        Returns:
            True if STOP keyword found
        """
        message_lower = message.strip().lower()
        return any(keyword in message_lower for keyword in self.STOP_KEYWORDS)

    def is_help_keyword(self, message: str) -> bool:
        """Check if message contains HELP keyword.

        Args:
            message: User message text

        Returns:
            True if HELP keyword found
        """
        message_lower = message.strip().lower()
        return any(keyword in message_lower for keyword in self.HELP_KEYWORDS)

    def is_dnc_request(self, message: str) -> bool:
        """Check if message is a Do Not Contact request.

        Args:
            message: User message text

        Returns:
            True if DNC phrase found
        """
        return self._is_dnc_request(message)

