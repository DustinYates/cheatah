"""Audit logging service for tracking tenant access and sensitive operations."""

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.audit_log import AuditAction
from app.persistence.models.tenant import Tenant, User
from app.persistence.repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger(__name__)


class AuditService:
    """Service for creating audit log entries.

    Usage:
        audit = AuditService(db)
        await audit.log_login(user, request)
        await audit.log_tenant_action(AuditAction.TENANT_CREATED, user, tenant, request)
    """

    def __init__(self, session: AsyncSession):
        """Initialize audit service."""
        self.repo = AuditLogRepository(session)

    def _extract_client_info(self, request: Request | None) -> tuple[str | None, str | None]:
        """Extract IP address and user agent from request."""
        if request is None:
            return None, None

        # Get IP from X-Forwarded-For header (for proxied requests) or client host
        ip_address = request.headers.get("X-Forwarded-For")
        if ip_address:
            # Take the first IP in the chain (original client)
            ip_address = ip_address.split(",")[0].strip()
        else:
            ip_address = request.client.host if request.client else None

        user_agent = request.headers.get("User-Agent")

        return ip_address, user_agent

    async def log(
        self,
        action: AuditAction | str,
        user: User | None = None,
        tenant: Tenant | None = None,
        tenant_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        details: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> None:
        """Create an audit log entry.

        Args:
            action: The action being logged
            user: The user performing the action (optional)
            tenant: The tenant being affected (optional)
            tenant_id: Tenant ID if tenant object not available
            resource_type: Type of resource affected
            resource_id: ID of the specific resource
            details: Additional action-specific details
            request: FastAPI request for extracting IP/user agent
        """
        ip_address, user_agent = self._extract_client_info(request)

        # Resolve tenant_id from tenant object or parameter
        effective_tenant_id = tenant.id if tenant else tenant_id
        tenant_name = tenant.name if tenant else None

        try:
            await self.repo.create(
                action=action,
                user_id=user.id if user else None,
                user_email=user.email if user else None,
                tenant_id=effective_tenant_id,
                tenant_name=tenant_name,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as e:
            # Don't let audit logging failures break the application
            logger.error(f"Failed to create audit log: {e}")

    async def log_login(
        self,
        user: User,
        request: Request | None = None,
        success: bool = True,
    ) -> None:
        """Log a login attempt."""
        action = AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED
        await self.log(
            action=action,
            user=user,
            tenant_id=user.tenant_id,
            request=request,
        )

    async def log_impersonation(
        self,
        admin_user: User,
        target_tenant: Tenant,
        request: Request | None = None,
        ending: bool = False,
    ) -> None:
        """Log admin impersonation of a tenant."""
        action = (
            AuditAction.ADMIN_IMPERSONATION_END
            if ending
            else AuditAction.ADMIN_IMPERSONATION_START
        )
        await self.log(
            action=action,
            user=admin_user,
            tenant=target_tenant,
            details={"admin_email": admin_user.email, "target_tenant": target_tenant.name},
            request=request,
        )

    async def log_tenant_change(
        self,
        action: AuditAction,
        user: User,
        tenant: Tenant,
        request: Request | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log tenant-related changes."""
        await self.log(
            action=action,
            user=user,
            tenant=tenant,
            resource_type="tenant",
            resource_id=tenant.id,
            details=details,
            request=request,
        )

    async def log_data_export(
        self,
        user: User,
        tenant_id: int,
        export_type: str,
        record_count: int,
        request: Request | None = None,
    ) -> None:
        """Log data export operations."""
        await self.log(
            action=AuditAction.DATA_BULK_EXPORT,
            user=user,
            tenant_id=tenant_id,
            details={
                "export_type": export_type,
                "record_count": record_count,
            },
            request=request,
        )

    async def log_config_change(
        self,
        user: User,
        tenant_id: int,
        config_type: str,
        changes: dict[str, Any],
        request: Request | None = None,
    ) -> None:
        """Log configuration changes."""
        await self.log(
            action=AuditAction.CONFIG_UPDATED,
            user=user,
            tenant_id=tenant_id,
            resource_type=config_type,
            details={"changes": changes},
            request=request,
        )
