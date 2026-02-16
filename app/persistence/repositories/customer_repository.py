"""Repository for customer data."""

from datetime import datetime

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.customer import Customer
from app.persistence.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """Repository for verified customers."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Customer, session)

    async def get_by_phone(
        self,
        tenant_id: int,
        phone: str,
    ) -> Customer | None:
        """Get customer by phone number.

        Args:
            tenant_id: Tenant ID
            phone: Phone number (E.164 format)

        Returns:
            Customer or None if not found
        """
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.phone == phone,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self,
        tenant_id: int,
        external_customer_id: str,
    ) -> Customer | None:
        """Get customer by external CRM ID (e.g., Jackrabbit ID).

        Args:
            tenant_id: Tenant ID
            external_customer_id: External customer ID

        Returns:
            Customer or None if not found
        """
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.external_customer_id == external_customer_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(
        self,
        tenant_id: int,
        email: str,
    ) -> Customer | None:
        """Get customer by email.

        Args:
            tenant_id: Tenant ID
            email: Email address

        Returns:
            Customer or None if not found
        """
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            func.lower(Customer.email) == email.lower(),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        tenant_id: int,
        query: str,
        limit: int = 50,
    ) -> list[Customer]:
        """Search customers by name, email, or phone.

        Args:
            tenant_id: Tenant ID
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching customers
        """
        search_pattern = f"%{query}%"
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            or_(
                Customer.name.ilike(search_pattern),
                Customer.email.ilike(search_pattern),
                Customer.phone.ilike(search_pattern),
            ),
        ).order_by(Customer.name).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(
        self,
        tenant_id: int,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Customer]:
        """List customers by status.

        Args:
            tenant_id: Tenant ID
            status: Status filter (active, inactive, suspended)
            skip: Pagination offset
            limit: Maximum results to return

        Returns:
            List of customers
        """
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.status == status,
        ).order_by(Customer.updated_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_from_jackrabbit(
        self,
        tenant_id: int,
        external_customer_id: str,
        phone: str,
        name: str | None = None,
        email: str | None = None,
        account_data: dict | None = None,
        jackrabbit_customer_id: int | None = None,
        status: str | None = None,
    ) -> Customer:
        """Create or update customer from Jackrabbit sync.

        Args:
            tenant_id: Tenant ID
            external_customer_id: Jackrabbit customer ID
            phone: Phone number (E.164)
            name: Customer name
            email: Email address
            account_data: Account details JSON
            jackrabbit_customer_id: FK to jackrabbit_customers table
            status: Account status from Jackrabbit (active/inactive)

        Returns:
            Created or updated customer
        """
        resolved_status = (status or "active").lower().strip()
        if resolved_status not in ("active", "inactive", "suspended"):
            resolved_status = "active"

        # Try to find by external_customer_id first
        existing = await self.get_by_external_id(tenant_id, external_customer_id)

        if existing:
            existing.phone = phone
            existing.name = name
            existing.email = email
            existing.account_data = account_data
            existing.jackrabbit_customer_id = jackrabbit_customer_id
            existing.status = resolved_status
            existing.last_synced_at = datetime.utcnow()
            existing.sync_source = "jackrabbit"
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        customer = Customer(
            tenant_id=tenant_id,
            external_customer_id=external_customer_id,
            phone=phone,
            name=name,
            email=email,
            account_data=account_data,
            jackrabbit_customer_id=jackrabbit_customer_id,
            last_synced_at=datetime.utcnow(),
            sync_source="jackrabbit",
            status=resolved_status,
        )
        self.session.add(customer)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def get_count(self, tenant_id: int, status: str | None = None) -> int:
        """Get count of customers for a tenant.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter

        Returns:
            Count of customers
        """
        stmt = select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Customer.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_needs_sync(
        self,
        tenant_id: int,
        stale_hours: int = 24,
        limit: int = 100,
    ) -> list[Customer]:
        """Get customers that need to be re-synced.

        Args:
            tenant_id: Tenant ID
            stale_hours: Consider stale if last_synced_at older than this
            limit: Maximum results

        Returns:
            List of customers needing sync
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=stale_hours)

        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.sync_source == "jackrabbit",
            or_(
                Customer.last_synced_at.is_(None),
                Customer.last_synced_at < cutoff,
            ),
        ).order_by(Customer.last_synced_at.nulls_first()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
