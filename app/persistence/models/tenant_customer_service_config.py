"""Tenant customer service configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base
from app.persistence.types import EncryptedString

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantCustomerServiceConfig(Base):
    """Tenant configuration for customer service via Jackrabbit/Zapier."""

    __tablename__ = "tenant_customer_service_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # Enable/disable customer service mode
    is_enabled = Column(Boolean, default=False, nullable=False)

    # Zapier Configuration
    zapier_webhook_url = Column(Text, nullable=True)  # Outbound webhook to Zapier
    zapier_callback_secret = Column(EncryptedString(255), nullable=True)  # Encrypted

    # Lookup Configuration
    customer_lookup_timeout_seconds = Column(Integer, default=30, nullable=False)

    # Query Configuration
    query_timeout_seconds = Column(Integer, default=45, nullable=False)

    # LLM Fallback Settings
    llm_fallback_enabled = Column(Boolean, default=True, nullable=False)
    llm_fallback_prompt_override = Column(Text, nullable=True)  # Custom prompt for customer service

    # Routing Rules (JSON)
    # Schema: {
    #   "enable_sms": true,
    #   "enable_voice": true,
    #   "fallback_to_lead_capture": true,  # If customer not found
    #   "auto_respond_pending_lookup": true,  # "Please hold while I look up your account"
    # }
    routing_rules = Column(JSON, nullable=True, default=lambda: {
        "enable_sms": True,
        "enable_voice": True,
        "fallback_to_lead_capture": True,
        "auto_respond_pending_lookup": True,
    })

    # Additional flexible settings
    settings = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="customer_service_config")

    def __repr__(self) -> str:
        return f"<TenantCustomerServiceConfig(id={self.id}, tenant_id={self.tenant_id}, enabled={self.is_enabled})>"
