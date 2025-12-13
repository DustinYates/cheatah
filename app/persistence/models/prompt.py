"""Prompt bundle and section models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Enum
from sqlalchemy.orm import relationship
import enum

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class PromptStatus(str, enum.Enum):
    """Status of a prompt bundle."""
    DRAFT = "draft"
    TESTING = "testing"
    PRODUCTION = "production"


class PromptBundle(Base):
    """Prompt bundle model representing a collection of prompt sections."""

    __tablename__ = "prompt_bundles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # NULL for global/base
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False, default="1.0.0")
    status = Column(String(20), default=PromptStatus.DRAFT.value, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)  # Kept for backward compatibility
    published_at = Column(DateTime, nullable=True)
    source_bundle_id = Column(Integer, ForeignKey("prompt_bundles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="prompt_bundles")
    sections = relationship(
        "PromptSection", back_populates="bundle", cascade="all, delete-orphan", order_by="PromptSection.order"
    )
    source_bundle = relationship("PromptBundle", remote_side=[id], backref="derived_bundles")

    def __repr__(self) -> str:
        return f"<PromptBundle(id={self.id}, tenant_id={self.tenant_id}, name={self.name}, status={self.status})>"


class SectionScope(str, enum.Enum):
    """Scope of a prompt section."""
    SYSTEM = "system"  # Core system instructions
    BASE = "base"  # Base prompt from platform
    PRICING = "pricing"  # Tenant pricing info
    FAQ = "faq"  # Tenant FAQ
    BUSINESS_INFO = "business_info"  # Tenant business details
    CUSTOM = "custom"  # Any custom tenant content


class PromptSection(Base):
    """Prompt section model representing a part of a prompt bundle."""

    __tablename__ = "prompt_sections"

    id = Column(Integer, primary_key=True, index=True)
    bundle_id = Column(Integer, ForeignKey("prompt_bundles.id"), nullable=False, index=True)
    section_key = Column(String(100), nullable=False)  # system, base, pricing, faq, etc.
    scope = Column(String(50), default=SectionScope.CUSTOM.value, nullable=False)
    content = Column(Text, nullable=False)
    order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    bundle = relationship("PromptBundle", back_populates="sections")

    def __repr__(self) -> str:
        return f"<PromptSection(id={self.id}, bundle_id={self.bundle_id}, section_key={self.section_key}, scope={self.scope})>"

