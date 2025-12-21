"""ContactMergeLog model for audit trail of contact merges."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.tenant import Tenant, User


class ContactMergeLog(Base):
    """Audit log for contact merge operations."""

    __tablename__ = "contact_merge_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    primary_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    secondary_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    merged_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    merged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Store which field values were chosen from which contact
    # Example: {"email": "primary", "phone": "secondary", "name": "secondary"}
    field_resolutions = Column(JSON, nullable=True)
    
    # Backup of the secondary contact's data before merge
    # Example: {"email": "old@email.com", "phone": "555-1234", "name": "Old Name"}
    secondary_data_snapshot = Column(JSON, nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    primary_contact = relationship(
        "Contact",
        back_populates="merge_logs_as_primary",
        foreign_keys=[primary_contact_id]
    )
    secondary_contact = relationship(
        "Contact",
        foreign_keys=[secondary_contact_id]
    )
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ContactMergeLog(id={self.id}, primary={self.primary_contact_id}, secondary={self.secondary_contact_id}, at={self.merged_at})>"
