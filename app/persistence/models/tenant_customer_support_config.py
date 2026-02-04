"""Tenant customer support configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.persistence.database import Base
from app.persistence.types import EncryptedString

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantCustomerSupportConfig(Base):
    """Tenant configuration for customer support AI agent.

    This is separate from TenantCustomerServiceConfig (Zapier/Jackrabbit lookups).
    This config manages the dedicated customer support phone line and AI agent.
    """

    __tablename__ = "tenant_customer_support_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # Enable/disable customer support mode
    is_enabled = Column(Boolean, default=False, nullable=False)

    # Telnyx Configuration (separate from sales/leads agent)
    telnyx_agent_id = Column(String(255), nullable=True)  # Customer support AI agent
    telnyx_phone_number = Column(String(50), nullable=True)  # Dedicated support number
    telnyx_messaging_profile_id = Column(String(255), nullable=True)
    telnyx_api_key = Column(EncryptedString(255), nullable=True)  # Optional separate API key

    # Channel configuration
    support_sms_enabled = Column(Boolean, default=True, nullable=False)
    support_voice_enabled = Column(Boolean, default=True, nullable=False)

    # Routing rules (JSON)
    # Schema: {
    #   "business_hours_only": false,
    #   "fallback_to_human": true,
    #   "max_conversation_turns": 10,
    #   "auto_lookup_customer": true
    # }
    routing_rules = Column(JSONB, nullable=True, default=lambda: {
        "business_hours_only": False,
        "fallback_to_human": True,
        "max_conversation_turns": 10,
        "auto_lookup_customer": True,
    })

    # Transfer/escalation settings
    handoff_mode = Column(String(50), default="take_message", nullable=False)  # live_transfer, take_message
    transfer_number = Column(String(50), nullable=True)  # Human support line

    # System prompt override for support agent
    system_prompt_override = Column(Text, nullable=True)

    # Additional settings
    settings = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="customer_support_config")

    def __repr__(self) -> str:
        return f"<TenantCustomerSupportConfig(id={self.id}, tenant_id={self.tenant_id}, enabled={self.is_enabled})>"
