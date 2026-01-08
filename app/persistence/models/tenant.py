"""Tenant and User models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.lead import Lead
    from app.persistence.models.notification import Notification
    from app.persistence.models.prompt import PromptBundle
    from app.persistence.models.tenant_email_config import TenantEmailConfig
    from app.persistence.models.tenant_voice_config import TenantVoiceConfig


class Tenant(Base):
    """Tenant model representing a business/organization."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    tenant_number = Column(String(50), unique=True, nullable=True, index=True)  # Admin-assignable ID
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_date = Column(Date, nullable=True)
    tier = Column(String(50), nullable=True)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship(
        "Conversation", back_populates="tenant", cascade="all, delete-orphan"
    )
    leads = relationship("Lead", back_populates="tenant", cascade="all, delete-orphan")
    prompt_bundles = relationship(
        "PromptBundle", back_populates="tenant", cascade="all, delete-orphan"
    )
    sms_config = relationship(
        "TenantSmsConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    sms_opt_ins = relationship(
        "SmsOptIn", back_populates="tenant", cascade="all, delete-orphan"
    )
    escalations = relationship(
        "Escalation", back_populates="tenant", cascade="all, delete-orphan"
    )
    business_profile = relationship(
        "TenantBusinessProfile", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    contacts = relationship(
        "Contact", back_populates="tenant", cascade="all, delete-orphan"
    )
    calls = relationship(
        "Call", back_populates="tenant", cascade="all, delete-orphan"
    )
    voice_config = relationship(
        "TenantVoiceConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="tenant", cascade="all, delete-orphan"
    )
    email_config = relationship(
        "TenantEmailConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    widget_config = relationship(
        "TenantWidgetConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    customer_service_config = relationship(
        "TenantCustomerServiceConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, subdomain={self.subdomain})>"


class TenantBusinessProfile(Base):
    """Business profile for a tenant - contact and business info for chat/SMS."""

    __tablename__ = "tenant_business_profiles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)
    
    business_name = Column(String(255), nullable=True)
    website_url = Column(Text, nullable=True)
    phone_number = Column(String(50), nullable=True)
    twilio_phone = Column(String(50), nullable=True)
    twilio_voice_phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    
    profile_complete = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Scraped website data
    scraped_services = Column(JSON, nullable=True)  # List of services/programs offered
    scraped_hours = Column(JSON, nullable=True)  # Business hours by location
    scraped_locations = Column(JSON, nullable=True)  # Address, phone per location
    scraped_pricing = Column(JSON, nullable=True)  # Pricing information
    scraped_faqs = Column(JSON, nullable=True)  # FAQ question/answer pairs
    scraped_policies = Column(JSON, nullable=True)  # Cancellation, refund, booking policies
    scraped_programs = Column(JSON, nullable=True)  # Class levels, curriculum details
    scraped_unique_selling_points = Column(JSON, nullable=True)  # Key differentiators
    scraped_target_audience = Column(Text, nullable=True)  # Age groups, skill levels
    scraped_raw_content = Column(Text, nullable=True)  # Raw scraped text for reference
    last_scraped_at = Column(DateTime, nullable=True)  # When scraping last occurred

    # Relationships
    tenant = relationship("Tenant", back_populates="business_profile")

    def __repr__(self) -> str:
        return f"<TenantBusinessProfile(id={self.id}, tenant_id={self.tenant_id}, business_name={self.business_name})>"


class User(Base):
    """User model representing system users."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user")  # admin, tenant_admin, user
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    contact = relationship("Contact", foreign_keys=[contact_id])
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, tenant_id={self.tenant_id}, role={self.role})>"
