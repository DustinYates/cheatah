"""ContactAlias model for storing secondary identifiers."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact


class ContactAlias(Base):
    """Model for storing secondary identifiers (emails, phones, names) for contacts."""

    __tablename__ = "contact_aliases"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    alias_type = Column(String(50), nullable=False)  # 'email', 'phone', 'name'
    value = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    source_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    contact = relationship(
        "Contact",
        back_populates="aliases",
        foreign_keys=[contact_id]
    )
    source_contact = relationship(
        "Contact",
        foreign_keys=[source_contact_id]
    )

    def __repr__(self) -> str:
        primary_str = " (primary)" if self.is_primary else ""
        return f"<ContactAlias(id={self.id}, contact_id={self.contact_id}, type={self.alias_type}, value={self.value}{primary_str})>"
