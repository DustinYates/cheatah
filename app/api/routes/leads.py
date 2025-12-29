"""Leads API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.lead_service import LeadService
from app.domain.services.conversation_service import ConversationService
from app.domain.services.followup_service import FollowUpService
from app.persistence.database import get_db
from app.persistence.models.conversation import Message
from app.persistence.models.tenant import User

router = APIRouter()


class LeadResponse(BaseModel):
    """Lead response model."""

    id: int
    tenant_id: int
    conversation_id: int | None
    name: str | None
    email: str | None
    phone: str | None
    status: str | None
    extra_data: dict | None
    created_at: str
    llm_responded: bool | None = None  # True if assistant responded, False if not, None if no conversation

    class Config:
        from_attributes = True


class LeadsListResponse(BaseModel):
    """Leads list response."""

    leads: list[LeadResponse]
    total: int


class LeadStatusUpdate(BaseModel):
    """Lead status update request."""
    
    status: str  # 'new', 'verified', 'unknown', 'dismissed'


class MessageResponse(BaseModel):
    """Message response model."""
    
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """Conversation with messages response."""
    
    id: int
    channel: str
    created_at: str
    messages: list[MessageResponse]

    class Config:
        from_attributes = True


async def _check_llm_responded(db: AsyncSession, conversation_id: int | None) -> bool | None:
    """Check if LLM responded in a conversation (has assistant messages)."""
    if not conversation_id:
        return None
    result = await db.execute(
        select(Message.id)
        .where(Message.conversation_id == conversation_id)
        .where(Message.role == "assistant")
        .limit(1)
    )
    return result.scalar() is not None


@router.get("", response_model=LeadsListResponse)
async def list_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None),
) -> LeadsListResponse:
    """List leads for the current tenant, optionally filtered by status."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Listing leads for tenant_id={tenant_id}, user={current_user.email}")

    lead_service = LeadService(db)
    leads = await lead_service.list_leads(tenant_id, skip=skip, limit=limit)

    logger.info(f"Found {len(leads)} leads for tenant_id={tenant_id}")

    # Filter by status if provided
    if status:
        leads = [l for l in leads if l.status == status]

    # Build response with llm_responded field
    lead_responses = []
    for lead in leads:
        llm_responded = await _check_llm_responded(db, lead.conversation_id)
        lead_responses.append(
            LeadResponse(
                id=lead.id,
                tenant_id=lead.tenant_id,
                conversation_id=lead.conversation_id,
                name=lead.name,
                email=lead.email,
                phone=lead.phone,
                status=lead.status if hasattr(lead, 'status') else None,
                extra_data=lead.extra_data,
                created_at=lead.created_at.isoformat() if lead.created_at else None,
                llm_responded=llm_responded,
            )
        )

    return LeadsListResponse(
        leads=lead_responses,
        total=len(leads),
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> LeadResponse:
    """Get a specific lead by ID."""
    lead_service = LeadService(db)
    lead = await lead_service.get_lead(tenant_id, lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    llm_responded = await _check_llm_responded(db, lead.conversation_id)

    return LeadResponse(
        id=lead.id,
        tenant_id=lead.tenant_id,
        conversation_id=lead.conversation_id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        status=lead.status if hasattr(lead, 'status') else None,
        extra_data=lead.extra_data,
        created_at=lead.created_at.isoformat() if lead.created_at else None,
        llm_responded=llm_responded,
    )


@router.get("/{lead_id}/conversation", response_model=ConversationResponse)
async def get_lead_conversation(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ConversationResponse:
    """Get the conversation associated with a lead."""
    lead_service = LeadService(db)
    lead = await lead_service.get_lead(tenant_id, lead_id)
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    
    if not lead.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation associated with this lead",
        )
    
    conversation_service = ConversationService(db)
    conversation = await conversation_service.get_conversation(tenant_id, lead.conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    return ConversationResponse(
        id=conversation.id,
        channel=conversation.channel,
        created_at=conversation.created_at.isoformat(),
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            )
            for msg in conversation.messages
        ],
    )


@router.put("/{lead_id}/status", response_model=LeadResponse)
async def update_lead_status(
    lead_id: int,
    status_update: LeadStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> LeadResponse:
    """Update lead status (verify or mark unknown)."""
    valid_statuses = ['new', 'verified', 'unknown', 'dismissed']
    if status_update.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    lead_service = LeadService(db)
    lead = await lead_service.update_lead_status(tenant_id, lead_id, status_update.status)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    llm_responded = await _check_llm_responded(db, lead.conversation_id)

    return LeadResponse(
        id=lead.id,
        tenant_id=lead.tenant_id,
        conversation_id=lead.conversation_id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        status=lead.status if hasattr(lead, 'status') else None,
        extra_data=lead.extra_data,
        created_at=lead.created_at.isoformat() if lead.created_at else None,
        llm_responded=llm_responded,
    )


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete a lead by ID."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        lead_service = LeadService(db)
        deleted = await lead_service.delete_lead(tenant_id, lead_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting lead {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete lead: {str(e)}",
        )


class TriggerFollowUpResponse(BaseModel):
    """Response for trigger follow-up endpoint."""

    success: bool
    message: str
    task_id: str | None = None


@router.post("/{lead_id}/trigger-followup", response_model=TriggerFollowUpResponse)
async def trigger_followup(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TriggerFollowUpResponse:
    """Trigger an immediate follow-up SMS for a lead.

    Sends a follow-up SMS to the lead using the configured telephony provider
    (Twilio or Telnyx) and the Gemini LLM for intelligent responses.

    The lead must:
    - Have a phone number
    - Not have already received a follow-up

    Args:
        lead_id: Lead ID to trigger follow-up for
        db: Database session
        current_user: Authenticated user
        tenant_id: Tenant context

    Returns:
        TriggerFollowUpResponse with success status and task ID
    """
    import logging
    logger = logging.getLogger(__name__)

    # Verify lead exists
    lead_service = LeadService(db)
    lead = await lead_service.get_lead(tenant_id, lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    if not lead.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead has no phone number",
        )

    # Check if follow-up already sent
    if lead.extra_data and lead.extra_data.get("followup_sent_at"):
        return TriggerFollowUpResponse(
            success=False,
            message="Follow-up already sent for this lead",
        )

    # Trigger immediate follow-up
    followup_service = FollowUpService(db)
    task_name = await followup_service.trigger_immediate_followup(tenant_id, lead_id)

    if task_name:
        logger.info(f"Triggered follow-up for lead {lead_id} by user {current_user.email}")
        return TriggerFollowUpResponse(
            success=True,
            message="Follow-up SMS scheduled successfully",
            task_id=task_name,
        )
    else:
        return TriggerFollowUpResponse(
            success=False,
            message="Failed to schedule follow-up. Check SMS configuration.",
        )
