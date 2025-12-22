"""Contacts API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.contact_service import ContactService
from app.domain.services.contact_merge_service import ContactMergeService
from app.domain.services.conversation_service import ConversationService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.contact_repository import ContactRepository

router = APIRouter()


# ============== Response Models ==============

class AliasResponse(BaseModel):
    """Alias response model."""
    
    id: int
    alias_type: str
    value: str
    is_primary: bool
    created_at: str

    class Config:
        from_attributes = True


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
    aliases: list[AliasResponse] | None = None

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


class MergeConflictResponse(BaseModel):
    """Merge conflict response."""
    
    field: str
    values: dict[str, str]  # contact_id -> value


class MergePreviewResponse(BaseModel):
    """Merge preview response."""
    
    contacts: list[ContactResponse]
    conflicts: list[MergeConflictResponse]
    suggested_primary_id: int | None


class MergeHistoryEntry(BaseModel):
    """Merge history entry."""
    
    id: int
    merged_contact_id: int
    merged_contact_data: dict | None
    merged_by: str | None
    merged_at: str | None
    field_resolutions: dict | None


# ============== Request Models ==============

class UpdateContactRequest(BaseModel):
    """Update contact request."""
    
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class MergeContactsRequest(BaseModel):
    """Merge contacts request."""
    
    secondary_contact_ids: list[int]
    field_resolutions: dict[str, str | int]  # field -> "primary" or contact_id


class AddAliasRequest(BaseModel):
    """Add alias request."""
    
    alias_type: str  # 'email', 'phone', 'name'
    value: str
    is_primary: bool = False


# ============== Helper Functions ==============

def _contact_to_response(contact, include_aliases: bool = False) -> ContactResponse:
    """Convert a contact model to response."""
    aliases = None
    if include_aliases and hasattr(contact, 'aliases') and contact.aliases:
        aliases = [
            AliasResponse(
                id=alias.id,
                alias_type=alias.alias_type,
                value=alias.value,
                is_primary=alias.is_primary,
                created_at=alias.created_at.isoformat() if alias.created_at else "",
            )
            for alias in contact.aliases
        ]
    
    return ContactResponse(
        id=contact.id,
        tenant_id=contact.tenant_id,
        lead_id=contact.lead_id if hasattr(contact, 'lead_id') else None,
        name=contact.name,
        email=contact.email,
        phone_number=contact.phone,
        opt_in_status='verified',
        source=contact.source,
        created_at=contact.created_at.isoformat() if contact.created_at else "",
        aliases=aliases,
    )


# ============== Contact CRUD Endpoints ==============

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
        contacts=[_contact_to_response(contact) for contact in contacts],
        total=len(contacts),
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    include_aliases: bool = Query(False),
) -> ContactResponse:
    """Get a specific contact by ID."""
    contact_service = ContactService(db)
    
    if include_aliases:
        contact = await contact_service.get_contact_with_aliases(tenant_id, contact_id)
    else:
        contact = await contact_service.get_contact(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    return _contact_to_response(contact, include_aliases=include_aliases)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    request: UpdateContactRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Update a contact's information."""
    contact_service = ContactService(db)
    
    contact = await contact_service.update_contact(
        tenant_id,
        contact_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
    )
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    return _contact_to_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Permanently delete a contact."""
    contact_service = ContactService(db)
    
    deleted = await contact_service.delete_contact(tenant_id, contact_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )


# ============== Conversation Endpoint ==============

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


# ============== Merge Endpoints ==============

@router.post("/merge/preview", response_model=MergePreviewResponse)
async def get_merge_preview(
    contact_ids: list[int] = Body(..., embed=True),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    tenant_id: Annotated[int, Depends(require_tenant_context)] = None,
) -> MergePreviewResponse:
    """Get a preview of merging multiple contacts."""
    if len(contact_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 contacts required for merge",
        )
    
    merge_service = ContactMergeService(db)
    
    try:
        preview = await merge_service.get_merge_preview(tenant_id, contact_ids)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MergePreviewResponse(
        contacts=[_contact_to_response(c) for c in preview.contacts],
        conflicts=[
            MergeConflictResponse(
                field=conflict.field,
                values={str(k): v for k, v in conflict.values.items()},
            )
            for conflict in preview.conflicts
        ],
        suggested_primary_id=preview.suggested_primary_id,
    )


@router.post("/{contact_id}/merge", response_model=ContactResponse)
async def merge_contacts(
    contact_id: int,
    request: MergeContactsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Merge multiple contacts into a primary contact."""
    if not request.secondary_contact_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one secondary contact required",
        )
    
    merge_service = ContactMergeService(db)
    
    try:
        merged_contact = await merge_service.merge_contacts(
            tenant_id=tenant_id,
            primary_contact_id=contact_id,
            secondary_contact_ids=request.secondary_contact_ids,
            field_resolutions=request.field_resolutions,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return _contact_to_response(merged_contact)


@router.get("/{contact_id}/merge-history", response_model=list[MergeHistoryEntry])
async def get_merge_history(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[MergeHistoryEntry]:
    """Get merge history for a contact."""
    merge_service = ContactMergeService(db)
    
    history = await merge_service.get_merge_history(tenant_id, contact_id)
    
    return [
        MergeHistoryEntry(
            id=entry['id'],
            merged_contact_id=entry['merged_contact_id'],
            merged_contact_data=entry['merged_contact_data'],
            merged_by=entry['merged_by'],
            merged_at=entry['merged_at'],
            field_resolutions=entry['field_resolutions'],
        )
        for entry in history
    ]


# ============== Alias Endpoints ==============

@router.get("/{contact_id}/aliases", response_model=list[AliasResponse])
async def get_contact_aliases(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    alias_type: str | None = Query(None),
) -> list[AliasResponse]:
    """Get all aliases for a contact."""
    contact_service = ContactService(db)
    
    # Verify contact exists
    contact = await contact_service.get_contact(tenant_id, contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    if alias_type:
        aliases = await contact_service.get_aliases_by_type(contact_id, alias_type)
    else:
        aliases = await contact_service.get_aliases(contact_id)
    
    return [
        AliasResponse(
            id=alias.id,
            alias_type=alias.alias_type,
            value=alias.value,
            is_primary=alias.is_primary,
            created_at=alias.created_at.isoformat() if alias.created_at else "",
        )
        for alias in aliases
    ]


@router.post("/{contact_id}/aliases", response_model=AliasResponse, status_code=status.HTTP_201_CREATED)
async def add_contact_alias(
    contact_id: int,
    request: AddAliasRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> AliasResponse:
    """Add an alias to a contact."""
    if request.alias_type not in ('email', 'phone', 'name'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="alias_type must be 'email', 'phone', or 'name'",
        )
    
    contact_service = ContactService(db)
    
    alias = await contact_service.add_alias(
        tenant_id=tenant_id,
        contact_id=contact_id,
        alias_type=request.alias_type,
        value=request.value,
        is_primary=request.is_primary,
    )
    
    if not alias:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    return AliasResponse(
        id=alias.id,
        alias_type=alias.alias_type,
        value=alias.value,
        is_primary=alias.is_primary,
        created_at=alias.created_at.isoformat() if alias.created_at else "",
    )


@router.put("/{contact_id}/aliases/{alias_id}/primary", response_model=AliasResponse)
async def set_primary_alias(
    contact_id: int,
    alias_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> AliasResponse:
    """Set an alias as the primary for its type."""
    contact_service = ContactService(db)
    
    alias = await contact_service.set_primary_alias(tenant_id, contact_id, alias_id)
    
    if not alias:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact or alias not found",
        )
    
    return AliasResponse(
        id=alias.id,
        alias_type=alias.alias_type,
        value=alias.value,
        is_primary=alias.is_primary,
        created_at=alias.created_at.isoformat() if alias.created_at else "",
    )


@router.delete("/{contact_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_contact_alias(
    contact_id: int,
    alias_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Remove an alias from a contact (cannot remove primary aliases)."""
    contact_service = ContactService(db)
    
    removed = await contact_service.remove_alias(tenant_id, contact_id, alias_id)
    
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alias not found, does not belong to contact, or is primary (cannot remove primary aliases)",
        )
