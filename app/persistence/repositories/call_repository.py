"""Call repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.call import Call
from app.persistence.repositories.base import BaseRepository


class CallRepository(BaseRepository[Call]):
    """Repository for Call entities."""

    def __init__(self, session: AsyncSession):
        """Initialize call repository."""
        super().__init__(Call, session)

    async def get_by_call_sid(self, call_sid: str) -> Call | None:
        """Get call by Twilio call SID.
        
        Args:
            call_sid: Twilio call SID
            
        Returns:
            Call entity or None if not found
        """
        stmt = select(Call).where(Call.call_sid == call_sid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Call]:
        """List calls for a tenant.
        
        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Call entities
        """
        return await self.list(tenant_id=tenant_id, skip=skip, limit=limit)

