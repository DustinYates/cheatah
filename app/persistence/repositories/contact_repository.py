"""Contact repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.persistence.models.contact import Contact
from app.persistence.repositories.base import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    """Repository for Contact entities."""

    def __init__(self, session: AsyncSession):
        """Initialize contact repository."""
        super().__init__(Contact, session)

    async def get_by_email_or_phone(
        self, tenant_id: int, email: str | None = None, phone: str | None = None
    ) -> Contact | None:
        """Get contact by email or phone.
        
        Args:
            tenant_id: Tenant ID
            email: Optional email to search
            phone: Optional phone to search
            
        Returns:
            Contact or None if not found
        """
        if not email and not phone:
            return None
            
        conditions = []
        if email:
            conditions.append(Contact.email == email)
        if phone:
            conditions.append(Contact.phone == phone)
        
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            or_(*conditions)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Contact]:
        """List contacts for a tenant, ordered by created_at descending.
        
        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of contacts
        """
        stmt = (
            select(Contact)
            .where(Contact.tenant_id == tenant_id)
            .order_by(Contact.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

