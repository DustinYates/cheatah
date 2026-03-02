"""Email campaign management API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_context
from app.domain.services.email_outreach_service import EmailOutreachService
from app.persistence.database import get_db
from app.persistence.repositories.email_campaign_repository import (
    EmailCampaignRepository,
    EmailCampaignRecipientRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Schemas ─────────────────────────────────────────────

class EmailCampaignCreateRequest(BaseModel):
    name: str
    subject_template: str
    email_prompt_instructions: str | None = None
    from_email: str | None = None
    reply_to: str | None = None
    unsubscribe_url: str
    physical_address: str
    send_at: str | None = None  # ISO datetime
    batch_size: int = 50
    batch_delay_seconds: int = 300


class EmailCampaignUpdateRequest(BaseModel):
    name: str | None = None
    subject_template: str | None = None
    email_prompt_instructions: str | None = None
    from_email: str | None = None
    reply_to: str | None = None
    unsubscribe_url: str | None = None
    physical_address: str | None = None
    send_at: str | None = None
    batch_size: int | None = None
    batch_delay_seconds: int | None = None


class RecipientRequest(BaseModel):
    email: str
    name: str | None = None
    company: str | None = None
    role: str | None = None
    personalization_data: dict | None = None


class RecipientResponse(BaseModel):
    id: int
    email: str
    name: str | None
    company: str | None
    role: str | None
    status: str
    generated_subject: str | None = None
    sent_at: str | None = None
    error_message: str | None = None


class EmailCampaignResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    status: str
    subject_template: str
    email_prompt_instructions: str | None
    from_email: str | None
    reply_to: str | None
    unsubscribe_url: str
    physical_address: str
    send_at: str | None
    batch_size: int
    batch_delay_seconds: int
    total_recipients: int
    sent_count: int
    failed_count: int
    created_at: str
    updated_at: str


class EmailCampaignDetailResponse(EmailCampaignResponse):
    status_counts: dict[str, int] = {}


# ── Campaign CRUD ────────────────────────────────────────────────────────

@router.get("")
async def list_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    status_filter: str | None = None,
) -> list[EmailCampaignResponse]:
    """List all email campaigns for the current tenant."""
    repo = EmailCampaignRepository(db)
    campaigns = await repo.list_campaigns(tenant_id, status=status_filter)
    return [_campaign_to_response(c) for c in campaigns]


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> EmailCampaignDetailResponse:
    """Get an email campaign with recipient status counts."""
    repo = EmailCampaignRepository(db)
    recipient_repo = EmailCampaignRecipientRepository(db)

    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    status_counts = await recipient_repo.count_by_status(campaign_id)
    resp = _campaign_to_response(campaign)
    return EmailCampaignDetailResponse(**resp.model_dump(), status_counts=status_counts)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: EmailCampaignCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> EmailCampaignResponse:
    """Create a new email campaign (draft)."""
    from datetime import datetime

    repo = EmailCampaignRepository(db)

    create_data = {
        "name": body.name,
        "subject_template": body.subject_template,
        "email_prompt_instructions": body.email_prompt_instructions,
        "from_email": body.from_email,
        "reply_to": body.reply_to,
        "unsubscribe_url": body.unsubscribe_url,
        "physical_address": body.physical_address,
        "batch_size": body.batch_size,
        "batch_delay_seconds": body.batch_delay_seconds,
    }
    if body.send_at:
        create_data["send_at"] = datetime.fromisoformat(body.send_at)

    campaign = await repo.create(tenant_id=tenant_id, **create_data)
    return _campaign_to_response(campaign)


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    body: EmailCampaignUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> EmailCampaignResponse:
    """Update an email campaign. Only draft/paused campaigns can be updated."""
    from datetime import datetime

    repo = EmailCampaignRepository(db)
    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(status_code=400, detail="Can only update draft or paused campaigns")

    update_data = body.model_dump(exclude_none=True)
    if "send_at" in update_data and update_data["send_at"]:
        update_data["send_at"] = datetime.fromisoformat(update_data["send_at"])

    campaign = await repo.update(tenant_id, campaign_id, **update_data)
    return _campaign_to_response(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete an email campaign. Only draft campaigns can be deleted."""
    repo = EmailCampaignRepository(db)
    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

    deleted = await repo.delete(tenant_id, campaign_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")


# ── Recipient Management ─────────────────────────────────────────────────

@router.post("/{campaign_id}/recipients", status_code=status.HTTP_201_CREATED)
async def add_recipients(
    campaign_id: int,
    recipients: list[RecipientRequest],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Add recipients to an email campaign."""
    repo = EmailCampaignRepository(db)
    recipient_repo = EmailCampaignRecipientRepository(db)

    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(status_code=400, detail="Can only add recipients to draft or paused campaigns")

    count = await recipient_repo.bulk_create(
        campaign_id=campaign_id,
        tenant_id=tenant_id,
        recipients=[r.model_dump() for r in recipients],
    )

    # Update total count
    status_counts = await recipient_repo.count_by_status(campaign_id)
    campaign.total_recipients = sum(status_counts.values())
    await db.commit()

    return {"added": count, "total_recipients": campaign.total_recipients}


@router.get("/{campaign_id}/recipients")
async def list_recipients(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    skip: int = 0,
    limit: int = 100,
) -> list[RecipientResponse]:
    """List recipients for an email campaign."""
    repo = EmailCampaignRepository(db)
    recipient_repo = EmailCampaignRecipientRepository(db)

    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    recipients = await recipient_repo.list_for_campaign(campaign_id, skip, limit)
    return [
        RecipientResponse(
            id=r.id,
            email=r.email,
            name=r.name,
            company=r.company,
            role=r.role,
            status=r.status,
            generated_subject=r.generated_subject,
            sent_at=r.sent_at.isoformat() if r.sent_at else None,
            error_message=r.error_message,
        )
        for r in recipients
    ]


@router.delete("/{campaign_id}/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recipient(
    campaign_id: int,
    recipient_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Remove a recipient from an email campaign."""
    recipient_repo = EmailCampaignRecipientRepository(db)
    recipient = await recipient_repo.get_by_id(tenant_id, recipient_id)
    if not recipient or recipient.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if recipient.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot remove already-sent recipient")

    await recipient_repo.delete(tenant_id, recipient_id)


# ── Campaign Actions ─────────────────────────────────────────────────────

@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Trigger sending for an email campaign. Schedules the first batch via Cloud Tasks."""
    repo = EmailCampaignRepository(db)
    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send campaign with status '{campaign.status}'",
        )

    service = EmailOutreachService(db)

    # Validate campaign has recipients
    recipient_repo = EmailCampaignRecipientRepository(db)
    status_counts = await recipient_repo.count_by_status(campaign_id)
    pending = status_counts.get("pending", 0)
    if pending == 0:
        raise HTTPException(status_code=400, detail="No pending recipients to send to")

    task_name = await service.trigger_campaign(campaign)
    return {
        "status": "scheduled",
        "pending_recipients": pending,
        "task_name": task_name,
    }


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Pause a sending email campaign."""
    repo = EmailCampaignRepository(db)
    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    service = EmailOutreachService(db)
    success = await service.pause_campaign(campaign)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause campaign with status '{campaign.status}'",
        )
    return {"status": "paused"}


@router.post("/{campaign_id}/preview")
async def preview_campaign_email(
    campaign_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    recipient_id: int | None = None,
) -> dict:
    """Generate a preview email for one recipient without sending.

    If recipient_id is not provided, uses the first pending recipient.
    """
    repo = EmailCampaignRepository(db)
    recipient_repo = EmailCampaignRecipientRepository(db)

    campaign = await repo.get_by_id(tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if recipient_id:
        recipient = await recipient_repo.get_by_id(tenant_id, recipient_id)
        if not recipient or recipient.campaign_id != campaign_id:
            raise HTTPException(status_code=404, detail="Recipient not found")
    else:
        batch = await recipient_repo.get_pending_batch(campaign_id, 1)
        if not batch:
            raise HTTPException(status_code=400, detail="No recipients to preview")
        recipient = batch[0]

    service = EmailOutreachService(db)
    preview = await service.preview_email(tenant_id, recipient, campaign)
    return preview


# ── Helpers ──────────────────────────────────────────────────────────────

def _campaign_to_response(campaign) -> EmailCampaignResponse:
    """Convert an EmailCampaign model to response schema."""
    return EmailCampaignResponse(
        id=campaign.id,
        tenant_id=campaign.tenant_id,
        name=campaign.name,
        status=campaign.status,
        subject_template=campaign.subject_template,
        email_prompt_instructions=campaign.email_prompt_instructions,
        from_email=campaign.from_email,
        reply_to=campaign.reply_to,
        unsubscribe_url=campaign.unsubscribe_url,
        physical_address=campaign.physical_address,
        send_at=campaign.send_at.isoformat() if campaign.send_at else None,
        batch_size=campaign.batch_size,
        batch_delay_seconds=campaign.batch_delay_seconds,
        total_recipients=campaign.total_recipients,
        sent_count=campaign.sent_count,
        failed_count=campaign.failed_count,
        created_at=campaign.created_at.isoformat() if campaign.created_at else "",
        updated_at=campaign.updated_at.isoformat() if campaign.updated_at else "",
    )
