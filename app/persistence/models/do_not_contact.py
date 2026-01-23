"""Do Not Contact model for opt-out management."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.tenant import Tenant, User


class DoNotContact(Base):
    """Do Not Contact record for blocking all communications to a phone/email."""

    __tablename__ = "do_not_contact"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Identifiers (at least one required via DB constraint)
    phone_number = Column(String(50), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Source tracking
    source_channel = Column(String(50), nullable=False)  # "sms", "email", "voice", "manual"
    source_message = Column(Text, nullable=True)  # The message that triggered DNC
    source_conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    # Audit - creation
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL if auto-detected

    # Audit - deactivation (if they opt back in)
    deactivated_at = Column(DateTime, nullable=True)
    deactivated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deactivation_reason = Column(String(255), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="dnc_records")
    source_conversation = relationship("Conversation")
    created_by_user = relationship("User", foreign_keys=[created_by])
    deactivated_by_user = relationship("User", foreign_keys=[deactivated_by])

    def __repr__(self) -> str:
        identifier = self.phone_number or self.email
        return f"<DoNotContact(id={self.id}, tenant_id={self.tenant_id}, {identifier}, active={self.is_active})>"
