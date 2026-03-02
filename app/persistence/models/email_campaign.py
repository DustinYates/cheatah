"""Email campaign models for automated cold outreach with AI-generated content."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.tenant import Tenant


class EmailCampaign(Base):
    """Per-tenant email outreach campaign definition."""

    __tablename__ = "email_campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_email_campaign_tenant_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    status = Column(String(30), default="draft", nullable=False, index=True)  # draft/scheduled/sending/paused/completed
    subject_template = Column(String(500), nullable=False)
    email_prompt_instructions = Column(Text, nullable=True)  # Campaign-specific LLM instructions
    from_email = Column(String(255), nullable=True)  # Override tenant SendGrid default
    reply_to = Column(String(255), nullable=True)
    unsubscribe_url = Column(String(500), nullable=False)
    physical_address = Column(String(500), nullable=False)
    send_at = Column(DateTime, nullable=True)  # Scheduled send time (UTC)
    batch_size = Column(Integer, default=50, nullable=False)
    batch_delay_seconds = Column(Integer, default=300, nullable=False)  # 5 min between batches
    total_recipients = Column(Integer, default=0, nullable=False)
    sent_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    recipients = relationship("EmailCampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<EmailCampaign(id={self.id}, name={self.name}, status={self.status})>"


class EmailCampaignRecipient(Base):
    """Individual recipient within an email campaign."""

    __tablename__ = "email_campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_email_recipient_campaign_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    role = Column(String(255), nullable=True)
    personalization_data = Column(JSON, nullable=True)  # Extra context for LLM
    status = Column(String(30), default="pending", nullable=False, index=True)  # pending/generating/sent/failed/skipped
    generated_subject = Column(String(500), nullable=True)
    generated_body = Column(Text, nullable=True)  # Stored for audit
    sendgrid_message_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    campaign = relationship("EmailCampaign", back_populates="recipients")
    tenant = relationship("Tenant")
    contact = relationship("Contact")

    def __repr__(self) -> str:
        return f"<EmailCampaignRecipient(id={self.id}, email={self.email}, status={self.status})>"
