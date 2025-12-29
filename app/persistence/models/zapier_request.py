"""Zapier request tracking model for correlation."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, Index
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant
    from app.persistence.models.conversation import Conversation


class ZapierRequest(Base):
    """Track outbound Zapier requests and their responses (correlation tracking)."""

    __tablename__ = "zapier_requests"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Correlation
    correlation_id = Column(String(100), nullable=False, unique=True, index=True)

    # Request Details
    request_type = Column(String(50), nullable=False)  # "customer_lookup", "customer_query"
    request_payload = Column(JSON, nullable=False)
    request_sent_at = Column(DateTime, nullable=False)

    # Response Details
    response_payload = Column(JSON, nullable=True)
    response_received_at = Column(DateTime, nullable=True)

    # Status
    status = Column(String(30), default="pending", nullable=False)  # pending, completed, timeout, error
    error_message = Column(Text, nullable=True)

    # Context linking
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    phone_number = Column(String(50), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_zapier_requests_tenant_status", "tenant_id", "status"),
    )

    # Relationships
    tenant = relationship("Tenant")
    conversation = relationship("Conversation")

    def __repr__(self) -> str:
        return f"<ZapierRequest(id={self.id}, correlation_id={self.correlation_id}, status={self.status})>"
