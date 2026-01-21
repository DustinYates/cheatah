"""Tenant email configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class TenantEmailConfig(Base):
    """Tenant email configuration for Gmail-based email responder."""

    __tablename__ = "tenant_email_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True)
    
    # Enable/disable email responder
    is_enabled = Column(Boolean, default=False, nullable=False)
    
    # Gmail OAuth credentials
    gmail_email = Column(String(255), nullable=True)  # Connected Gmail address
    gmail_refresh_token = Column(Text, nullable=True)  # Encrypted refresh token
    gmail_access_token = Column(Text, nullable=True)  # Current access token (short-lived)
    gmail_token_expires_at = Column(DateTime, nullable=True)  # Access token expiry
    
    # Gmail API watch/sync
    last_history_id = Column(String(100), nullable=True)  # For Gmail API incremental sync
    watch_expiration = Column(DateTime, nullable=True)  # When the Gmail watch expires
    
    # Business hours settings
    business_hours_enabled = Column(Boolean, default=False, nullable=False)
    auto_reply_outside_hours = Column(Boolean, default=True, nullable=False)
    auto_reply_message = Column(Text, nullable=True, default=(
        "Thank you for your email. We're currently outside our business hours. "
        "We'll respond as soon as possible during our next business day."
    ))
    
    # Response settings
    response_signature = Column(Text, nullable=True)  # Email signature to append
    max_thread_depth = Column(Integer, default=10)  # Max emails in thread to consider for context
    
    # Notification preferences (JSON)
    # Schema: ["email", "sms", "in_app"]
    notification_methods = Column(JSON, nullable=True, default=lambda: ["in_app"])
    
    # Escalation settings (JSON)
    # Schema: {
    #   "keywords": ["urgent", "complaint"],
    #   "auto_escalate_no_response": {"enabled": true, "hours": 4}
    # }
    escalation_rules = Column(JSON, nullable=True, default=lambda: {
        "keywords": ["urgent", "complaint", "lawyer", "legal"],
        "auto_escalate_no_response": {"enabled": False, "hours": 4},
    })
    
    # Lead capture settings (JSON)
    # List of email subject prefixes that should trigger lead creation
    # If null/empty, uses default prefixes. If explicitly [], no leads are created.
    lead_capture_subject_prefixes = Column(JSON, nullable=True, default=lambda: [
        "Email Capture from Booking Page",
        "Get In Touch Form Submission",
    ])

    # SendGrid Inbound Parse Configuration
    # Alternative to Gmail API - uses email forwarding instead of OAuth
    sendgrid_enabled = Column(Boolean, default=False, nullable=False)
    sendgrid_parse_address = Column(String(255), nullable=True, unique=True, index=True)
    sendgrid_webhook_secret = Column(String(255), nullable=True)  # Shared secret for webhook verification
    email_ingestion_method = Column(String(20), default="gmail", nullable=False)  # 'gmail' or 'sendgrid'

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="email_config")

    def __repr__(self) -> str:
        return f"<TenantEmailConfig(id={self.id}, tenant_id={self.tenant_id}, gmail_email={self.gmail_email})>"


class EmailConversation(Base):
    """Email conversation tracking - links Gmail threads to internal conversations."""

    __tablename__ = "email_conversations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    
    # Gmail identifiers
    gmail_thread_id = Column(String(255), nullable=False, index=True)
    gmail_message_id = Column(String(255), nullable=True)  # Latest message ID
    
    # Email metadata
    subject = Column(String(500), nullable=True)
    from_email = Column(String(255), nullable=False, index=True)
    to_email = Column(String(255), nullable=False)
    
    # Status tracking
    status = Column(String(50), default="active", nullable=False)  # active, escalated, resolved, spam
    last_response_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=1, nullable=False)
    
    # Lead/contact linkage
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    conversation = relationship("Conversation")
    contact = relationship("Contact")
    lead = relationship("Lead")

    def __repr__(self) -> str:
        return f"<EmailConversation(id={self.id}, thread_id={self.gmail_thread_id}, from={self.from_email})>"


# Default escalation rules for new tenants
DEFAULT_EMAIL_ESCALATION_RULES = {
    "keywords": ["urgent", "complaint", "lawyer", "legal"],
    "auto_escalate_no_response": {"enabled": False, "hours": 4},
}

# Default notification methods
DEFAULT_EMAIL_NOTIFICATION_METHODS = ["in_app"]

# Default lead capture subject prefixes
DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES = [
    "Email Capture from Booking Page",
    "Get In Touch Form Submission",
]

