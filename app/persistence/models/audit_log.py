"""Audit log model for tracking tenant access and sensitive operations."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base


class AuditAction(str, Enum):
    """Types of auditable actions."""

    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"

    # Tenant operations
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DELETED = "tenant_deleted"
    TENANT_ACTIVATED = "tenant_activated"
    TENANT_DEACTIVATED = "tenant_deactivated"

    # Data access (sensitive)
    CONTACT_EXPORTED = "contact_exported"
    LEAD_EXPORTED = "lead_exported"
    DATA_BULK_EXPORT = "data_bulk_export"

    # Admin operations
    ADMIN_IMPERSONATION_START = "admin_impersonation_start"
    ADMIN_IMPERSONATION_END = "admin_impersonation_end"
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"

    # Configuration changes
    CONFIG_UPDATED = "config_updated"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"


class AuditLog(Base):
    """Audit log for tracking tenant access and sensitive operations.

    Records who did what, when, from where, and to which tenant's data.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Who performed the action
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)  # Denormalized for historical records

    # Which tenant was affected
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    tenant_name = Column(String(255), nullable=True)  # Denormalized for historical records

    # What action was performed
    action = Column(String(100), nullable=False, index=True)

    # What resource was affected
    resource_type = Column(String(100), nullable=True)  # e.g., "contact", "lead", "tenant"
    resource_id = Column(Integer, nullable=True)

    # Additional context
    details = Column(JSON, nullable=True)  # Action-specific details
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)

    # When
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships (optional, for lookups)
    user = relationship("User", foreign_keys=[user_id])
    tenant = relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action={self.action}, "
            f"user_id={self.user_id}, tenant_id={self.tenant_id})>"
        )
