"""Tenant SMS configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base
from app.persistence.types import EncryptedString

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantSmsConfig(Base):
    """Tenant SMS configuration model."""

    __tablename__ = "tenant_sms_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    
    # Enable/disable
    is_enabled = Column(Boolean, default=False, nullable=False)

    # Provider selection (twilio or telnyx)
    provider = Column(String(20), default="twilio", nullable=False)

    # Twilio configuration
    twilio_account_sid = Column(String(255), nullable=True)
    twilio_auth_token = Column(EncryptedString(255), nullable=True)  # Encrypted
    twilio_phone_number = Column(String(50), nullable=True)  # Tenant's Twilio phone number

    # Telnyx configuration
    telnyx_api_key = Column(EncryptedString(255), nullable=True)  # Encrypted
    telnyx_messaging_profile_id = Column(String(255), nullable=True)  # Required for SMS
    telnyx_connection_id = Column(String(255), nullable=True)  # Required for Voice/TeXML
    telnyx_phone_number = Column(String(50), nullable=True)  # Tenant's Telnyx phone number

    # Voice configuration
    voice_enabled = Column(Boolean, default=False, nullable=False)
    voice_phone_number = Column(String(50), nullable=True)  # Optional separate voice number

    # Business hours
    business_hours_enabled = Column(Boolean, default=False, nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)  # e.g., "America/New_York"
    business_hours = Column(JSON, nullable=True)  # {"monday": {"start": "09:00", "end": "17:00"}, ...}
    
    # Auto-reply rules
    auto_reply_outside_hours = Column(Boolean, default=False, nullable=False)
    auto_reply_message = Column(Text, nullable=True)  # Message to send outside business hours
    
    # Additional settings
    settings = Column(JSON, nullable=True)  # Flexible settings storage
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="sms_config")

    def __repr__(self) -> str:
        return f"<TenantSmsConfig(id={self.id}, tenant_id={self.tenant_id}, enabled={self.is_enabled})>"

