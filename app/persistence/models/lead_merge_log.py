"""LeadMergeLog model for audit trail of lead merges."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.lead import Lead
    from app.persistence.models.tenant import Tenant


class LeadMergeLog(Base):
    """Audit log for lead merge operations."""

    __tablename__ = "lead_merge_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    primary_lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    secondary_lead_id = Column(Integer, nullable=False)  # No FK — secondary gets deleted
    merged_by = Column(Integer, default=0, nullable=False)  # 0 = system auto-merge
    merged_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Store which field values were chosen from which lead
    # Example: {"email": "primary", "phone": "secondary", "name": "secondary"}
    field_resolutions = Column(JSONB, nullable=True)

    # Backup of the secondary lead's data before merge
    secondary_data_snapshot = Column(JSONB, nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    primary_lead = relationship("Lead", foreign_keys=[primary_lead_id])

    def __repr__(self) -> str:
        return f"<LeadMergeLog(id={self.id}, primary={self.primary_lead_id}, secondary={self.secondary_lead_id}, at={self.merged_at})>"
