"""Compliance handler for SMS hard rules (STOP, HELP, etc.)."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ComplianceResult:
    """Result of compliance check."""
    
    is_compliant: bool
    action: Literal["allow", "stop", "help", "opt_in"] | None
    response_message: str | None = None


class ComplianceHandler:
    """Handler for SMS compliance keywords and hard rules."""

    # Compliance keywords (case-insensitive)
    STOP_KEYWORDS = ["stop", "stopall", "unsubscribe", "cancel", "end", "quit"]
    HELP_KEYWORDS = ["help", "info", "assistance"]
    OPT_IN_KEYWORDS = ["start", "yes", "subscribe", "begin", "join"]
    
    def check_compliance(self, message: str) -> ComplianceResult:
        """Check message for compliance keywords.
        
        Args:
            message: User message text
            
        Returns:
            ComplianceResult with action and response
        """
        message_lower = message.strip().lower()
        
        # Check STOP keywords
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

