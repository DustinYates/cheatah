"""Pub/Sub for async job processing including Gmail push notifications."""

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

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


class PubSubPublisher:
    """Pub/Sub publisher for async job processing."""

    async def publish(self, topic: str, message: dict[str, Any]) -> str:
        """Publish a message to a topic.

        Args:
            topic: Topic name
            message: Message dictionary

        Returns:
            Message ID (stub)

        Note:
            This is a skeleton implementation. Real publishing will be
            implemented in later phases.
        """
        # Stub: Just return a placeholder message ID
        return f"msg_{topic}_{hash(str(message))}"


class PubSubWorker:
    """Pub/Sub worker for processing push notifications."""

    async def process_message(self, message: dict[str, Any]) -> None:
        """Process a message from a subscription.

        Args:
            message: Message dictionary

        Note:
            This is a skeleton implementation. Real message processing
            will be implemented in later phases.
        """
        # Stub: No-op
        pass


def verify_pubsub_token(token: str | None) -> bool:
    """Verify Pub/Sub push notification token.
    
    For Gmail push notifications, Google Cloud Pub/Sub sends a bearer token
    that should be verified against our expected value.
    
    Args:
        token: Bearer token from Authorization header
        
    Returns:
        True if token is valid (or if no verification is configured)
    """
    # In production, implement proper token verification
    # For now, accept all tokens (configure in settings for production)
    if not token:
        return True
    
    # TODO: Add token verification when pubsub_auth_token is configured
    return True


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


# Global instances
pubsub_publisher = PubSubPublisher()
pubsub_worker = PubSubWorker()

