"""Lead repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.persistence.models.lead import Lead
from app.persistence.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    """Repository for Lead entities."""

    def __init__(self, session: AsyncSession):
        """Initialize lead repository."""
        super().__init__(Lead, session)

    async def list(
        self,
        tenant_id: int | None,
        skip: int = 0,
        limit: int = 100,
        **filters
    ) -> list[Lead]:
        """List leads sorted by most recent activity (updated_at).

        Overrides base list to sort by updated_at instead of created_at.
        """
        stmt = select(Lead)

        if tenant_id is not None:
            stmt = stmt.where(Lead.tenant_id == tenant_id)

        for key, value in filters.items():
            if hasattr(Lead, key):
                stmt = stmt.where(getattr(Lead, key) == value)

        # Sort by updated_at (most recent activity) then created_at
        # Fallback to created_at if updated_at column doesn't exist yet
        if hasattr(Lead, 'updated_at') and Lead.updated_at is not None:
            stmt = stmt.order_by(Lead.updated_at.desc(), Lead.created_at.desc())
        else:
            stmt = stmt.order_by(Lead.created_at.desc())
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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

