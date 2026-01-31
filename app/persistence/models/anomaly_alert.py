"""Anomaly detection alert model."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)

from app.persistence.database import Base


class AnomalyAlert(Base):
    """Anomaly detected in communications metrics.

    Created by the health_snapshot_worker when metric values
    deviate significantly from their 7-day rolling baseline.
    """

    __tablename__ = "anomaly_alerts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    alert_type = Column(String(50), nullable=False)  # volume_drop, escalation_spike, duration_spike, burst_detected
    severity = Column(String(20), nullable=False, default="warning")  # info, warning, critical
    metric_name = Column(String(100), nullable=False)

    current_value = Column(Float, nullable=False)
    baseline_value = Column(Float, nullable=False)
    threshold_percent = Column(Float, nullable=False)

    details = Column(JSON, nullable=True)

    status = Column(String(20), nullable=False, default="active")  # active, acknowledged, resolved

    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_anomaly_tenant_detected", "tenant_id", "detected_at"),
        Index("ix_anomaly_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnomalyAlert(id={self.id}, tenant={self.tenant_id}, "
            f"type={self.alert_type}, severity={self.severity})>"
        )
