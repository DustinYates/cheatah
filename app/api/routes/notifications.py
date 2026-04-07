"""Notification API routes for in-app notifications."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_tenant_admin
from app.infrastructure.notifications import NotificationService
from app.persistence.models.tenant import User

router = APIRouter()


class NotificationItem(BaseModel):
    """Response model for a single notification."""

    id: int
    notification_type: str
    title: str
    message: str
    extra_data: dict | None = None
    action_url: str | None = None
    priority: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response with notifications and unread count."""

    notifications: list[NotificationItem]
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Lightweight response for polling unread count."""

    count: int


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
    include_read: bool = Query(True),
    since: datetime | None = Query(None),
) -> NotificationListResponse:
    """List recent notifications for the current user."""
    user, tenant_id = auth
    service = NotificationService(db)

    notifications = await service.get_notifications(
        tenant_id=tenant_id,
        user_id=user.id,
        limit=limit,
        include_read=include_read,
        since=since,
    )
    unread_count = await service.get_unread_count(
        tenant_id=tenant_id,
        user_id=user.id,
    )

    return NotificationListResponse(
        notifications=[NotificationItem.model_validate(n) for n in notifications],
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UnreadCountResponse:
    """Get unread notification count (lightweight poll endpoint)."""
    user, tenant_id = auth
    service = NotificationService(db)
    count = await service.get_unread_count(tenant_id=tenant_id, user_id=user.id)
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark a single notification as read."""
    user, tenant_id = auth
    service = NotificationService(db)
    success = await service.mark_notification_read(
        tenant_id=tenant_id,
        user_id=user.id,
        notification_id=notification_id,
    )
    return {"success": success}


@router.post("/read-all")
async def mark_all_notifications_read(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark all notifications as read for the current user."""
    user, tenant_id = auth
    service = NotificationService(db)
    count = await service.mark_all_notifications_read(
        tenant_id=tenant_id,
        user_id=user.id,
    )
    return {"count": count}
