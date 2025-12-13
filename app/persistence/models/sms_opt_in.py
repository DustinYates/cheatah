"""SMS opt-in tracking model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class SmsOptIn(Base):
    """SMS opt-in tracking per phone number per tenant."""

    __tablename__ = "sms_opt_ins"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    phone_number = Column(String(50), nullable=False, index=True)
    
    # Opt-in status
    is_opted_in = Column(Boolean, default=False, nullable=False)
    
    # Opt-in/out tracking
    opted_in_at = Column(DateTime, nullable=True)
    opted_out_at = Column(DateTime, nullable=True)
    opt_in_method = Column(String(50), nullable=True)  # "keyword", "manual", "api", etc.
    opt_out_method = Column(String(50), nullable=True)  # "STOP", "manual", "api", etc.
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="sms_opt_ins")

    def __repr__(self) -> str:
        return f"<SmsOptIn(id={self.id}, tenant_id={self.tenant_id}, phone={self.phone_number}, opted_in={self.is_opted_in})>"

