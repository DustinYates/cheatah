"""SMS template model — tenant-wide reusable mass-text snippets."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.persistence.database import Base


class SmsTemplate(Base):
    __tablename__ = "sms_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sms_template_tenant_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    body = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")

    def __repr__(self) -> str:
        return f"<SmsTemplate(id={self.id}, tenant_id={self.tenant_id}, name={self.name!r})>"
