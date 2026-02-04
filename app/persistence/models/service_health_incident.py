"""Service health incident model for tracking external service failures."""

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

from app.persistence.database import Base


class ServiceHealthIncident(Base):
    """Tracks external service failures (Telnyx, Gmail, Gemini, etc.).

    Used to detect and notify admins when external services are experiencing issues.
    Supports both tenant-specific incidents (e.g., tenant's Gmail token expired)
    and global incidents (e.g., Gemini API down for all tenants).
    """

    __tablename__ = "service_health_incidents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )  # NULL for global incidents

    # Service identification
    service_name = Column(String(50), nullable=False)  # telnyx, gmail, gemini, sendgrid
    error_type = Column(String(100), nullable=False)  # timeout, auth_failed, rate_limited, api_error

    # Error details
    error_message = Column(Text, nullable=True)
    error_count = Column(Integer, nullable=False, default=1)

    # Timestamps
    first_error_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_error_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Severity and status
    severity = Column(String(20), nullable=False, default="warning")  # info, warning, critical
    status = Column(String(20), nullable=False, default="active")  # active, acknowledged, resolved

    # Admin notification tracking
    admin_notified_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_service_health_service_status", "service_name", "status"),
        Index("ix_service_health_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        tenant_str = f"tenant={self.tenant_id}" if self.tenant_id else "global"
        return (
            f"<ServiceHealthIncident(id={self.id}, {tenant_str}, "
            f"service={self.service_name}, errors={self.error_count}, severity={self.severity})>"
        )
