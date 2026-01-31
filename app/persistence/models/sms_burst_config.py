"""Per-tenant SMS burst detection configuration."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)

from app.persistence.database import Base


class SmsBurstConfig(Base):
    """Per-tenant configuration for SMS burst detection thresholds.

    One row per tenant. If no row exists, system defaults apply.
    """

    __tablename__ = "sms_burst_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True)

    # Master toggle
    enabled = Column(Boolean, nullable=False, default=True)

    # Detection window
    time_window_seconds = Column(Integer, nullable=False, default=180)  # 3 minutes

    # Message count thresholds
    message_threshold = Column(Integer, nullable=False, default=3)
    high_severity_threshold = Column(Integer, nullable=False, default=5)

    # Rapid gap detection (flag if avg gap in this range)
    rapid_gap_min_seconds = Column(Integer, nullable=False, default=5)
    rapid_gap_max_seconds = Column(Integer, nullable=False, default=29)

    # Content repetition detection
    identical_content_threshold = Column(Integer, nullable=False, default=2)
    similarity_threshold = Column(Float, nullable=False, default=0.9)

    # Auto-blocking
    auto_block_enabled = Column(Boolean, nullable=False, default=False)
    auto_block_threshold = Column(Integer, nullable=False, default=10)

    # Exclusions (flow types that should not trigger detection)
    excluded_flows = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<SmsBurstConfig(tenant_id={self.tenant_id}, enabled={self.enabled}, "
            f"window={self.time_window_seconds}s, threshold={self.message_threshold})>"
        )
