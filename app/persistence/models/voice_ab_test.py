"""Voice A/B test models for comparing voice agent variants."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant


class VoiceABTest(Base):
    """A named A/B test grouping voice agent variants."""

    __tablename__ = "voice_ab_tests"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="active")  # active, paused, completed
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    variants = relationship("VoiceABTestVariant", back_populates="test", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<VoiceABTest(id={self.id}, name={self.name}, status={self.status})>"


class VoiceABTestVariant(Base):
    """A single variant (voice model) within an A/B test."""

    __tablename__ = "voice_ab_test_variants"
    __table_args__ = (
        UniqueConstraint("test_id", "voice_model", name="uq_voice_ab_test_variant_model"),
        UniqueConstraint("test_id", "assistant_id", name="uq_voice_ab_test_variant_assistant"),
    )

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("voice_ab_tests.id", ondelete="CASCADE"), nullable=False, index=True)
    voice_model = Column(String(255), nullable=False)  # Legacy field, kept for compatibility
    assistant_id = Column(String(255), nullable=True, index=True)  # Telnyx AI Agent ID - primary matching key
    label = Column(String(100), nullable=False)  # Display name (e.g., "Jessica", "DBOT")
    is_control = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    test = relationship("VoiceABTest", back_populates="variants")

    def __repr__(self) -> str:
        return f"<VoiceABTestVariant(id={self.id}, label={self.label}, voice_model={self.voice_model})>"
