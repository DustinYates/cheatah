"""Repository for TenantPromptConfig."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_prompt_config import TenantPromptConfig


class TenantPromptConfigRepository:
    """Repository for tenant prompt configurations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def get_by_tenant_id(self, tenant_id: int) -> Optional[TenantPromptConfig]:
        """Get the active prompt config for a tenant.

        Args:
            tenant_id: The tenant ID

        Returns:
            TenantPromptConfig if found and active, None otherwise
        """
        stmt = select(TenantPromptConfig).where(
            TenantPromptConfig.tenant_id == tenant_id,
            TenantPromptConfig.is_active == True,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, config_id: int) -> Optional[TenantPromptConfig]:
        """Get a prompt config by ID.

        Args:
            config_id: The config ID

        Returns:
            TenantPromptConfig if found, None otherwise
        """
        stmt = select(TenantPromptConfig).where(TenantPromptConfig.id == config_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        tenant_id: int,
        config_json: dict,
        schema_version: str = "bss_chatbot_prompt_v1",
        business_type: str = "bss",
    ) -> TenantPromptConfig:
        """Create a new tenant prompt config.

        Args:
            tenant_id: The tenant ID
            config_json: The JSON configuration
            schema_version: Schema version string
            business_type: Business type identifier

        Returns:
            Created TenantPromptConfig
        """
        config = TenantPromptConfig(
            tenant_id=tenant_id,
            config_json=config_json,
            schema_version=schema_version,
            business_type=business_type,
            validated_at=datetime.utcnow(),
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def update(
        self,
        config: TenantPromptConfig,
        config_json: dict,
        schema_version: Optional[str] = None,
        business_type: Optional[str] = None,
    ) -> TenantPromptConfig:
        """Update an existing tenant prompt config.

        Args:
            config: The config to update
            config_json: New JSON configuration
            schema_version: Optional new schema version
            business_type: Optional new business type

        Returns:
            Updated TenantPromptConfig
        """
        config.config_json = config_json
        config.validated_at = datetime.utcnow()

        if schema_version is not None:
            config.schema_version = schema_version
        if business_type is not None:
            config.business_type = business_type

        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def upsert(
        self,
        tenant_id: int,
        config_json: dict,
        schema_version: str = "bss_chatbot_prompt_v1",
        business_type: str = "bss",
    ) -> TenantPromptConfig:
        """Create or update tenant prompt config.

        Args:
            tenant_id: The tenant ID
            config_json: The JSON configuration
            schema_version: Schema version string
            business_type: Business type identifier

        Returns:
            Created or updated TenantPromptConfig
        """
        existing = await self.get_by_tenant_id(tenant_id)
        if existing:
            return await self.update(
                existing,
                config_json=config_json,
                schema_version=schema_version,
                business_type=business_type,
            )
        return await self.create(
            tenant_id=tenant_id,
            config_json=config_json,
            schema_version=schema_version,
            business_type=business_type,
        )

    async def deactivate(self, config: TenantPromptConfig) -> TenantPromptConfig:
        """Deactivate a prompt config.

        Args:
            config: The config to deactivate

        Returns:
            Deactivated TenantPromptConfig
        """
        config.is_active = False
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def delete(self, config: TenantPromptConfig) -> None:
        """Delete a prompt config.

        Args:
            config: The config to delete
        """
        await self.session.delete(config)
        await self.session.commit()
