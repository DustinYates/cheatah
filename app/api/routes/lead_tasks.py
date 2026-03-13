"""Lead tasks API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.lead import Lead
from app.persistence.models.lead_task import LeadTask
from app.persistence.models.tenant import User

router = APIRouter()


# --- Schemas ---

class TaskCreate(BaseModel):
    title: str
    due_date: str | None = None  # ISO 8601 string


class TaskUpdate(BaseModel):
    title: str | None = None
    due_date: str | None = None
    is_completed: bool | None = None


class TaskResponse(BaseModel):
    id: int
    lead_id: int
    title: str
    due_date: str | None
    is_completed: bool
    completed_at: str | None
    created_at: str
    updated_at: str
    lead_name: str | None = None

    class Config:
        from_attributes = True


def _isoformat_utc(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _task_to_response(task: LeadTask, lead_name: str | None = None) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        lead_id=task.lead_id,
        title=task.title,
        due_date=_isoformat_utc(task.due_date),
        is_completed=task.is_completed,
        completed_at=_isoformat_utc(task.completed_at),
        created_at=_isoformat_utc(task.created_at),
        updated_at=_isoformat_utc(task.updated_at),
        lead_name=lead_name,
    )


def _parse_due_date(due_date_str: str | None) -> datetime | None:
    if not due_date_str:
        return None
    try:
        return datetime.fromisoformat(due_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid due_date format. Use ISO 8601.")


# --- Per-lead endpoints ---

@router.get("/leads/{lead_id}/tasks", response_model=list[TaskResponse])
async def list_lead_tasks(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[TaskResponse]:
    """List all tasks for a lead."""
    result = await db.execute(
        select(LeadTask)
        .where(LeadTask.lead_id == lead_id, LeadTask.tenant_id == tenant_id)
        .order_by(LeadTask.is_completed, LeadTask.due_date.asc().nulls_last(), LeadTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return [_task_to_response(t) for t in tasks]


@router.post("/leads/{lead_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_lead_task(
    lead_id: int,
    body: TaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TaskResponse:
    """Create a task for a lead."""
    # Verify lead exists and belongs to tenant
    lead = await db.get(Lead, lead_id)
    if not lead or lead.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")

    task = LeadTask(
        tenant_id=tenant_id,
        lead_id=lead_id,
        title=body.title.strip(),
        due_date=_parse_due_date(body.due_date),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.patch("/leads/{lead_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_lead_task(
    lead_id: int,
    task_id: int,
    body: TaskUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TaskResponse:
    """Update a task."""
    task = await db.get(LeadTask, task_id)
    if not task or task.lead_id != lead_id or task.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title.strip()
    if body.due_date is not None:
        task.due_date = _parse_due_date(body.due_date) if body.due_date else None
    if body.is_completed is not None:
        task.is_completed = body.is_completed
        task.completed_at = datetime.utcnow() if body.is_completed else None

    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.delete("/leads/{lead_id}/tasks/{task_id}", status_code=204)
async def delete_lead_task(
    lead_id: int,
    task_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
):
    """Delete a task."""
    task = await db.get(LeadTask, task_id)
    if not task or task.lead_id != lead_id or task.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()


# --- Cross-lead endpoints (for dashboard calendar) ---

@router.get("/tasks/upcoming", response_model=list[TaskResponse])
async def get_upcoming_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[TaskResponse]:
    """Get all incomplete tasks with due dates in the next N days (plus overdue)."""
    cutoff = datetime.utcnow() + timedelta(days=days)
    result = await db.execute(
        select(LeadTask, Lead.name.label("lead_name"))
        .join(Lead, LeadTask.lead_id == Lead.id)
        .where(
            LeadTask.tenant_id == tenant_id,
            LeadTask.is_completed == False,
            LeadTask.due_date.isnot(None),
            LeadTask.due_date <= cutoff,
        )
        .order_by(LeadTask.due_date.asc())
    )
    rows = result.all()
    return [_task_to_response(row.LeadTask, lead_name=row.lead_name) for row in rows]
