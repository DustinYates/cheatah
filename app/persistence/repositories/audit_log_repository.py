"""Audit log repository."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.audit_log import AuditAction, AuditLog


class AuditLogRepository:
    """Repository for audit log operations.

    Note: This repository intentionally does NOT extend BaseRepository
    because audit logs should not be tenant-scoped in their access patterns.
    Global admins need to query across tenants for security monitoring.
    """

    def __init__(self, session: AsyncSession):
        """Initialize audit log repository."""
        self.session = session

    async def create(
        self,
        action: str | AuditAction,
        user_id: int | None = None,
        user_email: str | None = None,
        tenant_id: int | None = None,
        tenant_name: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Create a new audit log entry.

        Args:
            action: The action being logged (AuditAction enum or string)
            user_id: ID of user performing the action
            user_email: Email of user (denormalized for historical record)
            tenant_id: ID of tenant affected
            tenant_name: Name of tenant (denormalized for historical record)
            resource_type: Type of resource affected (e.g., "contact", "lead")
            resource_id: ID of the specific resource
            details: Additional action-specific details as JSON
            ip_address: Client IP address
            user_agent: Client user agent string

        Returns:
            The created AuditLog entry
        """
        action_str = action.value if isinstance(action, AuditAction) else action

        audit_log = AuditLog(
            action=action_str,
            user_id=user_id,
            user_email=user_email,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.session.add(audit_log)
        await self.session.commit()
        await self.session.refresh(audit_log)
        return audit_log

    async def list_by_tenant(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        action: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[AuditLog]:
        """List audit logs for a specific tenant.

        Args:
            tenant_id: The tenant to filter by
            skip: Pagination offset
            limit: Maximum records to return
            action: Filter by specific action type
            start_date: Filter logs after this date
            end_date: Filter logs before this date

        Returns:
            List of audit log entries
        """
        stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

        if action:
            stmt = stmt.where(AuditLog.action == action)
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)

        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        """List audit logs for a specific user (global admin use)."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        action: str | None = None,
    ) -> list[AuditLog]:
        """List all audit logs (global admin only)."""
        stmt = select(AuditLog)

        if action:
            stmt = stmt.where(AuditLog.action == action)

        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
