"""Email ingestion log model for deduplication and audit trail."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.persistence.database import Base


class IngestionStatus(str, Enum):
    """Status of email ingestion processing."""

    RECEIVED = "received"  # Initial state, queued for processing
    PROCESSED = "processed"  # Successfully created lead
    FAILED = "failed"  # Processing error occurred
    DUPLICATE = "duplicate"  # Duplicate email detected
    SKIPPED = "skipped"  # Skipped (subject doesn't match prefixes, etc.)


class EmailIngestionLog(Base):
    """Email ingestion log for SendGrid Inbound Parse deduplication and audit.

    Tracks all incoming emails from SendGrid, provides deduplication via Message-ID,
    and stores raw payload for debugging and replay.
    """

    __tablename__ = "email_ingestion_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Deduplication key (RFC 2822 Message-ID or hash fallback)
    message_id = Column(String(255), nullable=False, index=True)
    message_id_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hash fallback

    # Email metadata
    from_email = Column(String(255), nullable=False)
    to_email = Column(String(255), nullable=True)  # Parse address that received it
    subject = Column(String(500), nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Processing status
    status = Column(String(50), default=IngestionStatus.RECEIVED.value, nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    error_message = Column(Text, nullable=True)

    # Raw payload storage for audit/debugging/replay
    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    lead = relationship("Lead", foreign_keys=[lead_id])

    # Composite unique constraint for deduplication
    __table_args__ = (
        UniqueConstraint("tenant_id", "message_id", name="uq_ingestion_tenant_message"),
    )

    def __repr__(self) -> str:
        return (
            f"<EmailIngestionLog(id={self.id}, tenant_id={self.tenant_id}, "
            f"message_id={self.message_id[:30]}..., status={self.status})>"
        )
