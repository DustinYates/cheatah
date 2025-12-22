"""Lead repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

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

    async def find_leads_with_conversation_by_email_or_phone(
        self, tenant_id: int, email: str | None = None, phone: str | None = None
    ) -> list[Lead]:
        """Find leads with conversations that match email or phone.
        
        Args:
            tenant_id: Tenant ID
            email: Optional email to match
            phone: Optional phone to match
            
        Returns:
            List of leads with conversation_id, ordered by created_at desc
        """
        if not email and not phone:
            return []
        
        conditions = []
        if email:
            conditions.append(Lead.email == email)
        if phone:
            conditions.append(Lead.phone == phone)
        
        stmt = (
            select(Lead)
            .where(
                Lead.tenant_id == tenant_id,
                Lead.conversation_id.isnot(None),
                or_(*conditions)
            )
            .order_by(Lead.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

