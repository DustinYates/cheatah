"""Conversation repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation entities."""

    def __init__(self, session: AsyncSession):
        """Initialize conversation repository."""
        super().__init__(Conversation, session)

    async def get_by_id_with_messages(
        self, tenant_id: int, conversation_id: int
    ) -> Conversation | None:
        """Get conversation by ID with messages eagerly loaded.
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            
        Returns:
            Conversation with messages or None if not found
        """
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self, tenant_id: int, external_id: str
    ) -> Conversation | None:
        """Get conversation by external_id (for idempotency)."""
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.external_id == external_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone_number(
        self, tenant_id: int, phone_number: str, channel: str = "sms"
    ) -> Conversation | None:
        """Get conversation by phone number and channel.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            channel: Channel type (default: "sms")
            
        Returns:
            Conversation or None if not found
        """
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.phone_number == phone_number,
            Conversation.channel == channel
        ).order_by(Conversation.updated_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_channel(
        self, tenant_id: int, channel: str, skip: int = 0, limit: int = 100
    ) -> list[Conversation]:
        """List conversations by channel.
        
        Args:
            tenant_id: Tenant ID
            channel: Channel type
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of conversations
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.channel == channel
            )
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Conversation]:
        """List all conversations for tenant, ordered by updated_at.
        
        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of conversations
        """
        stmt = (
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
