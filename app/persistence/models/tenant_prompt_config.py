"""Tenant prompt configuration model for JSON-based prompt system."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.persistence.database import Base


class TenantPromptConfig(Base):
    """Stores tenant-specific prompt configuration as JSON.

    This model supports the new JSON-based prompt architecture where:
    - Base rules are hardcoded in Python (app/domain/prompts/base_configs/)
    - Tenant-specific data (locations, levels, tuition, etc.) is stored as JSON
    - The assembler combines base + tenant at runtime
    """

    __tablename__ = "tenant_prompt_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    schema_version = Column(String(50), nullable=False, default="bss_chatbot_prompt_v1")
    business_type = Column(String(50), nullable=False, default="bss")
    config_json = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="prompt_config")

    def __repr__(self) -> str:
        return f"<TenantPromptConfig(id={self.id}, tenant_id={self.tenant_id}, schema={self.schema_version})>"
