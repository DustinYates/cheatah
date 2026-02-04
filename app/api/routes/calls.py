"""Calls API endpoints."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_tenant, get_current_user, require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.tenant import User
from app.persistence.repositories.call_repository import CallRepository
from app.persistence.repositories.call_summary_repository import CallSummaryRepository

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class CallSummaryResponse(BaseModel):
    """Call summary response model."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    intent: str | None = None
    outcome: str | None = None
    summary_text: str | None = None
    transcript: str | None = None
    extracted_fields: dict | None = None
    contact_id: int | None = None
    lead_id: int | None = None
    created_at: datetime


class CallResponse(BaseModel):
    """Call response model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    tenant_id: int
    call_sid: str
    from_number: str
    to_number: str
    status: str
    direction: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration: int | None = None
    recording_url: str | None = None
    created_at: datetime
    summary: CallSummaryResponse | None = None


class CallListResponse(BaseModel):
    """Paginated call list response."""
    calls: list[CallResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class ContactCallResponse(BaseModel):
    """Call response for contact profile."""
    id: int
    call_sid: str
    from_number: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration: int | None = None
    recording_url: str | None = None
    intent: str | None = None
    outcome: str | None = None
    summary_preview: str | None = None
    created_at: datetime


@router.get("", response_model=CallListResponse)
async def list_calls(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    intent: str | None = Query(None, description="Filter by intent"),
    outcome: str | None = Query(None, description="Filter by outcome"),
    status: str | None = Query(None, description="Filter by call status"),
    direction: str | None = Query(None, description="Filter by direction (inbound/outbound)"),
) -> CallListResponse:
    """List calls for the current tenant.
    
    Args:
        current_user: Current authenticated user
        tenant_id: Tenant ID from context
        db: Database session
        page: Page number (1-indexed)
        page_size: Number of items per page
        intent: Optional intent filter
        outcome: Optional outcome filter
        status: Optional call status filter
        direction: Optional direction filter
        
    Returns:
        Paginated list of calls
    """
    # Build base query
    query = (
        select(Call)
        .where(Call.tenant_id == tenant_id)
        .options(joinedload(Call.summary))
        .order_by(Call.created_at.desc())
    )
    
    # Apply filters
    if status:
        query = query.where(Call.status == status)
    if direction:
        query = query.where(Call.direction == direction)
    
    # Count total before pagination
    count_query = select(func.count()).select_from(Call).where(Call.tenant_id == tenant_id)
    if status:
        count_query = count_query.where(Call.status == status)
    if direction:
        count_query = count_query.where(Call.direction == direction)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # Execute query
    result = await db.execute(query)
    calls = list(result.unique().scalars().all())
    
    # Filter by intent/outcome if specified (requires join with summary)
    if intent or outcome:
        filtered_calls = []
        for call in calls:
            if call.summary:
                if intent and call.summary.intent != intent:
                    continue
                if outcome and call.summary.outcome != outcome:
                    continue
            elif intent or outcome:
                continue  # Skip calls without summary if filtering by intent/outcome
            filtered_calls.append(call)
        calls = filtered_calls
    
    # Build response
    call_responses = []
    for call in calls:
        summary_response = None
        if call.summary:
            summary_response = CallSummaryResponse(
                id=call.summary.id,
                intent=call.summary.intent,
                outcome=call.summary.outcome,
                summary_text=call.summary.summary_text,
                transcript=call.summary.transcript,
                extracted_fields=call.summary.extracted_fields,
                contact_id=call.summary.contact_id,
                lead_id=call.summary.lead_id,
                created_at=call.summary.created_at,
            )

        call_responses.append(CallResponse(
            id=call.id,
            tenant_id=call.tenant_id,
            call_sid=call.call_sid,
            from_number=call.from_number,
            to_number=call.to_number,
            status=call.status,
            direction=call.direction,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration=call.duration,
            recording_url=call.recording_url,
            created_at=call.created_at,
            summary=summary_response,
        ))
    
    return CallListResponse(
        calls=call_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(calls)) < total,
    )


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CallResponse:
    """Get call details by ID.
    
    Args:
        call_id: Call ID
        current_user: Current authenticated user
        tenant_id: Tenant ID from context
        db: Database session
        
    Returns:
        Call details with summary
        
    Raises:
        HTTPException: If call not found
    """
    query = (
        select(Call)
        .where(Call.id == call_id, Call.tenant_id == tenant_id)
        .options(joinedload(Call.summary))
    )
    
    result = await db.execute(query)
    call = result.unique().scalar_one_or_none()
    
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call {call_id} not found",
        )
    
    summary_response = None
    if call.summary:
        summary_response = CallSummaryResponse(
            id=call.summary.id,
            intent=call.summary.intent,
            outcome=call.summary.outcome,
            summary_text=call.summary.summary_text,
            transcript=call.summary.transcript,
            extracted_fields=call.summary.extracted_fields,
            contact_id=call.summary.contact_id,
            lead_id=call.summary.lead_id,
            created_at=call.summary.created_at,
        )

    return CallResponse(
        id=call.id,
        tenant_id=call.tenant_id,
        call_sid=call.call_sid,
        from_number=call.from_number,
        to_number=call.to_number,
        status=call.status,
        direction=call.direction,
        started_at=call.started_at,
        ended_at=call.ended_at,
        duration=call.duration,
        recording_url=call.recording_url,
        created_at=call.created_at,
        summary=summary_response,
    )


@router.get("/by-contact/{contact_id}", response_model=list[ContactCallResponse])
async def get_calls_for_contact(
    contact_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100, description="Maximum number of calls to return"),
) -> list[ContactCallResponse]:
    """Get calls associated with a contact.
    
    Args:
        contact_id: Contact ID
        current_user: Current authenticated user
        tenant_id: Tenant ID from context
        db: Database session
        limit: Maximum number of calls to return
        
    Returns:
        List of calls for the contact
    """
    # Get call summaries linked to this contact
    call_summary_repo = CallSummaryRepository(db)
    summaries = await call_summary_repo.get_by_contact(contact_id, limit=limit)
    
    # Build response
    responses = []
    for summary in summaries:
        call = summary.call
        if call and call.tenant_id == tenant_id:
            # Truncate summary for preview
            summary_preview = None
            if summary.summary_text:
                summary_preview = summary.summary_text[:150]
                if len(summary.summary_text) > 150:
                    summary_preview += "..."
            
            responses.append(ContactCallResponse(
                id=call.id,
                call_sid=call.call_sid,
                from_number=call.from_number,
                status=call.status,
                started_at=call.started_at,
                ended_at=call.ended_at,
                duration=call.duration,
                recording_url=call.recording_url,
                intent=summary.intent,
                outcome=summary.outcome,
                summary_preview=summary_preview,
                created_at=call.created_at,
            ))
    
    return responses


@router.get("/by-phone/{phone_number}", response_model=list[ContactCallResponse])
async def get_calls_for_phone(
    phone_number: str,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100, description="Maximum number of calls to return"),
) -> list[ContactCallResponse]:
    """Get calls from a specific phone number.
    
    Args:
        phone_number: Phone number to search for
        current_user: Current authenticated user
        tenant_id: Tenant ID from context
        db: Database session
        limit: Maximum number of calls to return
        
    Returns:
        List of calls from the phone number
    """
    # Query calls by phone number
    query = (
        select(Call)
        .where(
            Call.tenant_id == tenant_id,
            Call.from_number == phone_number,
        )
        .options(joinedload(Call.summary))
        .order_by(Call.created_at.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    calls = list(result.unique().scalars().all())
    
    # Build response
    responses = []
    for call in calls:
        summary = call.summary
        summary_preview = None
        intent = None
        outcome = None
        
        if summary:
            intent = summary.intent
            outcome = summary.outcome
            if summary.summary_text:
                summary_preview = summary.summary_text[:150]
                if len(summary.summary_text) > 150:
                    summary_preview += "..."
        
        responses.append(ContactCallResponse(
            id=call.id,
            call_sid=call.call_sid,
            from_number=call.from_number,
            status=call.status,
            started_at=call.started_at,
            ended_at=call.ended_at,
            duration=call.duration,
            recording_url=call.recording_url,
            intent=intent,
            outcome=outcome,
            summary_preview=summary_preview,
            created_at=call.created_at,
        ))
    
    return responses

