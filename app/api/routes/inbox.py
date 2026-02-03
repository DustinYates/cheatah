"""Inbox routes for unified conversation management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_admin, require_tenant_context
from app.domain.services.inbox_service import InboxService
from app.persistence.database import get_db
from app.persistence.models.tenant import User

router = APIRouter()


# --- Schemas ---


class InboxConversationItem(BaseModel):
    """Summary item for inbox conversation list."""

    id: int
    tenant_id: int
    channel: str
    status: str
    phone_number: str | None = None
    contact_id: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    last_message_content: str | None = None
    last_message_role: str | None = None
    last_message_at: str | None = None
    pending_escalations: int = 0
    created_at: str
    updated_at: str


class InboxListResponse(BaseModel):
    """Paginated inbox conversation list."""

    conversations: list[InboxConversationItem]
    total: int


class InboxMessageItem(BaseModel):
    """Message item within a conversation detail."""

    id: int
    conversation_id: int
    role: str
    content: str
    sequence_number: int
    metadata: dict | None = None
    created_at: str | None = None


class InboxEscalationItem(BaseModel):
    """Escalation item within a conversation detail."""

    id: int
    reason: str | None = None
    status: str | None = None
    trigger_message: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None
    resolution_notes: str | None = None


class InboxContactInfo(BaseModel):
    """Contact info for conversation detail header."""

    id: int
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class InboxConversationDetail(BaseModel):
    """Full conversation detail with messages and escalations."""

    id: int
    tenant_id: int
    channel: str
    status: str
    phone_number: str | None = None
    contact: InboxContactInfo | None = None
    messages: list[InboxMessageItem]
    escalations: list[InboxEscalationItem]
    created_at: str | None = None
    updated_at: str | None = None


class InboxReplyRequest(BaseModel):
    """Request body for sending a human reply."""

    content: str


class InboxResolveEscalationRequest(BaseModel):
    """Request body for resolving an escalation."""

    notes: str | None = None


# --- Endpoints ---


@router.get("/conversations", response_model=InboxListResponse)
async def list_inbox_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    channel: str | None = Query(None, description="Filter by channel: web, sms, voice"),
    conv_status: str | None = Query(None, alias="status", description="Filter by status: open, resolved"),
    search: str | None = Query(None, description="Search contact name, phone, or email"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> InboxListResponse:
    """List conversations for the inbox with contact info and last message preview."""
    inbox_service = InboxService(db)
    result = await inbox_service.list_conversations(
        tenant_id=tenant_id,
        channel=channel,
        status=conv_status,
        search=search,
        skip=skip,
        limit=limit,
    )

    conversations = []
    for conv in result["conversations"]:
        last_message_at = conv.get("last_message_at")
        if last_message_at and hasattr(last_message_at, "isoformat"):
            last_message_at = last_message_at.isoformat()

        created_at = conv.get("created_at")
        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        updated_at = conv.get("updated_at")
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        conversations.append(
            InboxConversationItem(
                id=conv["id"],
                tenant_id=conv["tenant_id"],
                channel=conv["channel"],
                status=conv["status"],
                phone_number=conv.get("phone_number"),
                contact_id=conv.get("contact_id"),
                contact_name=conv.get("contact_name"),
                contact_phone=conv.get("contact_phone"),
                contact_email=conv.get("contact_email"),
                last_message_content=conv.get("last_message_content"),
                last_message_role=conv.get("last_message_role"),
                last_message_at=last_message_at,
                pending_escalations=conv.get("pending_escalations", 0),
                created_at=created_at or "",
                updated_at=updated_at or "",
            )
        )

    return InboxListResponse(conversations=conversations, total=result["total"])


@router.get("/conversations/{conversation_id}", response_model=InboxConversationDetail)
async def get_inbox_conversation(
    conversation_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InboxConversationDetail:
    """Get full conversation detail with messages, contact, and escalations."""
    inbox_service = InboxService(db)
    detail = await inbox_service.get_conversation_detail(tenant_id, conversation_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return InboxConversationDetail(**detail)


@router.post("/conversations/{conversation_id}/reply", response_model=InboxMessageItem)
async def reply_to_conversation(
    conversation_id: int,
    request: InboxReplyRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InboxMessageItem:
    """Send a human reply to an SMS or web chat conversation."""
    current_user, tenant_id = admin_data

    if not request.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reply content cannot be empty",
        )

    inbox_service = InboxService(db)
    try:
        message = await inbox_service.reply_to_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            content=request.content.strip(),
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return InboxMessageItem(**message)


@router.post("/conversations/{conversation_id}/resolve")
async def resolve_conversation(
    conversation_id: int,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark a conversation as resolved."""
    _, tenant_id = admin_data
    inbox_service = InboxService(db)
    try:
        return await inbox_service.resolve_conversation(tenant_id, conversation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/conversations/{conversation_id}/reopen")
async def reopen_conversation(
    conversation_id: int,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Reopen a resolved conversation."""
    _, tenant_id = admin_data
    inbox_service = InboxService(db)
    try:
        return await inbox_service.reopen_conversation(tenant_id, conversation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: int,
    request: InboxResolveEscalationRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Resolve a pending escalation from the inbox."""
    current_user, tenant_id = admin_data
    inbox_service = InboxService(db)
    try:
        return await inbox_service.resolve_escalation(
            tenant_id=tenant_id,
            escalation_id=escalation_id,
            user_id=current_user.id,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
