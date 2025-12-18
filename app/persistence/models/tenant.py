"""Tenant and User models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.conversation import Conversation
    from app.persistence.models.lead import Lead
    from app.persistence.models.prompt import PromptBundle


class Tenant(Base):
    """Tenant model representing a business/organization."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    email = Column(String(255), nullable=True)
    
    profile_complete = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, tenant_id={self.tenant_id}, role={self.role})>"

