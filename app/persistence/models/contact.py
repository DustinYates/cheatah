"""Contact model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.contact_alias import ContactAlias
    from app.persistence.models.contact_merge_log import ContactMergeLog
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.lead import Lead
    from app.persistence.models.tenant import Tenant, User


class Contact(Base):
    """Contact model representing verified customer information."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Soft delete columns
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Merge tracking columns
    merged_into_contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    merged_at = Column(DateTime, nullable=True)
    merged_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="contacts")
    # New one-to-many relationship: one contact can have many leads
    leads = relationship("Lead", back_populates="contact", foreign_keys="Lead.contact_id")
    # Deprecated: old one-to-one relationship via lead_id (kept for backward compat)
    _legacy_lead = relationship("Lead", foreign_keys=[lead_id], overlaps="contact,leads")
    
    # Alias relationships
    aliases = relationship(
        "ContactAlias",
        back_populates="contact",
        foreign_keys="ContactAlias.contact_id",
        cascade="all, delete-orphan"
    )
    
    # Merge log relationships
    merge_logs_as_primary = relationship(
        "ContactMergeLog",
        back_populates="primary_contact",
        foreign_keys="ContactMergeLog.primary_contact_id"
    )
    
    # Self-referential relationship for merged contacts
    merged_into = relationship(
        "Contact",
        remote_side="Contact.id",
        foreign_keys=[merged_into_contact_id],
        backref="merged_contacts"
    )
    
    # User relationships for audit
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    merged_by_user = relationship("User", foreign_keys=[merged_by])
    
    # Call summaries
    call_summaries = relationship("CallSummary", back_populates="contact")

    # Conversations linked to this contact
    conversations = relationship("Conversation", back_populates="contact")

    # Email conversations
    email_conversations = relationship("EmailConversation", back_populates="contact")

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, tenant_id={self.tenant_id}, email={self.email}, phone={self.phone})>"
