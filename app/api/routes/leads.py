"""Leads API endpoints."""

from typing import Annotated
from datetime import timezone

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

def _isoformat_utc(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


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


async def _sync_calls_to_leads_for_tenant(db: AsyncSession, tenant_id: int, logger) -> None:
    """Auto-sync calls to leads for a specific tenant.

    This runs when the leads list is fetched to ensure voice calls appear on the dashboard.
    """
    from app.persistence.models.call import Call
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.lead import Lead
    from sqlalchemy.orm import joinedload
    from sqlalchemy.orm.attributes import flag_modified

    try:
        # Find calls for this tenant that have a from_number
        stmt = (
            select(Call)
            .options(joinedload(Call.summary))
            .where(Call.tenant_id == tenant_id)
            .where(Call.from_number.isnot(None))
            .order_by(Call.created_at.desc())
            .limit(100)  # Limit to recent calls for performance
        )
        result = await db.execute(stmt)
        calls = result.unique().scalars().all()

        if not calls:
            return

        synced = 0
        for call in calls:
            if not call.from_number:
                continue

            # Normalize phone number
            normalized_phone = call.from_number
            if not normalized_phone.startswith("+"):
                if len(normalized_phone) == 10:
                    normalized_phone = "+1" + normalized_phone
                elif len(normalized_phone) == 11 and normalized_phone.startswith("1"):
                    normalized_phone = "+" + normalized_phone

            # Check if lead exists (get most recent if multiple)
            lead_stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.phone == normalized_phone,
            ).order_by(Lead.created_at.desc()).limit(1)
            lead_result = await db.execute(lead_stmt)
            lead = lead_result.scalar_one_or_none()

            # Get call data
            caller_name = None
            caller_email = None
            summary_text = None
            caller_intent = None

            if call.summary:
                extracted = call.summary.extracted_fields or {}
                caller_name = extracted.get("name")
                caller_email = extracted.get("email")
                caller_intent = extracted.get("reason")
                summary_text = call.summary.summary_text

            call_data = {
                "source": "voice_call",
                "call_id": call.id,
                "call_date": call.created_at.strftime("%Y-%m-%d %H:%M") if call.created_at else None,
                "summary": summary_text,
                "caller_name": caller_name,
                "caller_email": caller_email,
                "caller_intent": caller_intent,
                "duration": call.duration,
            }

            if not lead:
                # Create new lead - use phone number as fallback name
                display_name = caller_name if caller_name else f"Caller {normalized_phone}"
                lead = Lead(
                    tenant_id=tenant_id,
                    phone=normalized_phone,
                    name=display_name,
                    email=caller_email,
                    status="new",
                    extra_data={"voice_calls": [call_data]},
                )
                db.add(lead)
                synced += 1
            else:
                # Check if this call is already in the lead's voice_calls
                existing_data = dict(lead.extra_data) if lead.extra_data else {}
                voice_calls = existing_data.get("voice_calls", [])
                existing_call_ids = [vc.get("call_id") for vc in voice_calls if isinstance(vc, dict)]

                if call.id not in existing_call_ids:
                    voice_calls = list(voice_calls)
                    voice_calls.append(call_data)
                    existing_data["voice_calls"] = voice_calls
                    lead.extra_data = existing_data
                    flag_modified(lead, "extra_data")

                    if caller_name and not lead.name:
                        lead.name = caller_name
                    if caller_email and not lead.email:
                        lead.email = caller_email
                    # Update created_at to call time so lead appears at top
                    if call.created_at:
                        lead.created_at = call.created_at
                    synced += 1

            # Link CallSummary to lead
            if call.summary and not call.summary.lead_id:
                await db.flush()
                call.summary.lead_id = lead.id

        if synced > 0:
            await db.commit()
            logger.info(f"Auto-synced {synced} calls to leads for tenant {tenant_id}")

    except Exception as e:
        logger.warning(f"Auto-sync calls to leads failed: {e}")


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

    # Auto-sync calls to leads before fetching (for this tenant only)
    await _sync_calls_to_leads_for_tenant(db, tenant_id, logger)

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
                created_at=_isoformat_utc(lead.created_at),
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
        created_at=_isoformat_utc(lead.created_at),
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
        created_at=_isoformat_utc(conversation.created_at),
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                created_at=_isoformat_utc(msg.created_at),
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
    task_name, error_message = await followup_service.trigger_immediate_followup(tenant_id, lead_id)

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
            message=error_message or "Failed to schedule follow-up. Check SMS configuration.",
        )


class RelatedLeadsResponse(BaseModel):
    """Related leads response."""

    leads: list[LeadResponse]


@router.get("/{lead_id}/related", response_model=RelatedLeadsResponse)
async def get_related_leads(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> RelatedLeadsResponse:
    """Get leads with the same email or phone as this lead.

    Useful for finding related interactions from the same person
    across different channels (chatbot, voice, SMS, email).
    """
    from app.persistence.repositories.lead_repository import LeadRepository

    lead_service = LeadService(db)
    lead = await lead_service.get_lead(tenant_id, lead_id)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Find related leads by email or phone
    repo = LeadRepository(db)
    related = await repo.find_leads_with_conversation_by_email_or_phone(
        tenant_id, email=lead.email, phone=lead.phone
    )

    # Exclude the current lead and build response
    lead_responses = []
    for rel_lead in related:
        if rel_lead.id == lead_id:
            continue
        llm_responded = await _check_llm_responded(db, rel_lead.conversation_id)
        lead_responses.append(
            LeadResponse(
                id=rel_lead.id,
                tenant_id=rel_lead.tenant_id,
                conversation_id=rel_lead.conversation_id,
                name=rel_lead.name,
                email=rel_lead.email,
                phone=rel_lead.phone,
                status=rel_lead.status if hasattr(rel_lead, 'status') else None,
                extra_data=rel_lead.extra_data,
                created_at=_isoformat_utc(rel_lead.created_at),
                llm_responded=llm_responded,
            )
        )

    return RelatedLeadsResponse(leads=lead_responses)


@router.delete("/cleanup/none-names")
async def cleanup_none_name_leads(
    tenant_id: int = Depends(require_tenant_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all leads with None/NULL/empty names for this tenant."""
    from sqlalchemy import text, or_
    from app.persistence.models.lead import Lead

    # Delete leads with NULL, empty string, or 'None' as name
    result = await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            or_(
                Lead.name == None,
                Lead.name == "",
                Lead.name == "None",
            )
        )
    )
    leads_to_delete = result.scalars().all()
    count = len(leads_to_delete)

    for lead in leads_to_delete:
        await db.delete(lead)

    await db.commit()

    return {"deleted": count, "message": f"Deleted {count} leads with None/empty names"}


@router.delete("/cleanup/test-data")
async def cleanup_test_leads(
    tenant_id: int = Depends(require_tenant_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all test/junk leads for this tenant (None names, Caller + prefix, SMS Contact prefix)."""
    from sqlalchemy import or_
    from app.persistence.models.lead import Lead

    # Delete leads that are test data
    result = await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            or_(
                Lead.name == None,
                Lead.name == "",
                Lead.name == "None",
                Lead.name.like("Caller +%"),
                Lead.name.like("SMS Contact +%"),
            )
        )
    )
    leads_to_delete = result.scalars().all()
    count = len(leads_to_delete)

    for lead in leads_to_delete:
        await db.delete(lead)

    await db.commit()

    return {"deleted": count, "message": f"Deleted {count} test leads"}
