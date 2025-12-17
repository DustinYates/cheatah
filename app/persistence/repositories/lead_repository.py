"""Lead repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.lead import Lead
from app.persistence.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    """Repository for Lead entities."""

    def __init__(self, session: AsyncSession):
        """Initialize lead repository."""
        super().__init__(Lead, session)

    async def get_by_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Lead | None:
        """Get lead by conversation ID.
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            
        Returns:
            Lead or None if not found
        """
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.conversation_id == conversation_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

