"""Drip campaign models for automated SMS follow-up sequences."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.lead import Lead
    from app.persistence.models.tenant import Tenant


class DripCampaign(Base):
    """Per-tenant drip campaign definition. Routed to leads by optional
    audience and tag filters; tenants can define many campaigns per tenant."""

    __tablename__ = "drip_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    campaign_type = Column(String(50), nullable=False)  # legacy label ("kids"/"adults"/"custom")
    audience_filter = Column(String(50), nullable=True)  # null/"any"/"adult"/"child"/"under_3"
    tag_filter = Column(JSONB, nullable=True)  # list of tag values, all must match
    priority = Column(Integer, nullable=False, default=100, server_default="100")
    is_enabled = Column(Boolean, default=False, nullable=False)
    trigger_delay_minutes = Column(Integer, default=10, nullable=False)
    # Allowed sending window in the tenant's local timezone. "HH:MM" 24-hour.
    # Defaults match the prior global quiet-hours rule (8am-9pm). Steps that
    # fire outside this window get deferred to the next window-open.
    send_window_start = Column(String(5), nullable=False, default="08:00", server_default="08:00")
    send_window_end = Column(String(5), nullable=False, default="21:00", server_default="21:00")
    response_templates = Column(JSON, nullable=True)  # Hardcoded response category templates
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    steps = relationship("DripCampaignStep", back_populates="campaign", cascade="all, delete-orphan", order_by="DripCampaignStep.step_number")
    enrollments = relationship("DripEnrollment", back_populates="campaign")

    def __repr__(self) -> str:
        return f"<DripCampaign(id={self.id}, name={self.name}, type={self.campaign_type}, enabled={self.is_enabled})>"


class DripCampaignStep(Base):
    """Ordered step within a drip campaign (sent when lead doesn't respond)."""

    __tablename__ = "drip_campaign_steps"
    __table_args__ = (
        UniqueConstraint("campaign_id", "step_number", name="uq_drip_step_campaign_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("drip_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    delay_minutes = Column(Integer, nullable=False)  # Delay after previous step (step 1 uses campaign.trigger_delay_minutes)
    message_template = Column(Text, nullable=False)
    check_availability = Column(Boolean, default=False, nullable=False)
    fallback_template = Column(Text, nullable=True)  # Used if availability check fails
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    campaign = relationship("DripCampaign", back_populates="steps")

    def __repr__(self) -> str:
        return f"<DripCampaignStep(id={self.id}, campaign_id={self.campaign_id}, step={self.step_number})>"


class DripEnrollment(Base):
    """Tracks a lead's progress through a drip campaign."""

    __tablename__ = "drip_enrollments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "campaign_id", "lead_id", name="uq_drip_enrollment_tenant_campaign_lead"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("drip_campaigns.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    status = Column(String(30), default="active", nullable=False, index=True)  # active/responded/completed/cancelled
    current_step = Column(Integer, default=0, nullable=False)  # 0 = not started
    next_task_id = Column(String(500), nullable=True)  # Cloud Task name
    next_step_at = Column(DateTime, nullable=True)
    context_data = Column(JSON, nullable=True)  # Template variables from email body
    response_category = Column(String(50), nullable=True)  # price/spouse/schedule/sibling/yes/other
    cancelled_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    campaign = relationship("DripCampaign", back_populates="enrollments")
    lead = relationship("Lead")

    def __repr__(self) -> str:
        return f"<DripEnrollment(id={self.id}, lead_id={self.lead_id}, status={self.status}, step={self.current_step})>"
