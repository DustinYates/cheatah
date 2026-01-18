"""Contacts API routes."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_tenant_context
from app.persistence.models.contact import Contact
from app.persistence.models.lead import Lead
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import User
from app.persistence.repositories.contact_repository import ContactRepository
from app.domain.services.contact_merge_service import ContactMergeService

router = APIRouter()


class ContactResponse(BaseModel):
    """Contact response schema."""

    id: int
    tenant_id: int
    name: str | None
    email: str | None
    phone: str | None
    source: str | None
    lead_id: int | None
    merged_into_contact_id: int | None
    created_at: str
    last_contacted: str | None = None

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    """Contact list response with pagination."""

    items: list[ContactResponse]
    total: int
    page: int
    page_size: int


class CreateContactRequest(BaseModel):
    """Create contact request."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None


class UpdateContactRequest(BaseModel):
    """Update contact request."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None


class DuplicateGroup(BaseModel):
    """A group of potential duplicate contacts."""
    
    group_id: str
    match_type: str  # "email", "phone", "name", "multiple"
    match_value: str
    contacts: list[ContactResponse]
    confidence: float  # 0.0 to 1.0


class DuplicatesResponse(BaseModel):
    """Response containing potential duplicate groups."""
    
    groups: list[DuplicateGroup]
    total_groups: int
    total_duplicates: int


class MergeConflictResponse(BaseModel):
    """Response for a field conflict during merge."""
    
    field: str
    values: dict[int, str]  # contact_id -> value


class MergePreviewResponse(BaseModel):
    """Preview of what a merge would do."""
    
    contacts: list[ContactResponse]
    conflicts: list[MergeConflictResponse]
    suggested_primary_id: int | None


class MergeContactsRequest(BaseModel):
    """Merge contacts request."""
    
    secondary_contact_ids: list[int]
    field_resolutions: dict[str, str | int]  # field -> "primary" or contact_id


class ContactAliasResponse(BaseModel):
    """Contact alias response."""
    
    id: int
    contact_id: int
    alias_type: str
    value: str
    is_primary: bool
    source_contact_id: int | None


class MergeHistoryEntry(BaseModel):
    """Merge history entry."""
    
    id: int
    merged_contact_id: int
    merged_contact_data: dict
    merged_by: str | None
    merged_at: str | None
    field_resolutions: dict | None


class CombinedHistoryResponse(BaseModel):
    """Combined conversation history response."""
    
    conversations: list[dict]
    merge_history: list[MergeHistoryEntry]
    aliases: list[ContactAliasResponse]


def _contact_to_response(
    contact: Contact,
    last_contacted: str | None = None,
) -> ContactResponse:
    """Convert a Contact model to ContactResponse."""
    return ContactResponse(
        id=contact.id,
        tenant_id=contact.tenant_id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        source=contact.source,
        lead_id=contact.lead_id,
        merged_into_contact_id=contact.merged_into_contact_id,
        created_at=contact.created_at.isoformat() if contact.created_at else "",
        last_contacted=last_contacted,
    )


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    include_merged: bool = Query(False),
) -> ContactListResponse:
    """List all contacts for the tenant with pagination."""
    repo = ContactRepository(db)

    # Calculate offset from page
    offset = (page - 1) * page_size

    # Get contacts using list_by_tenant
    contacts = await repo.list_by_tenant(
        tenant_id=tenant_id,
        skip=offset,
        limit=page_size,
    )

    # Query last contacted dates for all contacts in a single efficient query
    # This joins Contact -> Lead -> Conversation -> Message to find the max message timestamp
    contact_ids = [c.id for c in contacts]
    last_contacted_map: dict[int, str | None] = {}

    if contact_ids:
        # Subquery to get the max message created_at for each contact
        last_contacted_query = (
            select(
                Contact.id.label("contact_id"),
                func.max(Message.created_at).label("last_contacted"),
            )
            .select_from(Contact)
            .outerjoin(Lead, Contact.lead_id == Lead.id)
            .outerjoin(Conversation, Lead.conversation_id == Conversation.id)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(Contact.id.in_(contact_ids))
            .group_by(Contact.id)
        )

        result = await db.execute(last_contacted_query)
        for row in result:
            if row.last_contacted:
                last_contacted_map[row.contact_id] = row.last_contacted.isoformat()

    # For now, estimate total as we don't have a count method
    # If we get a full page, there might be more
    total = offset + len(contacts)
    if len(contacts) == page_size:
        total += 1  # Indicate there might be more

    return ContactListResponse(
        items=[
            _contact_to_response(c, last_contacted=last_contacted_map.get(c.id))
            for c in contacts
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/duplicates", response_model=DuplicatesResponse)
async def find_duplicates(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
) -> DuplicatesResponse:
    """Find potential duplicate contacts within the tenant."""
    repo = ContactRepository(db)
    
    # Get all active contacts
    contacts = await repo.list_by_tenant(
        tenant_id=tenant_id,
        skip=0,
        limit=10000,  # Get all for duplicate detection
    )
    
    # Group by potential duplicates
    email_groups: dict[str, list[Contact]] = {}
    phone_groups: dict[str, list[Contact]] = {}
    name_groups: dict[str, list[Contact]] = {}
    
    for contact in contacts:
        if contact.email:
            email_key = contact.email.lower().strip()
            if email_key not in email_groups:
                email_groups[email_key] = []
            email_groups[email_key].append(contact)
        
        if contact.phone:
            # Normalize phone (remove non-digits)
            phone_key = ''.join(c for c in contact.phone if c.isdigit())
            if len(phone_key) >= 10:  # At least 10 digits
                if phone_key not in phone_groups:
                    phone_groups[phone_key] = []
                phone_groups[phone_key].append(contact)
        
        if contact.name:
            name_key = contact.name.lower().strip()
            if name_key not in name_groups:
                name_groups[name_key] = []
            name_groups[name_key].append(contact)
    
    # Build duplicate groups
    duplicate_groups: list[DuplicateGroup] = []
    seen_contact_ids: set[int] = set()
    group_counter = 0
    
    # Email matches (highest confidence)
    for email, group_contacts in email_groups.items():
        if len(group_contacts) > 1:
            contact_ids = {c.id for c in group_contacts}
            if not contact_ids.issubset(seen_contact_ids):
                group_counter += 1
                duplicate_groups.append(DuplicateGroup(
                    group_id=f"email-{group_counter}",
                    match_type="email",
                    match_value=email,
                    contacts=[_contact_to_response(c) for c in group_contacts],
                    confidence=0.95,
                ))
                seen_contact_ids.update(contact_ids)
    
    # Phone matches (high confidence)
    for phone, group_contacts in phone_groups.items():
        if len(group_contacts) > 1:
            contact_ids = {c.id for c in group_contacts}
            if not contact_ids.issubset(seen_contact_ids):
                group_counter += 1
                duplicate_groups.append(DuplicateGroup(
                    group_id=f"phone-{group_counter}",
                    match_type="phone",
                    match_value=phone,
                    contacts=[_contact_to_response(c) for c in group_contacts],
                    confidence=0.9,
                ))
                seen_contact_ids.update(contact_ids)
    
    # Name matches (lower confidence)
    for name, group_contacts in name_groups.items():
        if len(group_contacts) > 1:
            contact_ids = {c.id for c in group_contacts}
            if not contact_ids.issubset(seen_contact_ids):
                group_counter += 1
                duplicate_groups.append(DuplicateGroup(
                    group_id=f"name-{group_counter}",
                    match_type="name",
                    match_value=name,
                    contacts=[_contact_to_response(c) for c in group_contacts],
                    confidence=0.6,
                ))
                seen_contact_ids.update(contact_ids)
    
    # Filter by minimum confidence
    filtered_groups = [g for g in duplicate_groups if g.confidence >= min_confidence]
    
    total_duplicates = sum(len(g.contacts) for g in filtered_groups)
    
    return DuplicatesResponse(
        groups=filtered_groups,
        total_groups=len(filtered_groups),
        total_duplicates=total_duplicates,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Get a specific contact."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    return _contact_to_response(contact)


class ContactConversationResponse(BaseModel):
    """Contact conversation response with messages."""
    
    id: int
    channel: str
    created_at: str
    messages: list[dict]
    
    class Config:
        from_attributes = True


@router.get("/{contact_id}/conversation")
async def get_contact_conversation(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactConversationResponse:
    """Get the conversation history for a contact.
    
    This finds the conversation via the contact's linked lead.
    """
    from app.persistence.repositories.lead_repository import LeadRepository
    from app.domain.services.conversation_service import ConversationService
    
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    # Get the lead to find the conversation
    if not contact.lead_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation found for this contact",
        )
    
    lead_repo = LeadRepository(db)
    lead = await lead_repo.get_by_id(tenant_id, contact.lead_id)
    
    if not lead or not lead.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No conversation found for this contact",
        )
    
    # Get the conversation with messages
    conversation_service = ConversationService(db)
    conversation = await conversation_service.get_conversation(tenant_id, lead.conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    messages = await conversation_service.get_conversation_history(tenant_id, lead.conversation_id)
    
    return ContactConversationResponse(
        id=conversation.id,
        channel=conversation.channel,
        created_at=conversation.created_at.isoformat() if conversation.created_at else "",
        messages=[
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in messages
        ],
    )


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    request: CreateContactRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Create a new contact."""
    if not request.name and not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of name, email, or phone is required",
        )
    
    repo = ContactRepository(db)
    contact = await repo.create(
        tenant_id=tenant_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        source=request.source or "manual",
    )
    
    return _contact_to_response(contact)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    request: UpdateContactRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ContactResponse:
    """Update a contact."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    # Update fields
    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.email is not None:
        update_data["email"] = request.email
    if request.phone is not None:
        update_data["phone"] = request.phone
    if request.source is not None:
        update_data["source"] = request.source
    
    if update_data:
        contact = await repo.update(tenant_id, contact_id, **update_data)
    
    return _contact_to_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete a contact (soft delete)."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    await repo.soft_delete(tenant_id, contact_id, current_user.id)


@router.post("/merge-preview", response_model=MergePreviewResponse)
async def merge_preview(
    contact_ids: list[int],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> MergePreviewResponse:
    """Preview a merge operation to see conflicts."""
    if len(contact_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 contacts required for merge preview",
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
                field=c.field,
                values={k: str(v) if v else "" for k, v in c.values.items()}
            )
            for c in preview.conflicts
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
            field_resolutions=request.field_resolutions or {},
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # Log to stderr for Cloud Run logs
        import sys
        import traceback
        print(f"ERROR in merge_contacts: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
    
    return _contact_to_response(merged_contact)


@router.get("/{contact_id}/aliases", response_model=list[ContactAliasResponse])
async def get_contact_aliases(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[ContactAliasResponse]:
    """Get all aliases for a contact."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    from app.persistence.repositories.contact_alias_repository import ContactAliasRepository
    alias_repo = ContactAliasRepository(db)
    aliases = await alias_repo.get_aliases_for_contact(contact_id)
    
    return [
        ContactAliasResponse(
            id=a.id,
            contact_id=a.contact_id,
            alias_type=a.alias_type,
            value=a.value,
            is_primary=a.is_primary,
            source_contact_id=a.source_contact_id,
        )
        for a in aliases
    ]


@router.get("/{contact_id}/merge-history", response_model=list[MergeHistoryEntry])
async def get_merge_history(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[MergeHistoryEntry]:
    """Get merge history for a contact."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id_any_status(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    merge_service = ContactMergeService(db)
    history = await merge_service.get_merge_history(tenant_id, contact_id)
    
    return [MergeHistoryEntry(**entry) for entry in history]


@router.get("/{contact_id}/combined-history", response_model=CombinedHistoryResponse)
async def get_combined_history(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CombinedHistoryResponse:
    """Get combined conversation history from this contact and all merged contacts."""
    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    
    merge_service = ContactMergeService(db)
    
    # Get combined conversations
    conversations = await merge_service.get_combined_conversation_history(
        tenant_id, contact_id
    )
    
    # Get merge history
    history = await merge_service.get_merge_history(tenant_id, contact_id)
    
    # Get aliases
    from app.persistence.repositories.contact_alias_repository import ContactAliasRepository
    alias_repo = ContactAliasRepository(db)
    aliases = await alias_repo.get_aliases_for_contact(contact_id)
    
    return CombinedHistoryResponse(
        conversations=[
            {
                "id": c.id,
                "channel": c.channel,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "message_count": len(c.messages) if c.messages else 0,
            }
            for c in conversations
        ],
        merge_history=[MergeHistoryEntry(**entry) for entry in history],
        aliases=[
            ContactAliasResponse(
                id=a.id,
                contact_id=a.contact_id,
                alias_type=a.alias_type,
                value=a.value,
                is_primary=a.is_primary,
                source_contact_id=a.source_contact_id,
            )
            for a in aliases
        ],
    )


@router.post("/{contact_id}/unmerge/{secondary_contact_id}")
async def unmerge_contact(
    contact_id: int,
    secondary_contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Unmerge a previously merged contact (restore it)."""
    # This is a placeholder for unmerge functionality
    # Implementation would involve:
    # 1. Finding the merge log entry
    # 2. Restoring the secondary contact from the snapshot
    # 3. Moving back any entities that were reassigned
    # 4. Removing aliases that came from the secondary
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Unmerge functionality is not yet implemented",
    )
