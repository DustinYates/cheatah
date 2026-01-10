"""Prompt repository."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.prompt import PromptBundle, PromptChannel, PromptSection, PromptStatus
from app.persistence.repositories.base import BaseRepository


class PromptRepository(BaseRepository[PromptBundle]):
    """Repository for PromptBundle entities."""

    def __init__(self, session: AsyncSession):
        """Initialize prompt repository."""
        super().__init__(PromptBundle, session)

    async def get_active_bundle(
        self, tenant_id: int | None, channel: str = PromptChannel.CHAT.value
    ) -> PromptBundle | None:
        """Get the active prompt bundle for a tenant (or global if tenant_id is None)."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.channel == channel,
            PromptBundle.is_active == True
        ).order_by(PromptBundle.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_production_bundle(
        self, tenant_id: int | None, channel: str = PromptChannel.CHAT.value
    ) -> PromptBundle | None:
        """Get the production prompt bundle for a tenant."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.channel == channel,
            PromptBundle.status == PromptStatus.PRODUCTION.value
        ).order_by(PromptBundle.published_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_draft_bundle(
        self, tenant_id: int | None, channel: str = PromptChannel.CHAT.value
    ) -> PromptBundle | None:
        """Get the draft prompt bundle for a tenant."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.channel == channel,
            PromptBundle.status == PromptStatus.DRAFT.value
        ).order_by(PromptBundle.updated_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_global_base_bundle(self, channel: str = PromptChannel.CHAT.value) -> PromptBundle | None:
        """Get the global base prompt bundle (tenant_id is NULL)."""
        bundle = await self.get_production_bundle(None, channel)
        if bundle:
            return bundle
        return await self.get_active_bundle(None, channel)

    async def get_voice_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the voice-specific prompt bundle for a tenant.

        Falls back to chat bundle if no voice bundle exists.
        """
        # First try to get voice-specific bundle
        bundle = await self.get_production_bundle(tenant_id, PromptChannel.VOICE.value)
        if bundle:
            return bundle
        bundle = await self.get_active_bundle(tenant_id, PromptChannel.VOICE.value)
        if bundle:
            return bundle
        # Fall back to chat bundle if no voice bundle
        return None

    async def get_sections(self, bundle_id: int) -> list[PromptSection]:
        """Get all sections for a prompt bundle, ordered by order field."""
        stmt = (
            select(PromptSection)
            .where(PromptSection.bundle_id == bundle_id)
            .order_by(PromptSection.order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_all_bundles(
        self, tenant_id: int | None, channel: str = PromptChannel.CHAT.value
    ) -> None:
        """Deactivate all bundles for a tenant (or global) in a specific channel."""
        stmt = (
            select(PromptBundle)
            .where(
                PromptBundle.tenant_id == tenant_id,
                PromptBundle.channel == channel,
                PromptBundle.is_active == True
            )
        )
        result = await self.session.execute(stmt)
        bundles = result.scalars().all()
        for bundle in bundles:
            bundle.is_active = False
        await self.session.commit()

    async def publish_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Publish a bundle to production.

        Args:
            tenant_id: The tenant context (used for access control). If None (global admin),
                       the bundle's actual tenant_id is used for finding the old production bundle.
            bundle_id: The ID of the bundle to publish.

        Returns:
            The published bundle, or None if not found.
        """
        bundle = await self.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None

        # Use the bundle's actual tenant_id and channel to find/demote the old production bundle
        # This ensures we demote the correct tenant's old production prompt for the same channel,
        # not a global one when a global admin is operating
        actual_tenant_id = bundle.tenant_id
        actual_channel = bundle.channel
        old_prod = await self.get_production_bundle(actual_tenant_id, actual_channel)
        if old_prod and old_prod.id != bundle_id:
            old_prod.status = PromptStatus.DRAFT.value
            old_prod.is_active = False

        bundle.status = PromptStatus.PRODUCTION.value
        bundle.is_active = True
        bundle.published_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(bundle)
        return bundle

    async def set_testing(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Set a bundle to testing status."""
        bundle = await self.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None
        bundle.status = PromptStatus.TESTING.value
        await self.session.commit()
        await self.session.refresh(bundle)
        return bundle

    async def deactivate_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Deactivate a bundle (move from production to draft)."""
        bundle = await self.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None
        bundle.status = PromptStatus.DRAFT.value
        bundle.is_active = False
        await self.session.commit()
        await self.session.refresh(bundle)
        return bundle

