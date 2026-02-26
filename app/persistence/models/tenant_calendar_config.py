"""Tenant calendar configuration model for Google Calendar scheduling."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base
from app.persistence.types import EncryptedText

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantCalendarConfig(Base):
    """Tenant calendar configuration for Google Calendar meeting scheduling."""

    __tablename__ = "tenant_calendar_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # Enable/disable calendar scheduling
    is_enabled = Column(Boolean, default=False, nullable=False)

    # Google OAuth credentials (encrypted)
    google_email = Column(String(255), nullable=True)  # Connected Google account
    google_refresh_token = Column(EncryptedText(), nullable=True)
    google_access_token = Column(EncryptedText(), nullable=True)
    google_token_expires_at = Column(DateTime, nullable=True)

    # Calendar selection
    calendar_id = Column(String(255), nullable=True, default="primary")

    # Fallback booking link (used when Calendar API not connected)
    booking_link_url = Column(String(500), nullable=True)

    # Scheduling preferences (JSON)
    # Schema: {
    #   "meeting_duration_minutes": 30,
    #   "buffer_minutes": 15,
    #   "available_hours": {"start": "09:00", "end": "17:00"},
    #   "available_days": [0, 1, 2, 3, 4],  # Monday=0 through Friday=4
    #   "timezone": "America/New_York",
    #   "max_advance_days": 14,
    #   "meeting_title_template": "Meeting with {customer_name}",
    # }
    scheduling_preferences = Column(JSON, nullable=True, default=lambda: {
        "meeting_duration_minutes": 30,
        "buffer_minutes": 15,
        "min_notice_hours": 2,
        "available_hours": {"start": "09:00", "end": "17:00"},
        "available_days": [0, 1, 2, 3, 4],
        "timezone": "America/New_York",
        "max_advance_days": 14,
        "meeting_title_template": "Meeting with {customer_name}",
    })

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="calendar_config")

    def __repr__(self) -> str:
        return f"<TenantCalendarConfig(id={self.id}, tenant_id={self.tenant_id}, google_email={self.google_email})>"


# Default scheduling preferences for new tenants
DEFAULT_SCHEDULING_PREFERENCES = {
    "meeting_duration_minutes": 30,
    "buffer_minutes": 15,
    "min_notice_hours": 2,
    "available_hours": {"start": "09:00", "end": "17:00"},
    "available_days": [0, 1, 2, 3, 4],
    "timezone": "America/New_York",
    "max_advance_days": 14,
    "meeting_title_template": "Meeting with {customer_name}",
}
