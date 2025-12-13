"""Prompt bundle and section models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class PromptBundle(Base):
    """Prompt bundle model representing a collection of prompt sections."""

    __tablename__ = "prompt_bundles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # NULL for global
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False, default="1.0.0")
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="prompt_bundles")
    sections = relationship(
        "PromptSection", back_populates="bundle", cascade="all, delete-orphan", order_by="PromptSection.order"
    )

    def __repr__(self) -> str:
        return f"<PromptBundle(id={self.id}, tenant_id={self.tenant_id}, name={self.name}, version={self.version}, active={self.is_active})>"


class PromptSection(Base):
    """Prompt section model representing a part of a prompt bundle."""

    __tablename__ = "prompt_sections"

    id = Column(Integer, primary_key=True, index=True)
    bundle_id = Column(Integer, ForeignKey("prompt_bundles.id"), nullable=False, index=True)
    section_key = Column(String(100), nullable=False)  # system, base, instructions, etc.
    content = Column(Text, nullable=False)
    order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    bundle = relationship("PromptBundle", back_populates="sections")

    def __repr__(self) -> str:
        return f"<PromptSection(id={self.id}, bundle_id={self.bundle_id}, section_key={self.section_key}, order={self.order})>"

