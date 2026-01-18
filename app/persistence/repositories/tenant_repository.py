"""Tenant repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.tenant import Tenant
from app.persistence.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    """Repository for Tenant entities."""

    def __init__(self, session: AsyncSession):
        """Initialize tenant repository."""
        super().__init__(Tenant, session)

    async def get_by_id_active(self, tenant_id: int) -> Tenant | None:
        """Get tenant by ID, only if active and not deleted.

        Use this for validating tenant access in requests.
        """
        stmt = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.is_active == True,
            Tenant.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_subdomain(self, subdomain: str, include_inactive: bool = False) -> Tenant | None:
        """Get tenant by subdomain.

        Args:
            subdomain: The tenant subdomain
            include_inactive: If True, return tenant even if inactive/deleted
        """
        stmt = select(Tenant).where(Tenant.subdomain == subdomain)
        if not include_inactive:
            stmt = stmt.where(
                Tenant.is_active == True,
                Tenant.deleted_at.is_(None)
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
        include_deleted: bool = False
    ) -> list[Tenant]:
        """List all tenants (for global admin).

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            include_inactive: If True, include inactive tenants
            include_deleted: If True, include soft-deleted tenants
        """
        stmt = select(Tenant)

        if not include_inactive:
            stmt = stmt.where(Tenant.is_active == True)
        if not include_deleted:
            stmt = stmt.where(Tenant.deleted_at.is_(None))

        stmt = stmt.order_by(Tenant.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, tenant_id: int, deleted_by_user_id: int) -> Tenant | None:
        """Soft delete a tenant.

        Args:
            tenant_id: The tenant to delete
            deleted_by_user_id: The user performing the deletion

        Returns:
            The updated tenant or None if not found
        """
        from datetime import datetime

        stmt = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()

        if tenant is None:
            return None

        tenant.deleted_at = datetime.utcnow()
        tenant.deleted_by = deleted_by_user_id
        tenant.is_active = False

        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

