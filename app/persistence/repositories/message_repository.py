"""Message repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.conversation import Message
from app.persistence.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository for Message entities."""

    def __init__(self, session: AsyncSession):
        """Initialize message repository."""
        super().__init__(Message, session)

    async def get_by_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> list[Message]:
        """Get all messages for a conversation, ordered by sequence_number."""
        from app.persistence.models.conversation import Conversation
        # Join with conversation to ensure tenant isolation
        stmt = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.tenant_id == tenant_id
            )
            .order_by(Message.sequence_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_sequence_number(
        self, tenant_id: int, conversation_id: int
    ) -> int:
        """Get the next sequence number for a conversation."""
        messages = await self.get_by_conversation(tenant_id, conversation_id)
        if not messages:
            return 1
        return max(msg.sequence_number for msg in messages) + 1

