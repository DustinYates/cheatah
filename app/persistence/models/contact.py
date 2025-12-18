"""Contact model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class Contact(Base):
    """Contact model representing verified customer information."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    source = Column(String(50), nullable=True)  # 'web_chat_lead', 'sms_optin', 'manual', etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="contacts")

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, tenant_id={self.tenant_id}, email={self.email}, phone={self.phone})>"

