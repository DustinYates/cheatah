"""Config snapshot model for versioning tenant configurations."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.prompt import PromptBundle
    from app.persistence.models.tenant import Tenant, User


class ConfigSnapshot(Base):
    """Config snapshot for versioning widget/prompt configurations."""

    __tablename__ = "config_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    version_id = Column(UUID(as_uuid=True), default=uuid4, nullable=False, unique=True)
    version_number = Column(Integer, nullable=False)

    # Snapshot data
    widget_settings = Column(JSON, nullable=True)
    prompt_bundle_id = Column(Integer, ForeignKey("prompt_bundles.id"), nullable=True)
    prompt_bundle_name = Column(String(255), nullable=True)
    prompt_sections = Column(JSON, nullable=True)
    business_profile = Column(JSON, nullable=True)

    # Metadata
    went_live_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    change_summary = Column(Text, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="config_snapshots")
    prompt_bundle = relationship("PromptBundle")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])

    def __repr__(self) -> str:
        return f"<ConfigSnapshot(id={self.id}, tenant_id={self.tenant_id}, version={self.version_number})>"
