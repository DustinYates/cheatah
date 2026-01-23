"""Pub/Sub for async job processing including Gmail push notifications."""

import base64
import json
import logging
from dataclasses import dataclass

from app.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class GmailPushNotification:
    """Parsed Gmail push notification from Pub/Sub."""
    
    email_address: str
    history_id: str
    
    @classmethod
    def from_pubsub_message(cls, data: str) -> "GmailPushNotification":
        """Parse Gmail push notification from Pub/Sub message data.
        
        Args:
            data: Base64-encoded message data from Pub/Sub
            
        Returns:
            Parsed GmailPushNotification
            
        Raises:
            ValueError: If message format is invalid
        """
        try:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8")
            payload = json.loads(decoded)
            
            return cls(
                email_address=payload.get("emailAddress", ""),
                history_id=payload.get("historyId", ""),
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse Gmail push notification: {e}")
            raise ValueError(f"Invalid Gmail push notification format: {e}") from e


def verify_pubsub_token(token: str | None) -> bool:
    """Verify Pub/Sub push notification token.

    For Gmail push notifications, Google Cloud Pub/Sub sends a bearer token
    that should be verified against our expected value.

    Args:
        token: Bearer token from Authorization header

    Returns:
        True if token is valid (or if no verification is configured)
    """
    import hmac

    # If no auth token is configured, accept all requests (development mode)
    if not settings.gmail_pubsub_auth_token:
        if token:
            logger.warning("Pub/Sub token received but GMAIL_PUBSUB_AUTH_TOKEN not configured")
        return True

    # Token is required when auth is configured
    if not token:
        logger.warning("Pub/Sub request missing token but GMAIL_PUBSUB_AUTH_TOKEN is configured")
        return False

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(token, settings.gmail_pubsub_auth_token)
    if not is_valid:
        logger.warning("Invalid Pub/Sub token received")

    return is_valid


def get_gmail_pubsub_topic() -> str | None:
    """Get the full Gmail Pub/Sub topic name.
    
    Returns:
        Full topic path or None if not configured
    """
    if settings.gmail_pubsub_topic:
        # If already a full path, return as-is
        if settings.gmail_pubsub_topic.startswith("projects/"):
            return settings.gmail_pubsub_topic
        # Otherwise, build full path
        return f"projects/{settings.gcp_project_id}/topics/{settings.gmail_pubsub_topic}"
    return None

