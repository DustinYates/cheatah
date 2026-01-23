"""Lead model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.contact import Contact
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.tenant import Tenant


class Lead(Base):
    """Lead model representing captured customer information."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True, default='new', index=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="leads")
    conversation = relationship("Conversation", back_populates="leads")
    contact = relationship("Contact", back_populates="leads", foreign_keys=[contact_id])
    call_summaries = relationship("CallSummary", back_populates="lead")

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, tenant_id={self.tenant_id}, email={self.email}, phone={self.phone}, status={self.status})>"
