"""Contacts API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.contact_service import ContactService
from app.persistence.database import get_db
from app.persistence.models.tenant import User

router = APIRouter()


class ContactResponse(BaseModel):
    """Contact response model - matches frontend expectations."""

    id: int
    tenant_id: int
    name: str | None
    email: str | None
    phone_number: str | None  # Frontend expects phone_number, not phone
    opt_in_status: str | None  # Frontend expects opt_in_status, maps from source
    source: str | None
    created_at: str

    class Config:
        from_attributes = True


class ContactsListResponse(BaseModel):
    """Contacts list response."""

    contacts: list[ContactResponse]
    total: int


@router.get("", response_model=ContactsListResponse)
async def list_contacts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> ContactsListResponse:
    """List contacts for the current tenant."""
    contact_service = ContactService(db)
    contacts = await contact_service.list_contacts(tenant_id, skip=skip, limit=limit)
    
    return ContactsListResponse(
        contacts=[
            ContactResponse(
                id=contact.id,
                tenant_id=contact.tenant_id,
                name=contact.name,
                email=contact.email,
                phone_number=contact.phone,  # Map phone to phone_number for frontend
                opt_in_status='verified',  # All contacts from leads are verified
                source=contact.source,
                created_at=contact.created_at.isoformat() if contact.created_at else None,
            )
            for contact in contacts
        ],
        total=len(contacts),
    )

