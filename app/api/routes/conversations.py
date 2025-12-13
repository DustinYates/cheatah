"""Conversation routes for conversation and message management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.conversation_service import ConversationService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class ConversationCreate(BaseModel):
    """Conversation creation request."""

    channel: str
    external_id: str | None = None


class ConversationResponse(BaseModel):
    """Conversation response."""

    id: int
    tenant_id: int
    channel: str
    external_id: str | None
    phone_number: str | None = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    """Message creation request."""

    role: str
    content: str


class MessageResponse(BaseModel):
    """Message response."""

    id: int
    conversation_id: int
    role: str
    content: str
    sequence_number: int
    created_at: str

    class Config:
        from_attributes = True


class ConversationWithMessagesResponse(BaseModel):
    """Conversation with messages response."""

    id: int
    tenant_id: int
    channel: str
    external_id: str | None
    phone_number: str | None = None
    created_at: str
    updated_at: str
    messages: list[MessageResponse]

    class Config:
        from_attributes = True


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationResponse:
    """Create a new conversation."""
    conversation_service = ConversationService(db)
    conversation = await conversation_service.create_conversation(
        tenant_id,
        conversation_data.channel,
        conversation_data.external_id,
    )
    
    return ConversationResponse(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        channel=conversation.channel,
        external_id=conversation.external_id,
        phone_number=conversation.phone_number,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    channel: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ConversationResponse]:
    """List conversations for the tenant.

    Args:
        current_user: Current authenticated user
        tenant_id: Tenant ID
        db: Database session
        channel: Optional channel filter (web, sms, voice)
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of conversations
    """
    from app.persistence.repositories.conversation_repository import ConversationRepository
    conversation_repo = ConversationRepository(db)
    
    # Filter by channel if specified
    if channel:
        conversations = await conversation_repo.list_by_channel(tenant_id, channel, skip=skip, limit=limit)
    else:
        conversations = await conversation_repo.list_all(tenant_id, skip=skip, limit=limit)
    
    return [
        ConversationResponse(
            id=conv.id,
            tenant_id=conv.tenant_id,
            channel=conv.channel,
            external_id=conv.external_id,
            created_at=conv.created_at.isoformat(),
            updated_at=conv.updated_at.isoformat(),
        )
        for conv in conversations
    ]


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationWithMessagesResponse:
    """Get a conversation with its messages."""
    conversation_service = ConversationService(db)
    conversation = await conversation_service.get_conversation(tenant_id, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    messages = await conversation_service.get_conversation_history(tenant_id, conversation_id)
    
    return ConversationWithMessagesResponse(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        channel=conversation.channel,
        external_id=conversation.external_id,
        phone_number=conversation.phone_number,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        messages=[
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                sequence_number=msg.sequence_number,
                created_at=msg.created_at.isoformat(),
            )
            for msg in messages
        ],
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def add_message(
    conversation_id: int,
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Add a message to a conversation."""
    conversation_service = ConversationService(db)
    try:
        message = await conversation_service.add_message(
            tenant_id,
            conversation_id,
            message_data.role,
            message_data.content,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        sequence_number=message.sequence_number,
        created_at=message.created_at.isoformat(),
    )

