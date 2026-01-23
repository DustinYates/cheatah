"""Tenant widget configuration model."""

import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantWidgetConfig(Base):
    """Tenant widget configuration model."""

    __tablename__ = "tenant_widget_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # All widget customization settings stored as JSON
    settings = Column(JSON, nullable=True)

    # API key for public chat endpoint authentication (64 hex chars)
    widget_api_key = Column(String(64), nullable=True, unique=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="widget_config")

    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure API key (32 bytes = 64 hex chars)."""
        return secrets.token_hex(32)

    def __repr__(self) -> str:
        return f"<TenantWidgetConfig(id={self.id}, tenant_id={self.tenant_id})>"
