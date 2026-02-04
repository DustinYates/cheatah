"""Customer model for verified existing customers (synced from Jackrabbit)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
    from app.persistence.models.tenant import Tenant


class Customer(Base):
    """Customer model representing verified existing customers.

    Unlike leads/contacts (potential customers), this table stores
    verified account holders synced from external CRM (Jackrabbit).
    """

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Link to contact record (if exists)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)

    # Link to Jackrabbit cache (if synced from Jackrabbit)
    jackrabbit_customer_id = Column(Integer, ForeignKey("jackrabbit_customers.id"), nullable=True, index=True)

    # External CRM identifier
    external_customer_id = Column(String(100), nullable=True, index=True)  # Jackrabbit ID or other CRM

    # Customer info
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=False, index=True)  # Primary identifier

    # Account status
    status = Column(String(50), default="active", nullable=False)  # active, inactive, suspended
    account_type = Column(String(50), nullable=True)  # family, individual, business

    # Account data (flexible JSON storage)
    # Schema: {balance, enrollments, membership_status, payment_history_summary, ...}
    account_data = Column(JSONB, nullable=True)

    # Sync management
    last_synced_at = Column(DateTime, nullable=True)
    sync_source = Column(String(50), nullable=True)  # jackrabbit, manual, import

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_customers_tenant_phone", "tenant_id", "phone", unique=True),
        Index("ix_customers_tenant_external_id", "tenant_id", "external_customer_id"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="customers")
    contact = relationship("Contact", foreign_keys=[contact_id])
    jackrabbit_customer = relationship("JackrabbitCustomer", foreign_keys=[jackrabbit_customer_id])

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, tenant_id={self.tenant_id}, name={self.name}, phone={self.phone})>"
