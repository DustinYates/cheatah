"""Contacts API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.contact_service import ContactService
from app.domain.services.conversation_service import ConversationService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.contact_repository import ContactRepository

router = APIRouter()


class ContactResponse(BaseModel):
    """Contact response model - matches frontend expectations."""

    id: int
    tenant_id: int
    lead_id: int | None
    name: str | None
    email: str | None
    phone_number: str | None
    opt_in_status: str | None
    source: str | None
    created_at: str

    class Config:
        from_attributes = True


class ContactsListResponse(BaseModel):
    """Contacts list response."""

    contacts: list[ContactResponse]
    total: int


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
                lead_id=contact.lead_id if hasattr(contact, 'lead_id') else None,
                name=contact.name,
                email=contact.email,
                phone_number=contact.phone,
                opt_in_status='verified',
                source=contact.source,
                created_at=contact.created_at.isoformat() if contact.created_at else None,
            )
            for contact in contacts
        ],
        total=len(contacts),
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Get a specific contact by ID."""
    contact_repo = ContactRepository(db)
    contact = await contact_repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    return ContactResponse(
        id=contact.id,
        tenant_id=contact.tenant_id,
        lead_id=contact.lead_id if hasattr(contact, 'lead_id') else None,
        name=contact.name,
        email=contact.email,
        phone_number=contact.phone,
        opt_in_status='verified',
        source=contact.source,
        created_at=contact.created_at.isoformat() if contact.created_at else None,
    )


@router.get("/{contact_id}/conversation", response_model=ConversationResponse)
async def get_contact_conversation(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ConversationResponse:
    """Get the conversation associated with a contact (via its lead)."""
    contact_repo = ContactRepository(db)
    contact = await contact_repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    # Contact links to Lead which links to Conversation
    if not contact.lead_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No lead associated with this contact",
        )
    
    # Get the lead to find conversation_id
    from app.persistence.repositories.lead_repository import LeadRepository
    lead_repo = LeadRepository(db)
    lead = await lead_repo.get_by_id(tenant_id, contact.lead_id)
    
    if not lead or not lead.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation associated with this contact",
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
