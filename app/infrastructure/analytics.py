"""Analytics event emitter utility."""

import json
from datetime import datetime
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)


class AnalyticsEvent:
    """Analytics event model."""

    def __init__(
        self,
        event_type: str,
        tenant_id: int | None = None,
        user_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize analytics event.

        Args:
            event_type: Event type (e.g., "conversation.created")
            tenant_id: Optional tenant ID
            user_id: Optional user ID
            data: Optional event data
        """
        self.event_type = event_type
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.data = data or {}
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())


class AnalyticsEmitter:
    """Analytics event emitter."""

    def emit(self, event: AnalyticsEvent) -> None:
        """Emit an analytics event.

        Args:
            event: Analytics event to emit

        Note:
            In Phase 0, events are logged. In future phases, they may be
            sent to Pub/Sub, BigQuery, or other analytics systems.
        """
        # Log the event (structured logging)
        logger.info(
            "Analytics event",
            extra={
                "event_type": event.event_type,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "event_data": event.data,
            },
        )

        # Future: Send to Pub/Sub, BigQuery, etc.


# Global emitter instance
analytics_emitter = AnalyticsEmitter()

