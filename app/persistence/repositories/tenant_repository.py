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

    async def get_by_subdomain(self, subdomain: str) -> Tenant | None:
        """Get tenant by subdomain."""
        stmt = select(Tenant).where(Tenant.subdomain == subdomain)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[Tenant]:
        """List all tenants (for global admin)."""
        stmt = select(Tenant).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

