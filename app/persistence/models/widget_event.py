"""Widget event model for tracking widget engagement analytics."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class WidgetEvent(Base):
    """Raw widget engagement events from client-side tracking."""

    __tablename__ = "widget_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Event identification
    event_type = Column(String(50), nullable=False, index=True)
    # Types: impression, render_success, render_failure, viewport_visible,
    #        widget_open, manual_open, auto_open, auto_open_dismiss,
    #        hover, focus, first_message, lead_collected

    # Session tracking
    visitor_id = Column(String(100), nullable=False, index=True)  # Persistent browser UUID
    session_id = Column(String(100), nullable=True, index=True)  # Chat session_id if available

    # Context data (stored as JSON for flexibility)
    event_data = Column(JSON, nullable=True)
    # Examples:
    #   - impression: { page_url, referrer, viewport_width, viewport_height }
    #   - viewport_visible: { time_to_first_view_ms, was_above_fold }
    #   - widget_open: { trigger: 'click' | 'auto', time_on_page_ms }
    #   - hover: { duration_ms }

    # Widget settings snapshot for A/B testing analysis
    # Only populated on impression events to track which settings were active
    settings_snapshot = Column(JSON, nullable=True)
    # Examples: { colors: {...}, behavior: {...}, icon: {...}, attention: {...} }

    # Device/browser info
    user_agent = Column(String(500), nullable=True)
    device_type = Column(String(20), nullable=True)  # desktop, mobile, tablet

    # Timestamps
    client_timestamp = Column(DateTime, nullable=True)  # When event occurred on client
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="widget_events")

    # Composite index for efficient analytics queries
    __table_args__ = (
        Index("ix_widget_events_tenant_type_date", "tenant_id", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<WidgetEvent(id={self.id}, tenant_id={self.tenant_id}, event_type={self.event_type})>"
