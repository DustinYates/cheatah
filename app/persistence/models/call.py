"""Call model for voice calls."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.tenant import Tenant


class Call(Base):
    """Call model representing voice calls."""

    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    call_sid = Column(String(255), unique=True, nullable=False, index=True)
    from_number = Column(String(255), nullable=False)
    to_number = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="initiated")
    direction = Column(String(20), nullable=False, default="inbound")
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration = Column(Integer, nullable=True)  # Duration in seconds
    recording_sid = Column(String(255), nullable=True)
    recording_url = Column(Text, nullable=True)
    
    # Language tracking (detected from phone number routing)
    language = Column(String(20), nullable=True)  # 'english', 'spanish', or None if unknown

    # Voice agent variant tracking (for A/B testing)
    assistant_id = Column(String(255), nullable=True, index=True)  # Telnyx AI assistant ID
    voice_model = Column(String(255), nullable=True, index=True)  # Voice model used (e.g., "ElevenLabsJessica")

    # Handoff tracking (Phase 2)
    handoff_attempted = Column(Boolean, default=False, nullable=False)
    handoff_number = Column(String(50), nullable=True)  # Number transferred to
    handoff_reason = Column(String(100), nullable=True)  # Reason for handoff
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="calls")
    summary = relationship("CallSummary", back_populates="call", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Call(id={self.id}, tenant_id={self.tenant_id}, call_sid={self.call_sid}, status={self.status})>"

