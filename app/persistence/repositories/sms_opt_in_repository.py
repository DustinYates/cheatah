"""SMS opt-in repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.sms_opt_in import SmsOptIn
from app.persistence.repositories.base import BaseRepository


class SmsOptInRepository(BaseRepository[SmsOptIn]):
    """Repository for SmsOptIn entities."""

    def __init__(self, session: AsyncSession):
        """Initialize SMS opt-in repository."""
        super().__init__(SmsOptIn, session)

    async def get_by_phone(
        self, tenant_id: int, phone_number: str
    ) -> SmsOptIn | None:
        """Get opt-in record by phone number.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            
        Returns:
            Opt-in record or None if not found
        """
        stmt = select(SmsOptIn).where(
            SmsOptIn.tenant_id == tenant_id,
            SmsOptIn.phone_number == phone_number
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

