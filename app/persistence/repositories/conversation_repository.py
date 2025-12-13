"""Conversation repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.conversation import Conversation
from app.persistence.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation entities."""

    def __init__(self, session: AsyncSession):
        """Initialize conversation repository."""
        super().__init__(Conversation, session)

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

