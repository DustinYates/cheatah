"""Audit logs API routes."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_global_admin, require_tenant_admin
from app.persistence.models.tenant import User
from app.persistence.repositories.audit_log_repository import AuditLogRepository

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Response model for audit log entry."""

    id: int
    user_id: int | None
    user_email: str | None
    tenant_id: int | None
    tenant_name: str | None
    action: str
    resource_type: str | None
    resource_id: int | None
    details: dict | None
    ip_address: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Response model for list of audit logs."""

    logs: list[AuditLogResponse]
    total: int


@router.get("/", response_model=AuditLogListResponse)
async def list_audit_logs_for_tenant(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> AuditLogListResponse:
    """List audit logs for the current tenant.

    Tenant admins can view their tenant's audit logs.
    Global admins viewing via impersonation also use this endpoint.
    """
    user, tenant_id = auth
    repo = AuditLogRepository(db)

    logs = await repo.list_by_tenant(
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )

    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.get("/all", response_model=AuditLogListResponse)
async def list_all_audit_logs(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = None,
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> AuditLogListResponse:
    """List all audit logs across all tenants.

    Global admin only. Can filter by tenant, user, or action.
    """
    repo = AuditLogRepository(db)

    if tenant_id:
        logs = await repo.list_by_tenant(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            action=action,
        )
    elif user_id:
        logs = await repo.list_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )
    else:
        logs = await repo.list_all(
            skip=skip,
            limit=limit,
            action=action,
        )

    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )
