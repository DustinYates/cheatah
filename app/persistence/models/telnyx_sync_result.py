"""Telnyx sync result model for tracking data discrepancies between our DB and Telnyx API."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.persistence.database import Base


class TelnyxSyncResult(Base):
    """Tracks discrepancies found between local DB and Telnyx API.

    Created by the telnyx_sync_worker (hourly) or on-demand admin checks.
    Types: missing_call, missing_sms, stale_delivery.
    """

    __tablename__ = "telnyx_sync_results"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Discrepancy classification
    sync_type = Column(
        String(30), nullable=False
    )  # missing_call, missing_sms, stale_delivery
    severity = Column(
        String(20), nullable=False, default="warning"
    )  # info, warning, critical
    status = Column(
        String(20), nullable=False, default="open"
    )  # open, backfilled, dismissed

    # Telnyx reference data
    telnyx_conversation_id = Column(String(255), nullable=True)
    telnyx_call_control_id = Column(String(255), nullable=True)
    telnyx_message_id = Column(String(255), nullable=True)

    # Flexible details (phone, channel, expected vs actual status, etc.)
    details = Column(JSONB, nullable=False, server_default="{}")

    # Resolution tracking
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(
        String(50), nullable=True
    )  # auto_backfill, manual, dismissed

    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_sync_results_tenant_status", "tenant_id", "status"),
        Index("ix_sync_results_detected", "detected_at"),
        Index("ix_sync_results_type", "sync_type", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<TelnyxSyncResult(id={self.id}, tenant={self.tenant_id}, "
            f"type={self.sync_type}, severity={self.severity}, status={self.status})>"
        )
