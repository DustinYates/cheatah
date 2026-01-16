"""Service for managing pending promises when phone isn't available yet.

When the chatbot promises to text information but doesn't have the user's
phone number, the promise is stored as "pending". When the phone is later
collected, pending promises are automatically fulfilled.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.promise_detector import DetectedPromise
from app.persistence.models.lead import Lead

logger = logging.getLogger(__name__)


@dataclass
class PendingPromise:
    """A promise that couldn't be fulfilled yet (no phone available)."""

    asset_type: str
    confidence: float
    original_text: str
    detected_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingPromise":
        """Create from dictionary loaded from JSON."""
        return cls(
            asset_type=data.get("asset_type", ""),
            confidence=data.get("confidence", 0.0),
            original_text=data.get("original_text", ""),
            detected_at=data.get("detected_at", ""),
        )

    def to_detected_promise(self) -> DetectedPromise:
        """Convert back to DetectedPromise for fulfillment."""
        return DetectedPromise(
            asset_type=self.asset_type,
            confidence=self.confidence,
            original_text=self.original_text,
        )


class PendingPromiseService:
    """Manages pending promises stored in Lead.extra_data.

    Pending promises are tracked when the chatbot promises to text
    information but the user hasn't provided a phone number yet.
    When the phone is later collected, these promises are automatically
    fulfilled.
    """

    PENDING_KEY = "pending_promises"
    FULFILLED_KEY = "fulfilled_promises"

    def __init__(self, session: AsyncSession):
        self.session = session

    def _get_extra_data(self, lead: Lead) -> dict[str, Any]:
        """Safely get extra_data as a dict."""
        extra_data = lead.extra_data or {}
        if isinstance(extra_data, str):
            try:
                extra_data = json.loads(extra_data)
            except json.JSONDecodeError:
                extra_data = {}
        return extra_data

    async def store_pending_promise(
        self, lead: Lead, promise: DetectedPromise
    ) -> None:
        """Store a promise that couldn't be fulfilled (no phone yet).

        Args:
            lead: The lead to store the promise for
            promise: The detected promise to store
        """
        extra_data = self._get_extra_data(lead)
        pending = extra_data.get(self.PENDING_KEY, [])

        # Avoid duplicates - only one pending promise per asset_type
        existing_types = {p.get("asset_type") for p in pending}
        if promise.asset_type in existing_types:
            logger.debug(
                f"Pending promise already exists for lead {lead.id}: {promise.asset_type}"
            )
            return

        pending.append({
            "asset_type": promise.asset_type,
            "confidence": promise.confidence,
            "original_text": (promise.original_text or "")[:500],  # Truncate for safety
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

        extra_data[self.PENDING_KEY] = pending
        lead.extra_data = extra_data
        await self.session.commit()

        logger.info(
            f"Stored pending promise for lead {lead.id}: "
            f"asset_type={promise.asset_type}, confidence={promise.confidence:.2f}"
        )

    async def get_pending_promises(self, lead: Lead) -> list[PendingPromise]:
        """Get all pending promises for a lead.

        Args:
            lead: The lead to get promises for

        Returns:
            List of pending promises
        """
        extra_data = self._get_extra_data(lead)
        pending = extra_data.get(self.PENDING_KEY, [])
        return [PendingPromise.from_dict(p) for p in pending]

    async def has_pending_promises(self, lead: Lead) -> bool:
        """Check if lead has any pending promises.

        Args:
            lead: The lead to check

        Returns:
            True if there are pending promises
        """
        promises = await self.get_pending_promises(lead)
        return len(promises) > 0

    async def mark_promise_fulfilled(
        self, lead: Lead, asset_type: str, result: dict[str, Any]
    ) -> None:
        """Mark a pending promise as fulfilled and remove from pending.

        Args:
            lead: The lead whose promise was fulfilled
            asset_type: The type of asset that was fulfilled
            result: The fulfillment result (status, message_id, etc.)
        """
        extra_data = self._get_extra_data(lead)

        # Remove from pending
        pending = extra_data.get(self.PENDING_KEY, [])
        pending = [p for p in pending if p.get("asset_type") != asset_type]
        extra_data[self.PENDING_KEY] = pending

        # Add to fulfilled history
        fulfilled = extra_data.get(self.FULFILLED_KEY, [])
        fulfilled.append({
            "asset_type": asset_type,
            "status": result.get("status"),
            "message_id": result.get("message_id"),
            "fulfilled_at": datetime.now(timezone.utc).isoformat(),
        })
        extra_data[self.FULFILLED_KEY] = fulfilled

        lead.extra_data = extra_data
        await self.session.commit()

        logger.info(
            f"Marked promise fulfilled for lead {lead.id}: "
            f"asset_type={asset_type}, status={result.get('status')}"
        )

    async def clear_pending_promises(self, lead: Lead) -> None:
        """Clear all pending promises for a lead.

        Args:
            lead: The lead to clear promises for
        """
        extra_data = self._get_extra_data(lead)
        extra_data[self.PENDING_KEY] = []
        lead.extra_data = extra_data
        await self.session.commit()

        logger.info(f"Cleared pending promises for lead {lead.id}")
