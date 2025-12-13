"""Tenant and User models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
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

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, subdomain={self.subdomain})>"


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

