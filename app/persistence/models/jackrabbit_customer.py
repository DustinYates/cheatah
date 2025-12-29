"""Jackrabbit customer cache model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Index
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class JackrabbitCustomer(Base):
    """Cached customer data from Jackrabbit (via Zapier lookups)."""

    __tablename__ = "jackrabbit_customers"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Jackrabbit Identifiers
    jackrabbit_id = Column(String(100), nullable=False, index=True)

    # Customer Info (denormalized from Jackrabbit)
    phone_number = Column(String(50), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=True)

    # Additional Jackrabbit Data (flexible storage)
    customer_data = Column(JSON, nullable=True)  # Full customer record from Jackrabbit

    # Cache Management
    last_synced_at = Column(DateTime, nullable=False)
    cache_expires_at = Column(DateTime, nullable=True)  # Optional TTL

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_jackrabbit_tenant_phone", "tenant_id", "phone_number"),
        Index("ix_jackrabbit_tenant_jid", "tenant_id", "jackrabbit_id"),
    )

    # Relationships
    tenant = relationship("Tenant")

    def __repr__(self) -> str:
        return f"<JackrabbitCustomer(id={self.id}, jackrabbit_id={self.jackrabbit_id}, phone={self.phone_number})>"
