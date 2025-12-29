"""Repository for cached Jackrabbit customer data."""

from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.repositories.base import BaseRepository


class JackrabbitCustomerRepository(BaseRepository[JackrabbitCustomer]):
    """Repository for Jackrabbit customer cache."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(JackrabbitCustomer, session)

    async def get_by_phone(
        self,
        tenant_id: int,
        phone_number: str,
    ) -> JackrabbitCustomer | None:
        """Get customer by phone number.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number (normalized)

        Returns:
            Customer or None if not found
        """
        stmt = select(JackrabbitCustomer).where(
            JackrabbitCustomer.tenant_id == tenant_id,
            JackrabbitCustomer.phone_number == phone_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_jackrabbit_id(
        self,
        tenant_id: int,
        jackrabbit_id: str,
    ) -> JackrabbitCustomer | None:
        """Get customer by Jackrabbit ID.

        Args:
            tenant_id: Tenant ID
            jackrabbit_id: Jackrabbit customer ID

        Returns:
            Customer or None if not found
        """
        stmt = select(JackrabbitCustomer).where(
            JackrabbitCustomer.tenant_id == tenant_id,
            JackrabbitCustomer.jackrabbit_id == jackrabbit_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        tenant_id: int,
        jackrabbit_id: str,
        phone_number: str,
        email: str | None = None,
        name: str | None = None,
        customer_data: dict | None = None,
        cache_expires_at: datetime | None = None,
    ) -> JackrabbitCustomer:
        """Create or update cached customer record.

        Args:
            tenant_id: Tenant ID
            jackrabbit_id: Jackrabbit customer ID
            phone_number: Phone number
            email: Optional email
            name: Optional customer name
            customer_data: Full Jackrabbit record as JSON
            cache_expires_at: Optional cache expiration

        Returns:
            Created or updated customer
        """
        # Try to find by jackrabbit_id first
        existing = await self.get_by_jackrabbit_id(tenant_id, jackrabbit_id)

        if existing:
            existing.phone_number = phone_number
            existing.email = email
            existing.name = name
            existing.customer_data = customer_data
            existing.last_synced_at = datetime.utcnow()
            existing.cache_expires_at = cache_expires_at
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        customer = JackrabbitCustomer(
            tenant_id=tenant_id,
            jackrabbit_id=jackrabbit_id,
            phone_number=phone_number,
            email=email,
            name=name,
            customer_data=customer_data,
            last_synced_at=datetime.utcnow(),
            cache_expires_at=cache_expires_at,
        )
        self.session.add(customer)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def invalidate_by_phone(
        self,
        tenant_id: int,
        phone_number: str,
    ) -> bool:
        """Invalidate (delete) cached customer by phone.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number

        Returns:
            True if customer was deleted
        """
        customer = await self.get_by_phone(tenant_id, phone_number)
        if not customer:
            return False

        await self.session.delete(customer)
        await self.session.commit()
        return True

    async def invalidate_by_jackrabbit_id(
        self,
        tenant_id: int,
        jackrabbit_id: str,
    ) -> bool:
        """Invalidate (delete) cached customer by Jackrabbit ID.

        Args:
            tenant_id: Tenant ID
            jackrabbit_id: Jackrabbit customer ID

        Returns:
            True if customer was deleted
        """
        customer = await self.get_by_jackrabbit_id(tenant_id, jackrabbit_id)
        if not customer:
            return False

        await self.session.delete(customer)
        await self.session.commit()
        return True

    async def get_expired_cache_entries(
        self,
        tenant_id: int | None = None,
        limit: int = 100,
    ) -> list[JackrabbitCustomer]:
        """Get expired cache entries for cleanup.

        Args:
            tenant_id: Optional tenant filter
            limit: Maximum entries to return

        Returns:
            List of expired customers
        """
        now = datetime.utcnow()
        stmt = select(JackrabbitCustomer).where(
            JackrabbitCustomer.cache_expires_at.isnot(None),
            JackrabbitCustomer.cache_expires_at < now,
        )

        if tenant_id is not None:
            stmt = stmt.where(JackrabbitCustomer.tenant_id == tenant_id)

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_cache_valid(
        self,
        tenant_id: int,
        phone_number: str,
    ) -> bool:
        """Check if cached customer data is still valid (not expired).

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number

        Returns:
            True if cache is valid (exists and not expired)
        """
        customer = await self.get_by_phone(tenant_id, phone_number)
        if not customer:
            return False

        if customer.cache_expires_at and customer.cache_expires_at < datetime.utcnow():
            return False

        return True
