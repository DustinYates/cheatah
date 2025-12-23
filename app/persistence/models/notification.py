"""Notification model for in-app notifications."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant, User


class Notification(Base):
    """In-app notification model for user alerts."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Nullable for tenant-wide notifications
    
    # Notification type: "call_summary", "escalation", "lead_captured", "system", etc.
    notification_type = Column(String(50), nullable=False, index=True)
    
    # Content
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Additional data (JSON)
    # Can contain: call_id, recording_url, lead_id, contact_id, etc.
    extra_data = Column(JSON, nullable=True)
    
    # Status
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    
    # Priority: "low", "normal", "high", "urgent"
    priority = Column(String(20), default="normal", nullable=False)
    
    # Action URL (optional) - deep link within the app
    action_url = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="notifications")
    user = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, tenant_id={self.tenant_id}, type={self.notification_type}, is_read={self.is_read})>"

    def mark_as_read(self) -> None:
        """Mark notification as read."""
        self.is_read = True
        self.read_at = datetime.utcnow()


# Notification types
class NotificationType:
    """Notification type constants."""
    CALL_SUMMARY = "call_summary"
    ESCALATION = "escalation"
    LEAD_CAPTURED = "lead_captured"
    HANDOFF = "handoff"
    VOICEMAIL = "voicemail"
    SYSTEM = "system"


# Notification priorities
class NotificationPriority:
    """Notification priority constants."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

