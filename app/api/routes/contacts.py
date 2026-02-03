"""Contacts API routes."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from datetime import datetime, timedelta
from sqlalchemy import select, or_, func, union_all, cast, Date, literal_column, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_tenant_context
from app.persistence.models.contact import Contact
from app.persistence.models.lead import Lead
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import User
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.email_ingestion_log import EmailIngestionLog
from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.repositories.contact_repository import ContactRepository
from app.domain.services.contact_merge_service import ContactMergeService

router = APIRouter()


class ContactResponse(BaseModel):
    """Contact response schema."""

    id: int
    tenant_id: int
    name: str | None
    customer_name: str | None = None
    email: str | None
    phone: str | None
    source: str | None
    lead_id: int | None
    merged_into_contact_id: int | None
    created_at: str
    first_contacted: str | None = None
    last_contacted: str | None = None
    # Profile fields
    location: str | None = None
    company: str | None = None
    role: str | None = None
    tags: list[str] | None = None
    notes: str | None = None

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
    # Profile fields
    location: str | None = None
    company: str | None = None
    role: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


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


# Activity Heatmap schemas
class DayActivity(BaseModel):
    """Activity count for a single day."""
    date: str  # YYYY-MM-DD
    count: int
    sms: int = 0
    call: int = 0
    email: int = 0
    chat: int = 0


class ActivityHeatmapResponse(BaseModel):
    """Activity heatmap response for GitHub-style contribution graph."""
    start_date: str
    end_date: str
    data: list[DayActivity]
    total_interactions: int


# Activity Feed schemas
class ActivityItemDetails(BaseModel):
    """Details for an activity item."""
    duration: int | None = None  # For calls, in seconds
    intent: str | None = None
    outcome: str | None = None
    channel: str | None = None
    message_count: int | None = None
    subject: str | None = None


class ActivityItem(BaseModel):
    """A single item in the activity feed."""
    id: str
    type: str  # call, sms, email, chat
    timestamp: str
    summary: str
    details: ActivityItemDetails | None = None


class ActivityFeedResponse(BaseModel):
    """Activity feed response with pagination."""
    items: list[ActivityItem]
    total: int
    page: int
    has_more: bool


async def _get_customer_names_by_phone(
    db: AsyncSession,
    tenant_id: int,
    phone_numbers: list[str],
) -> dict[str, str]:
    """Get customer names from JackrabbitCustomer cache by phone number.

    Returns dict of phone_number -> customer_name
    """
    if not phone_numbers:
        return {}

    stmt = select(
        JackrabbitCustomer.phone_number,
        JackrabbitCustomer.name
    ).where(
        JackrabbitCustomer.tenant_id == tenant_id,
        JackrabbitCustomer.phone_number.in_(phone_numbers),
    )
    result = await db.execute(stmt)
    return {row.phone_number: row.name for row in result if row.name}


async def _get_contact_communication_timestamps(
    db: AsyncSession,
    contact_ids: list[int],
    tenant_id: int,
) -> dict[int, tuple[str | None, str | None]]:
    """Get first and last contacted timestamps for contacts across all channels.

    Returns dict of contact_id -> (first_contacted, last_contacted)
    """
    if not contact_ids:
        return {}

    # Subquery 1: Messages via Lead -> Conversation -> Message
    messages_query = (
        select(
            Contact.id.label("contact_id"),
            Message.created_at.label("timestamp"),
        )
        .select_from(Contact)
        .join(Lead, Contact.lead_id == Lead.id)
        .join(Conversation, Lead.conversation_id == Conversation.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Contact.id.in_(contact_ids),
            Message.created_at.isnot(None),
        )
    )

    # Subquery 2: Calls via CallSummary -> Call
    calls_query = (
        select(
            CallSummary.contact_id.label("contact_id"),
            Call.started_at.label("timestamp"),
        )
        .select_from(CallSummary)
        .join(Call, CallSummary.call_id == Call.id)
        .where(
            CallSummary.contact_id.in_(contact_ids),
            Call.started_at.isnot(None),
        )
    )

    # Subquery 3: Emails via Lead -> EmailIngestionLog
    emails_query = (
        select(
            Contact.id.label("contact_id"),
            EmailIngestionLog.received_at.label("timestamp"),
        )
        .select_from(Contact)
        .join(Lead, Contact.lead_id == Lead.id)
        .join(EmailIngestionLog, EmailIngestionLog.lead_id == Lead.id)
        .where(
            Contact.id.in_(contact_ids),
            EmailIngestionLog.status == "processed",
            EmailIngestionLog.received_at.isnot(None),
        )
    )

    # Combine all subqueries with UNION ALL
    combined = union_all(messages_query, calls_query, emails_query).subquery()

    # Aggregate to get min and max timestamps per contact
    final_query = select(
        combined.c.contact_id,
        func.min(combined.c.timestamp).label("first_contacted"),
        func.max(combined.c.timestamp).label("last_contacted"),
    ).group_by(combined.c.contact_id)

    result = await db.execute(final_query)

    timestamps: dict[int, tuple[str | None, str | None]] = {}
    for row in result:
        first = row.first_contacted.isoformat() if row.first_contacted else None
        last = row.last_contacted.isoformat() if row.last_contacted else None
        timestamps[row.contact_id] = (first, last)

    return timestamps


def _contact_to_response(
    contact: Contact,
    customer_name: str | None = None,
    first_contacted: str | None = None,
    last_contacted: str | None = None,
) -> ContactResponse:
    """Convert a Contact model to ContactResponse."""
    return ContactResponse(
        id=contact.id,
        tenant_id=contact.tenant_id,
        name=contact.name,
        customer_name=customer_name,
        email=contact.email,
        phone=contact.phone,
        source=contact.source,
        lead_id=contact.lead_id,
        merged_into_contact_id=contact.merged_into_contact_id,
        created_at=contact.created_at.isoformat() if contact.created_at else "",
        first_contacted=first_contacted,
        last_contacted=last_contacted,
        # Profile fields
        location=contact.location,
        company=contact.company,
        role=contact.role,
        tags=contact.tags or [],
        notes=contact.notes,
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

    contact_ids = [c.id for c in contacts]
    timestamps_map: dict[int, tuple[str | None, str | None]] = {}
    customer_names_map: dict[str, str] = {}

    if contact_ids:
        # Get first/last contacted timestamps across all channels (messages, calls, emails)
        timestamps_map = await _get_contact_communication_timestamps(db, contact_ids, tenant_id)

        # Get customer names from Jackrabbit cache by phone number
        phone_numbers = [c.phone for c in contacts if c.phone]
        if phone_numbers:
            customer_names_map = await _get_customer_names_by_phone(db, tenant_id, phone_numbers)

    # For now, estimate total as we don't have a count method
    # If we get a full page, there might be more
    total = offset + len(contacts)
    if len(contacts) == page_size:
        total += 1  # Indicate there might be more

    return ContactListResponse(
        items=[
            _contact_to_response(
                c,
                customer_name=customer_names_map.get(c.phone) if c.phone else None,
                first_contacted=timestamps_map.get(c.id, (None, None))[0],
                last_contacted=timestamps_map.get(c.id, (None, None))[1],
            )
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
    """Create a new contact, auto-merging if matching email/phone exists."""
    if not request.name and not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of name, email, or phone is required",
        )

    repo = ContactRepository(db)

    # Check for existing contacts with matching email or phone for auto-merge
    matching_contacts = await repo.get_all_by_email_or_phone(
        tenant_id, email=request.email, phone=request.phone
    )

    if len(matching_contacts) > 1:
        # Multiple matches - auto-merge them all
        merge_service = ContactMergeService(db)
        primary_contact = matching_contacts[0]  # Oldest contact
        secondary_ids = [c.id for c in matching_contacts[1:]]

        # Build field resolutions - prefer primary but fill missing from others or request
        field_resolutions = {}
        for field in ['name', 'email', 'phone']:
            primary_value = getattr(primary_contact, field)
            request_value = getattr(request, field)
            if not primary_value:
                # Check if request has this value
                if request_value:
                    # Keep as "primary" - we'll update it after merge
                    field_resolutions[field] = "primary"
                else:
                    # Find first secondary with this value
                    for secondary in matching_contacts[1:]:
                        if getattr(secondary, field):
                            field_resolutions[field] = secondary.id
                            break
                    else:
                        field_resolutions[field] = "primary"
            else:
                field_resolutions[field] = "primary"

        contact = await merge_service.merge_contacts(
            tenant_id=tenant_id,
            primary_contact_id=primary_contact.id,
            secondary_contact_ids=secondary_ids,
            field_resolutions=field_resolutions,
            user_id=current_user.id,
        )

        # Update with any new data from request
        update_fields = {}
        if request.name and not contact.name:
            update_fields["name"] = request.name
        if request.email and not contact.email:
            update_fields["email"] = request.email
        if request.phone and not contact.phone:
            update_fields["phone"] = request.phone
        if update_fields:
            contact = await repo.update_contact(tenant_id, contact.id, **update_fields)

    elif len(matching_contacts) == 1:
        # Single match - update with new data
        contact = matching_contacts[0]
        update_fields = {}
        if request.name and not contact.name:
            update_fields["name"] = request.name
        if request.email and not contact.email:
            update_fields["email"] = request.email
        if request.phone and not contact.phone:
            update_fields["phone"] = request.phone
        if update_fields:
            contact = await repo.update_contact(tenant_id, contact.id, **update_fields)

    else:
        # No matches - create new contact
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
    # Profile fields
    if request.location is not None:
        update_data["location"] = request.location
    if request.company is not None:
        update_data["company"] = request.company
    if request.role is not None:
        update_data["role"] = request.role
    if request.tags is not None:
        update_data["tags"] = request.tags
    if request.notes is not None:
        update_data["notes"] = request.notes

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


@router.get("/{contact_id}/activity-heatmap", response_model=ActivityHeatmapResponse)
async def get_contact_activity_heatmap(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    days: int = Query(365, ge=30, le=730),
) -> ActivityHeatmapResponse:
    """Get daily interaction counts for activity heatmap.

    Returns interaction data grouped by day for the past N days,
    suitable for rendering a GitHub-style contribution graph.
    """
    from app.persistence.models.tenant_email_config import EmailConversation

    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    # Subquery 1: SMS/Chat messages via Contact -> Lead -> Conversation -> Message
    messages_query = (
        select(
            cast(Message.created_at, Date).label("date"),
            Conversation.channel.label("channel"),
        )
        .select_from(Contact)
        .join(Lead, Contact.lead_id == Lead.id)
        .join(Conversation, Lead.conversation_id == Conversation.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Contact.id == contact_id,
            Message.created_at >= start_date,
            Message.role != "system",  # Exclude system messages
        )
    )

    # Subquery 2: Calls via CallSummary
    calls_query = (
        select(
            cast(Call.started_at, Date).label("date"),
            literal_column("'call'").label("channel"),
        )
        .select_from(CallSummary)
        .join(Call, CallSummary.call_id == Call.id)
        .where(
            CallSummary.contact_id == contact_id,
            Call.started_at >= start_date,
        )
    )

    # Subquery 3: Emails via EmailConversation
    emails_query = (
        select(
            cast(EmailConversation.created_at, Date).label("date"),
            literal_column("'email'").label("channel"),
        )
        .select_from(EmailConversation)
        .where(
            EmailConversation.contact_id == contact_id,
            EmailConversation.created_at >= start_date,
        )
    )

    # Combine all queries
    combined = union_all(messages_query, calls_query, emails_query).subquery()

    # Aggregate by date
    result = await db.execute(
        select(
            combined.c.date,
            func.count().label("total"),
            func.sum(func.cast(combined.c.channel == "sms", Integer)).label("sms"),
            func.sum(func.cast(combined.c.channel == "call", Integer)).label("call"),
            func.sum(func.cast(combined.c.channel == "email", Integer)).label("email"),
            func.sum(func.cast(combined.c.channel == "web", Integer)).label("chat"),
        )
        .group_by(combined.c.date)
        .order_by(combined.c.date)
    )

    # Build response data
    activity_by_date: dict[str, DayActivity] = {}
    total_interactions = 0

    for row in result:
        date_str = row.date.isoformat() if row.date else None
        if date_str:
            activity_by_date[date_str] = DayActivity(
                date=date_str,
                count=row.total or 0,
                sms=row.sms or 0,
                call=row.call or 0,
                email=row.email or 0,
                chat=row.chat or 0,
            )
            total_interactions += row.total or 0

    return ActivityHeatmapResponse(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        data=list(activity_by_date.values()),
        total_interactions=total_interactions,
    )


@router.get("/{contact_id}/activity-feed", response_model=ActivityFeedResponse)
async def get_contact_activity_feed(
    contact_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel: str | None = Query(None, description="Filter by channel: call, sms, email, chat"),
) -> ActivityFeedResponse:
    """Get paginated chronological activity feed for a contact.

    Returns a unified feed of all interactions (calls, SMS, emails, chat)
    sorted by most recent first.
    """
    from app.persistence.models.tenant_email_config import EmailConversation

    repo = ContactRepository(db)
    contact = await repo.get_by_id(tenant_id, contact_id)

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    items: list[ActivityItem] = []

    # Get calls with summaries
    if not channel or channel == "call":
        calls_stmt = (
            select(Call, CallSummary)
            .select_from(CallSummary)
            .join(Call, CallSummary.call_id == Call.id)
            .where(CallSummary.contact_id == contact_id)
            .order_by(Call.started_at.desc())
        )
        calls_result = await db.execute(calls_stmt)
        for call, summary in calls_result:
            duration_str = ""
            if call.duration:
                mins = call.duration // 60
                secs = call.duration % 60
                duration_str = f"{mins}m {secs}s"

            intent_label = summary.intent.replace("_", " ").title() if summary.intent else ""
            summary_text = f"{duration_str} - {intent_label}" if duration_str and intent_label else (duration_str or intent_label or "Voice call")

            items.append(ActivityItem(
                id=f"call-{call.id}",
                type="call",
                timestamp=call.started_at.isoformat() if call.started_at else "",
                summary=summary_text,
                details=ActivityItemDetails(
                    duration=call.duration,
                    intent=summary.intent,
                    outcome=summary.outcome,
                ),
            ))

    # Get conversations (SMS and web chat)
    if not channel or channel in ("sms", "chat"):
        if contact.lead_id:
            conv_stmt = (
                select(Conversation)
                .select_from(Lead)
                .join(Conversation, Lead.conversation_id == Conversation.id)
                .where(Lead.contact_id == contact_id)
            )
            if channel == "sms":
                conv_stmt = conv_stmt.where(Conversation.channel == "sms")
            elif channel == "chat":
                conv_stmt = conv_stmt.where(Conversation.channel == "web")

            conv_result = await db.execute(conv_stmt)
            for (conv,) in conv_result:
                # Get message count and preview
                msg_count_stmt = select(func.count()).where(
                    Message.conversation_id == conv.id,
                    Message.role != "system"
                )
                msg_count = (await db.execute(msg_count_stmt)).scalar() or 0

                # Get last message for preview
                last_msg_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conv.id, Message.role == "user")
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                last_msg_result = await db.execute(last_msg_stmt)
                last_msg = last_msg_result.scalar_one_or_none()

                preview = ""
                if last_msg and last_msg.content:
                    preview = last_msg.content[:100] + ("..." if len(last_msg.content) > 100 else "")

                conv_type = "sms" if conv.channel == "sms" else "chat"
                items.append(ActivityItem(
                    id=f"{conv_type}-{conv.id}",
                    type=conv_type,
                    timestamp=conv.updated_at.isoformat() if conv.updated_at else conv.created_at.isoformat(),
                    summary=preview or f"{msg_count} messages",
                    details=ActivityItemDetails(
                        channel=conv.channel,
                        message_count=msg_count,
                    ),
                ))

    # Get email conversations
    if not channel or channel == "email":
        email_stmt = (
            select(EmailConversation)
            .where(EmailConversation.contact_id == contact_id)
            .order_by(EmailConversation.updated_at.desc())
        )
        email_result = await db.execute(email_stmt)
        for (email_conv,) in email_result:
            items.append(ActivityItem(
                id=f"email-{email_conv.id}",
                type="email",
                timestamp=email_conv.last_response_at.isoformat() if email_conv.last_response_at else email_conv.created_at.isoformat(),
                summary=email_conv.subject or "(No subject)",
                details=ActivityItemDetails(
                    channel="email",
                    message_count=email_conv.message_count,
                    subject=email_conv.subject,
                ),
            ))

    # Sort all items by timestamp (most recent first)
    items.sort(key=lambda x: x.timestamp, reverse=True)

    # Calculate pagination
    total = len(items)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_items = items[start_idx:end_idx]
    has_more = end_idx < total

    return ActivityFeedResponse(
        items=paginated_items,
        total=total,
        page=page,
        has_more=has_more,
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
