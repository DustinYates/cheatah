"""Drip campaign management API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_context
from app.domain.services.drip_campaign_service import DripCampaignService
from app.persistence.database import get_db
from app.persistence.repositories.drip_campaign_repository import (
    DripCampaignRepository,
    DripEnrollmentRepository,
)
from app.persistence.repositories.lead_repository import LeadRepository

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Schemas ─────────────────────────────────────────────

class DripStepRequest(BaseModel):
    step_number: int
    delay_minutes: int
    message_template: str
    check_availability: bool = False
    fallback_template: str | None = None


class DripStepResponse(BaseModel):
    id: int
    step_number: int
    delay_minutes: int
    message_template: str
    check_availability: bool
    fallback_template: str | None


def _validate_window(start: str | None, end: str | None) -> None:
    """Validate HH:MM 24h strings and refuse anything outside 07:00-22:00 (anti-spam)."""
    import re
    pat = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
    for label, val in (("send_window_start", start), ("send_window_end", end)):
        if val is None:
            continue
        if not pat.match(val):
            raise HTTPException(status_code=400, detail=f"{label} must be HH:MM 24-hour format")
        h, m = int(val[:2]), int(val[3:])
        mins = h * 60 + m
        if mins < 7 * 60 or mins > 22 * 60:
            raise HTTPException(
                status_code=400,
                detail=f"{label} must be between 07:00 and 22:00 (anti-spam guard)",
            )
    if start and end:
        s_mins = int(start[:2]) * 60 + int(start[3:])
        e_mins = int(end[:2]) * 60 + int(end[3:])
        if e_mins <= s_mins:
            raise HTTPException(
                status_code=400, detail="send_window_end must be after send_window_start"
            )


class DripCampaignCreateRequest(BaseModel):
    name: str
    campaign_type: str = "custom"  # legacy label; "kids"/"adults"/"custom"
    audience_filter: str | None = None  # null/"any"/"adult"/"child"/"under_3"
    tag_filter: list[str] | None = None
    priority: int = 100
    is_enabled: bool = False
    trigger_delay_minutes: int = 10
    send_window_start: str = "08:00"
    send_window_end: str = "21:00"
    response_templates: dict | None = None
    steps: list[DripStepRequest] = []


class DripCampaignUpdateRequest(BaseModel):
    name: str | None = None
    campaign_type: str | None = None
    audience_filter: str | None = None
    tag_filter: list[str] | None = None
    priority: int | None = None
    is_enabled: bool | None = None
    trigger_delay_minutes: int | None = None
    send_window_start: str | None = None
    send_window_end: str | None = None
    response_templates: dict | None = None


class DripCampaignResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    campaign_type: str
    audience_filter: str | None = None
    tag_filter: list[str] | None = None
    priority: int = 100
    is_enabled: bool
    trigger_delay_minutes: int
    send_window_start: str
    send_window_end: str
    response_templates: dict | None
    steps: list[DripStepResponse]


class DripEnrollmentResponse(BaseModel):
    id: int
    tenant_id: int
    campaign_id: int
    lead_id: int
    lead_name: str | None = None
    lead_phone: str | None = None
    campaign_name: str | None = None
    campaign_type: str | None = None
    status: str
    current_step: int
    total_steps: int = 0
    next_step_at: str | None = None
    response_category: str | None = None
    cancelled_reason: str | None = None
    created_at: str
    updated_at: str


# ── Tenant-level drip settings ────────────────────────────────────────────

class DripSettingsResponse(BaseModel):
    drip_affects_pipeline: bool
    auto_enroll_new_leads: bool


class DripSettingsUpdateRequest(BaseModel):
    drip_affects_pipeline: bool | None = None
    auto_enroll_new_leads: bool | None = None


@router.get("/settings")
async def get_drip_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> DripSettingsResponse:
    """Read tenant-level drip behavior flags."""
    from sqlalchemy import select as _select
    from app.persistence.models.tenant import TenantBusinessProfile

    result = await db.execute(
        _select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        # No profile row yet — return safe defaults.
        return DripSettingsResponse(drip_affects_pipeline=True, auto_enroll_new_leads=False)
    return DripSettingsResponse(
        drip_affects_pipeline=bool(profile.drip_affects_pipeline),
        auto_enroll_new_leads=bool(profile.auto_enroll_new_leads),
    )


@router.put("/settings")
async def update_drip_settings(
    body: DripSettingsUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> DripSettingsResponse:
    """Update tenant-level drip behavior flags. Only provided fields are changed."""
    from sqlalchemy import select as _select
    from app.persistence.models.tenant import TenantBusinessProfile

    result = await db.execute(
        _select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Tenant business profile not found")

    if body.drip_affects_pipeline is not None:
        profile.drip_affects_pipeline = body.drip_affects_pipeline
    if body.auto_enroll_new_leads is not None:
        profile.auto_enroll_new_leads = body.auto_enroll_new_leads
    await db.commit()
    await db.refresh(profile)
    return DripSettingsResponse(
        drip_affects_pipeline=bool(profile.drip_affects_pipeline),
        auto_enroll_new_leads=bool(profile.auto_enroll_new_leads),
    )


# ── Campaign CRUD ────────────────────────────────────────────────────────

@router.get("")
async def list_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[DripCampaignResponse]:
    """List all drip campaigns for the current tenant."""
    repo = DripCampaignRepository(db)
    campaigns = await repo.list_with_steps(tenant_id)
    return [_campaign_to_response(c) for c in campaigns]


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> DripCampaignResponse:
    """Get a drip campaign with its steps."""
    repo = DripCampaignRepository(db)
    campaign = await repo.get_with_steps(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_to_response(campaign)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: DripCampaignCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> DripCampaignResponse:
    """Create a new drip campaign."""
    _validate_window(body.send_window_start, body.send_window_end)
    repo = DripCampaignRepository(db)

    campaign = await repo.create(
        tenant_id=tenant_id,
        name=body.name,
        campaign_type=body.campaign_type,
        audience_filter=body.audience_filter,
        tag_filter=body.tag_filter,
        priority=body.priority,
        is_enabled=body.is_enabled,
        trigger_delay_minutes=body.trigger_delay_minutes,
        send_window_start=body.send_window_start,
        send_window_end=body.send_window_end,
        response_templates=body.response_templates,
    )

    if body.steps:
        await repo.upsert_steps(campaign.id, [s.model_dump() for s in body.steps])

    campaign = await repo.get_with_steps(tenant_id, campaign.id)
    return _campaign_to_response(campaign)


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    body: DripCampaignUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> DripCampaignResponse:
    """Update a drip campaign."""
    _validate_window(body.send_window_start, body.send_window_end)
    repo = DripCampaignRepository(db)
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
    if "send_window_start" in update_data or "send_window_end" in update_data:
        existing = await repo.get_by_id(tenant_id, campaign_id)
        if existing:
            new_start = update_data.get("send_window_start", existing.send_window_start)
            new_end = update_data.get("send_window_end", existing.send_window_end)
            _validate_window(new_start, new_end)

    campaign = await repo.update(tenant_id, campaign_id, **update_data)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign = await repo.get_with_steps(tenant_id, campaign.id)
    return _campaign_to_response(campaign)


@router.put("/{campaign_id}/steps")
async def update_campaign_steps(
    campaign_id: int,
    steps: list[DripStepRequest],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[DripStepResponse]:
    """Replace all steps for a campaign."""
    repo = DripCampaignRepository(db)
    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    new_steps = await repo.upsert_steps(campaign_id, [s.model_dump() for s in steps])
    return [
        DripStepResponse(
            id=s.id,
            step_number=s.step_number,
            delay_minutes=s.delay_minutes,
            message_template=s.message_template,
            check_availability=s.check_availability,
            fallback_template=s.fallback_template,
        )
        for s in new_steps
    ]


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete a drip campaign, its steps, and any enrollments referencing it."""
    from sqlalchemy import delete as sql_delete
    from app.persistence.models.drip_campaign import DripEnrollment

    repo = DripCampaignRepository(db)
    campaign = await repo.get_with_steps(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    await db.execute(
        sql_delete(DripEnrollment).where(
            DripEnrollment.tenant_id == tenant_id,
            DripEnrollment.campaign_id == campaign_id,
        )
    )
    await repo.delete(tenant_id, campaign_id)
    await db.commit()


# ── Enrollment Management ────────────────────────────────────────────────

@router.get("/enrollments/list")
async def list_enrollments(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[DripEnrollmentResponse]:
    """List drip enrollments for the current tenant."""
    enrollment_repo = DripEnrollmentRepository(db)
    campaign_repo = DripCampaignRepository(db)
    lead_repo = LeadRepository(db)

    if status_filter and status_filter in ("active", "responded"):
        enrollments = await enrollment_repo.list_active_for_tenant(tenant_id, skip, limit)
    else:
        enrollments = await enrollment_repo.list(tenant_id, skip, limit)

    # Build responses with lead/campaign info
    responses = []
    campaigns_cache: dict[int, object] = {}
    for e in enrollments:
        lead = await lead_repo.get_by_id(tenant_id, e.lead_id)
        if e.campaign_id not in campaigns_cache:
            campaigns_cache[e.campaign_id] = await campaign_repo.get_with_steps(tenant_id, e.campaign_id)
        campaign = campaigns_cache[e.campaign_id]

        responses.append(DripEnrollmentResponse(
            id=e.id,
            tenant_id=e.tenant_id,
            campaign_id=e.campaign_id,
            lead_id=e.lead_id,
            lead_name=lead.name if lead else None,
            lead_phone=lead.phone if lead else None,
            campaign_name=campaign.name if campaign else None,
            campaign_type=campaign.campaign_type if campaign else None,
            status=e.status,
            current_step=e.current_step,
            total_steps=len(campaign.steps) if campaign else 0,
            next_step_at=e.next_step_at.isoformat() if e.next_step_at else None,
            response_category=e.response_category,
            cancelled_reason=e.cancelled_reason,
            created_at=e.created_at.isoformat() if e.created_at else "",
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        ))

    return responses


@router.post("/enrollments/{enrollment_id}/cancel")
async def cancel_enrollment(
    enrollment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Cancel a drip enrollment."""
    service = DripCampaignService(db)
    # Verify ownership
    enrollment_repo = DripEnrollmentRepository(db)
    enrollment = await enrollment_repo.get_by_id(tenant_id, enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    success = await service.cancel_enrollment(enrollment_id, reason="manual")
    if not success:
        raise HTTPException(status_code=400, detail="Enrollment already completed or cancelled")
    return {"status": "cancelled"}


# ── Lead Drip Endpoints ──────────────────────────────────────────────────

@router.get("/leads/{lead_id}/status")
async def get_lead_drip_status(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[DripEnrollmentResponse]:
    """Get drip enrollment status for a specific lead."""
    enrollment_repo = DripEnrollmentRepository(db)
    campaign_repo = DripCampaignRepository(db)
    lead_repo = LeadRepository(db)

    enrollments = await enrollment_repo.list_for_lead(tenant_id, lead_id)
    lead = await lead_repo.get_by_id(tenant_id, lead_id)

    responses = []
    for e in enrollments:
        campaign = await campaign_repo.get_with_steps(tenant_id, e.campaign_id)
        responses.append(DripEnrollmentResponse(
            id=e.id,
            tenant_id=e.tenant_id,
            campaign_id=e.campaign_id,
            lead_id=e.lead_id,
            lead_name=lead.name if lead else None,
            lead_phone=lead.phone if lead else None,
            campaign_name=campaign.name if campaign else None,
            campaign_type=campaign.campaign_type if campaign else None,
            status=e.status,
            current_step=e.current_step,
            total_steps=len(campaign.steps) if campaign else 0,
            next_step_at=e.next_step_at.isoformat() if e.next_step_at else None,
            response_category=e.response_category,
            cancelled_reason=e.cancelled_reason,
            created_at=e.created_at.isoformat() if e.created_at else "",
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        ))
    return responses


@router.post("/leads/{lead_id}/opt-out")
async def opt_out_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Opt a lead out of all active drip campaigns."""
    service = DripCampaignService(db)
    count = await service.cancel_all_for_lead(tenant_id, lead_id, reason="manual_opt_out")
    return {"cancelled_count": count}


# ── Helpers ──────────────────────────────────────────────────────────────

def _campaign_to_response(campaign) -> DripCampaignResponse:
    """Convert a DripCampaign model to response schema."""
    return DripCampaignResponse(
        id=campaign.id,
        tenant_id=campaign.tenant_id,
        name=campaign.name,
        campaign_type=campaign.campaign_type,
        audience_filter=campaign.audience_filter,
        tag_filter=campaign.tag_filter or None,
        priority=campaign.priority or 100,
        is_enabled=campaign.is_enabled,
        trigger_delay_minutes=campaign.trigger_delay_minutes,
        send_window_start=campaign.send_window_start or "08:00",
        send_window_end=campaign.send_window_end or "21:00",
        response_templates=campaign.response_templates,
        steps=[
            DripStepResponse(
                id=s.id,
                step_number=s.step_number,
                delay_minutes=s.delay_minutes,
                message_template=s.message_template,
                check_availability=s.check_availability,
                fallback_template=s.fallback_template,
            )
            for s in sorted(campaign.steps, key=lambda s: s.step_number)
        ],
    )
