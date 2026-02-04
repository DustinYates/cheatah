"""Repository for tenant customer support configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_customer_support_config import TenantCustomerSupportConfig


class CustomerSupportConfigRepository:
    """Repository for tenant customer support configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tenant_id(
        self,
        tenant_id: int,
    ) -> TenantCustomerSupportConfig | None:
        """Get customer support config for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Config or None if not found
        """
        stmt = select(TenantCustomerSupportConfig).where(
            TenantCustomerSupportConfig.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        tenant_id: int,
        **kwargs,
    ) -> TenantCustomerSupportConfig:
        """Create or update customer support config.

        Args:
            tenant_id: Tenant ID
            **kwargs: Config fields to update

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

        config = TenantCustomerSupportConfig(tenant_id=tenant_id, **kwargs)
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def get_by_phone_number(
        self,
        phone_number: str,
    ) -> TenantCustomerSupportConfig | None:
        """Get config by support phone number.

        Used to route inbound calls/SMS to the correct tenant.

        Args:
            phone_number: Telnyx phone number (E.164)

        Returns:
            Config or None
        """
        stmt = select(TenantCustomerSupportConfig).where(
            TenantCustomerSupportConfig.telnyx_phone_number == phone_number,
            TenantCustomerSupportConfig.is_enabled == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
