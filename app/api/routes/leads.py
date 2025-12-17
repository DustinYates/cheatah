"""Leads API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_id
from app.domain.services.lead_service import LeadService
from app.persistence.database import get_db
from app.persistence.models.user import User

router = APIRouter()


class LeadResponse(BaseModel):
    """Lead response model."""

    id: int
    tenant_id: int
    conversation_id: int | None
    name: str | None
    email: str | None
    phone: str | None
    extra_data: dict | None
    created_at: str

    class Config:
        from_attributes = True


class LeadsListResponse(BaseModel):
    """Leads list response."""

    leads: list[LeadResponse]
    total: int


@router.get("", response_model=LeadsListResponse)
async def list_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(get_tenant_id)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> LeadsListResponse:
    """List leads for the current tenant."""
    lead_service = LeadService(db)
    leads = await lead_service.list_leads(tenant_id, skip=skip, limit=limit)
    
    return LeadsListResponse(
        leads=[
            LeadResponse(
                id=lead.id,
                tenant_id=lead.tenant_id,
                conversation_id=lead.conversation_id,
                name=lead.name,
                email=lead.email,
                phone=lead.phone,
                extra_data=lead.extra_data,
                created_at=lead.created_at.isoformat() if lead.created_at else None,
            )
            for lead in leads
        ],
        total=len(leads),
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(get_tenant_id)],
) -> LeadResponse:
    """Get a specific lead by ID."""
    lead_service = LeadService(db)
    lead = await lead_service.get_lead(tenant_id, lead_id)
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    
    return LeadResponse(
        id=lead.id,
        tenant_id=lead.tenant_id,
        conversation_id=lead.conversation_id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        extra_data=lead.extra_data,
        created_at=lead.created_at.isoformat() if lead.created_at else None,
    )
