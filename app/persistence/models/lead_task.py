"""Lead task model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.lead import Lead
    from app.persistence.models.tenant import Tenant


class LeadTask(Base):
    """Task/to-do item associated with a lead."""

    __tablename__ = "lead_tasks"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    due_date = Column(DateTime, nullable=True, index=True)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    lead = relationship("Lead", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<LeadTask(id={self.id}, lead_id={self.lead_id}, title={self.title!r}, completed={self.is_completed})>"
