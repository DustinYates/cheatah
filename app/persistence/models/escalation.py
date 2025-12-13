"""Escalation model for handoff requests and admin notifications."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.tenant import Tenant, User


class Escalation(Base):
    """Escalation record for handoff requests and admin notifications."""

    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    
    # Escalation details
    reason = Column(String(100), nullable=False)  # "low_confidence", "explicit_request", "manual", etc.
    status = Column(String(50), default="pending", nullable=False)  # "pending", "notified", "resolved", "cancelled"
    
    # Detection metadata
    confidence_score = Column(String(50), nullable=True)  # LLM confidence if applicable
    trigger_message = Column(Text, nullable=True)  # Message that triggered escalation
    
    # Notification tracking
    admin_notified_at = Column(DateTime, nullable=True)
    notification_methods = Column(JSON, nullable=True)  # ["email", "sms"] - which methods were used
    notification_status = Column(JSON, nullable=True)  # Status of each notification attempt
    
    # Resolution
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Admin user who resolved
    resolution_notes = Column(Text, nullable=True)
    
    # Additional metadata
    escalation_metadata = Column("metadata", JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="escalations")
    conversation = relationship("Conversation", back_populates="escalations")

    def __repr__(self) -> str:
        return f"<Escalation(id={self.id}, tenant_id={self.tenant_id}, reason={self.reason}, status={self.status})>"

