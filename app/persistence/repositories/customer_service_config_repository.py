"""Repository for customer service configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig
from app.persistence.repositories.base import BaseRepository


class CustomerServiceConfigRepository(BaseRepository[TenantCustomerServiceConfig]):
    """Repository for tenant customer service configuration."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantCustomerServiceConfig, session)

    async def get_by_tenant_id(self, tenant_id: int) -> TenantCustomerServiceConfig | None:
        """Get customer service config for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Config or None if not found
        """
        stmt = select(TenantCustomerServiceConfig).where(
            TenantCustomerServiceConfig.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        tenant_id: int,
        **kwargs,
    ) -> TenantCustomerServiceConfig:
        """Create or update customer service config for a tenant.

        Args:
            tenant_id: Tenant ID
            **kwargs: Config fields to set

        Returns:
            Created or updated config
        """
        existing = await self.get_by_tenant_id(tenant_id)

        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        config = TenantCustomerServiceConfig(tenant_id=tenant_id, **kwargs)
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def is_enabled_for_tenant(self, tenant_id: int) -> bool:
        """Check if customer service is enabled for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if enabled
        """
        config = await self.get_by_tenant_id(tenant_id)
        return config is not None and config.is_enabled
