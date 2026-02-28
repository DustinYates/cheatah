"""Tenant pipeline stage configuration model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.persistence.database import Base


class TenantPipelineStage(Base):
    """Per-tenant pipeline stage definition for Kanban board."""

    __tablename__ = "tenant_pipeline_stages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_pipeline_stage_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    color = Column(String(7), nullable=False, default="#6b7280")
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tenant = relationship("Tenant", back_populates="pipeline_stages")

    def __repr__(self) -> str:
        return f"<TenantPipelineStage(id={self.id}, tenant_id={self.tenant_id}, key={self.key}, label={self.label})>"
