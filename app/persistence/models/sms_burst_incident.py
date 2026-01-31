"""SMS burst/spam incident model."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.persistence.database import Base


class SmsBurstIncident(Base):
    """Records detected SMS burst/spam incidents.

    Created when the burst detector identifies repeated outbound SMS
    to the same recipient within a short time window.
    """

    __tablename__ = "sms_burst_incidents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    to_number = Column(String(50), nullable=False)

    # Detection details
    message_count = Column(Integer, nullable=False)
    first_message_at = Column(DateTime, nullable=False)
    last_message_at = Column(DateTime, nullable=False)
    time_window_seconds = Column(Integer, nullable=False)
    avg_gap_seconds = Column(Float, nullable=False)

    # Severity indicators
    severity = Column(String(20), nullable=False, default="warning")
    has_identical_content = Column(Boolean, nullable=False, default=False)
    content_similarity_score = Column(Float, nullable=True)

    # Root cause hints
    likely_cause = Column(String(100), nullable=True)
    handler = Column(String(50), nullable=True)

    # Status tracking
    status = Column(String(20), nullable=False, default="active")
    auto_blocked = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)

    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_burst_tenant_detected", "tenant_id", "detected_at"),
        Index("ix_burst_status_severity", "status", "severity"),
        Index("ix_burst_tenant_number", "tenant_id", "to_number"),
    )

    def __repr__(self) -> str:
        return (
            f"<SmsBurstIncident(id={self.id}, tenant_id={self.tenant_id}, "
            f"to={self.to_number}, count={self.message_count}, severity={self.severity})>"
        )
