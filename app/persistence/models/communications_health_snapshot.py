"""Pre-aggregated communications health metrics."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)

from app.persistence.database import Base


class CommunicationsHealthSnapshot(Base):
    """Hourly/daily pre-aggregated communications metrics per tenant.

    Populated by the health_snapshot_worker every hour.
    snapshot_hour is 0-23 for hourly rows, NULL for daily rollups.
    """

    __tablename__ = "communications_health_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    snapshot_date = Column(DateTime, nullable=False)  # Date only (time truncated)
    snapshot_hour = Column(Integer, nullable=True)  # 0-23 or NULL for daily

    # Channel volume
    total_calls = Column(Integer, nullable=False, default=0)
    inbound_calls = Column(Integer, nullable=False, default=0)
    outbound_calls = Column(Integer, nullable=False, default=0)
    total_sms = Column(Integer, nullable=False, default=0)
    inbound_sms = Column(Integer, nullable=False, default=0)
    outbound_sms = Column(Integer, nullable=False, default=0)
    total_emails = Column(Integer, nullable=False, default=0)
    inbound_emails = Column(Integer, nullable=False, default=0)
    outbound_emails = Column(Integer, nullable=False, default=0)

    # Call duration metrics
    total_call_minutes = Column(Float, nullable=False, default=0.0)
    avg_call_duration_seconds = Column(Float, nullable=False, default=0.0)
    median_call_duration_seconds = Column(Float, nullable=False, default=0.0)
    short_calls_count = Column(Integer, nullable=False, default=0)  # <30s
    long_calls_count = Column(Integer, nullable=False, default=0)  # >10min

    # Bot vs human workload
    bot_handled_count = Column(Integer, nullable=False, default=0)
    human_handled_count = Column(Integer, nullable=False, default=0)
    escalated_count = Column(Integer, nullable=False, default=0)
    bot_resolution_count = Column(Integer, nullable=False, default=0)
    avg_time_to_escalation_seconds = Column(Float, nullable=False, default=0.0)

    # Reliability
    dropped_calls_count = Column(Integer, nullable=False, default=0)
    failed_calls_count = Column(Integer, nullable=False, default=0)
    failed_sms_count = Column(Integer, nullable=False, default=0)
    bounced_emails_count = Column(Integer, nullable=False, default=0)
    api_errors_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "snapshot_date", "snapshot_hour",
            name="uix_tenant_snapshot_date_hour",
        ),
        Index("ix_snapshot_tenant_date", "tenant_id", "snapshot_date"),
    )

    def __repr__(self) -> str:
        hour = f"h{self.snapshot_hour}" if self.snapshot_hour is not None else "daily"
        return (
            f"<CommunicationsHealthSnapshot(tenant={self.tenant_id}, "
            f"date={self.snapshot_date}, {hour})>"
        )
