"""Pub/Sub skeleton for async job processing."""

from typing import Any


class PubSubPublisher:
    """Pub/Sub publisher stub (no real publishing in Phase 0)."""

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
    """Pub/Sub worker skeleton (no real processing in Phase 0)."""

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


# Global instances
pubsub_publisher = PubSubPublisher()
pubsub_worker = PubSubWorker()

