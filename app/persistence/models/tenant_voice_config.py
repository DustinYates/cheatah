"""Tenant voice configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantVoiceConfig(Base):
    """Tenant voice configuration for call handling and handoff."""

    __tablename__ = "tenant_voice_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    
    # Enable/disable voice
    is_enabled = Column(Boolean, default=False, nullable=False)
    
    # Handoff configuration
    # Modes: "live_transfer", "take_message", "schedule_callback", "voicemail"
    handoff_mode = Column(String(50), default="take_message", nullable=False)
    live_transfer_number = Column(String(50), nullable=True)  # Phone number for live transfers
    telnyx_agent_id = Column(String(255), nullable=True)  # Telnyx AI agent/assistant ID
    
    # Escalation rules (JSON)
    # Schema: {
    #   "caller_asks_human": true,
    #   "repeated_confusion": {"enabled": true, "threshold": 3},
    #   "high_value_intent": {"enabled": true, "intents": ["booking_request"]},
    #   "low_confidence": {"enabled": true, "threshold": 0.5}
    # }
    escalation_rules = Column(JSON, nullable=True, default=lambda: {
        "caller_asks_human": True,
        "repeated_confusion": {"enabled": True, "threshold": 3},
        "high_value_intent": {"enabled": False, "intents": []},
        "low_confidence": {"enabled": False, "threshold": 0.5},
    })
    
    # Greeting and disclosure
    default_greeting = Column(Text, nullable=True, default=(
        "Hello! Thank you for calling. I'm an AI assistant and I'm here to help you. "
        "How can I assist you today?"
    ))
    disclosure_line = Column(Text, nullable=True, default=(
        "This call may be recorded for quality and training purposes."
    ))
    
    # Notification preferences (JSON)
    # Schema: ["email", "sms", "in_app"]
    notification_methods = Column(JSON, nullable=True, default=lambda: ["email", "in_app"])
    
    # Notification recipients (JSON)
    # Schema: [{"type": "user_id", "value": 1}, {"type": "email", "value": "admin@example.com"}]
    notification_recipients = Column(JSON, nullable=True)
    
    # Auto-reply when outside business hours
    after_hours_message = Column(Text, nullable=True, default=(
        "Thank you for calling. We're currently outside our business hours. "
        "Please leave a message after the tone, and we'll get back to you as soon as possible."
    ))

    # Fallback voice prompt - used if dynamic prompt fails
    fallback_voice_prompt = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="voice_config")

    def __repr__(self) -> str:
        return f"<TenantVoiceConfig(id={self.id}, tenant_id={self.tenant_id}, handoff_mode={self.handoff_mode})>"


# Default escalation rules for new tenants
DEFAULT_ESCALATION_RULES = {
    "caller_asks_human": True,
    "repeated_confusion": {"enabled": True, "threshold": 3},
    "high_value_intent": {"enabled": False, "intents": []},
    "low_confidence": {"enabled": False, "threshold": 0.5},
}

# Default notification methods
DEFAULT_NOTIFICATION_METHODS = ["email", "in_app"]

