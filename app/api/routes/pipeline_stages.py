"""Pipeline stages API endpoints — per-tenant customizable Kanban stages."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import User
from app.persistence.models.tenant_pipeline_stage import TenantPipelineStage

router = APIRouter()

DEFAULT_PIPELINE_STAGES = [
    {"key": "new_lead", "label": "New Lead", "color": "#1d4ed8", "position": 0},
    {"key": "contacted", "label": "Contacted", "color": "#b45309", "position": 1},
    {"key": "interested", "label": "Interested", "color": "#be185d", "position": 2},
    {"key": "registered", "label": "Registered", "color": "#047857", "position": 3},
    {"key": "enrolled", "label": "Enrolled", "color": "#4338ca", "position": 4},
]

KEY_PATTERN = re.compile(r"^[a-z0-9_]+$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


# --- Pydantic models ---

class PipelineStageItem(BaseModel):
    key: str
    label: str
    color: str


class PipelineStageResponse(BaseModel):
    key: str
    label: str
    color: str
    position: int


class PipelineStagesResponse(BaseModel):
    stages: list[PipelineStageResponse]


class BulkUpdateRequest(BaseModel):
    stages: list[PipelineStageItem]
    orphan_action: str = "move_to_first"


# --- Helpers ---

async def _get_stages(db: AsyncSession, tenant_id: int) -> list[TenantPipelineStage]:
    result = await db.execute(
        select(TenantPipelineStage)
        .where(TenantPipelineStage.tenant_id == tenant_id)
        .order_by(TenantPipelineStage.position)
    )
    return list(result.scalars().all())


async def _seed_defaults(db: AsyncSession, tenant_id: int) -> list[TenantPipelineStage]:
    stages = []
    for s in DEFAULT_PIPELINE_STAGES:
        stage = TenantPipelineStage(tenant_id=tenant_id, **s)
        db.add(stage)
        stages.append(stage)
    await db.flush()
    return stages


def _to_response(stages: list[TenantPipelineStage]) -> PipelineStagesResponse:
    return PipelineStagesResponse(
        stages=[
            PipelineStageResponse(
                key=s.key, label=s.label, color=s.color, position=s.position
            )
            for s in stages
        ]
    )


# --- Endpoints ---

@router.get("", response_model=PipelineStagesResponse)
async def get_pipeline_stages(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PipelineStagesResponse:
    """Get pipeline stages for the current tenant."""
    stages = await _get_stages(db, tenant_id)
    if not stages:
        stages = await _seed_defaults(db, tenant_id)
        await db.commit()
    return _to_response(stages)


@router.put("", response_model=PipelineStagesResponse)
async def update_pipeline_stages(
    request_data: BulkUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PipelineStagesResponse:
    """Bulk replace all pipeline stages for the current tenant."""
    incoming = request_data.stages
    orphan_action = request_data.orphan_action

    # --- Validation ---
    if not incoming:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one stage is required.")
    if len(incoming) > 20:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maximum 20 stages allowed.")

    seen_keys: set[str] = set()
    for s in incoming:
        s.key = s.key.strip().lower()
        s.label = s.label.strip()
        s.color = s.color.strip()

        if not s.key or len(s.key) > 50:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Stage key must be 1-50 characters: '{s.key}'")
        if not KEY_PATTERN.match(s.key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Stage key must be lowercase alphanumeric/underscore: '{s.key}'")
        if not s.label or len(s.label) > 100:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Stage label must be 1-100 characters: '{s.label}'")
        if not COLOR_PATTERN.match(s.color):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid hex color: '{s.color}'")
        if s.key in seen_keys:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Duplicate stage key: '{s.key}'")
        seen_keys.add(s.key)

    # --- Detect removed stages and handle orphaned leads ---
    existing = await _get_stages(db, tenant_id)
    existing_keys = {s.key for s in existing}
    new_keys = {s.key for s in incoming}
    removed_keys = existing_keys - new_keys

    if removed_keys and orphan_action == "move_to_first":
        first_key = incoming[0].key
        for rk in removed_keys:
            await db.execute(
                update(Lead)
                .where(Lead.tenant_id == tenant_id, Lead.pipeline_stage == rk)
                .values(pipeline_stage=first_key)
            )

    # --- Delete all existing, insert new (atomic within transaction) ---
    await db.execute(
        delete(TenantPipelineStage).where(TenantPipelineStage.tenant_id == tenant_id)
    )

    new_stages = []
    for idx, s in enumerate(incoming):
        stage = TenantPipelineStage(
            tenant_id=tenant_id,
            key=s.key,
            label=s.label,
            color=s.color,
            position=idx,
        )
        db.add(stage)
        new_stages.append(stage)

    await db.commit()

    # Re-fetch to get DB-assigned ids/timestamps
    stages = await _get_stages(db, tenant_id)
    return _to_response(stages)
