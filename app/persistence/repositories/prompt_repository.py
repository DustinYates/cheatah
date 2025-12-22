"""Prompt repository."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus
from app.persistence.repositories.base import BaseRepository


class PromptRepository(BaseRepository[PromptBundle]):
    """Repository for PromptBundle entities."""

    def __init__(self, session: AsyncSession):
        """Initialize prompt repository."""
        super().__init__(PromptBundle, session)

    async def get_active_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the active prompt bundle for a tenant (or global if tenant_id is None)."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.is_active == True
        ).order_by(PromptBundle.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_production_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the production prompt bundle for a tenant."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.status == PromptStatus.PRODUCTION.value
        ).order_by(PromptBundle.published_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_draft_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the draft prompt bundle for a tenant."""
        stmt = select(PromptBundle).where(
            PromptBundle.tenant_id == tenant_id,
            PromptBundle.status == PromptStatus.DRAFT.value
        ).order_by(PromptBundle.updated_at.desc())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_global_base_bundle(self) -> PromptBundle | None:
        """Get the global base prompt bundle (tenant_id is NULL)."""
        bundle = await self.get_production_bundle(None)
        if bundle:
            return bundle
        return await self.get_active_bundle(None)

    async def get_sections(self, bundle_id: int) -> list[PromptSection]:
        """Get all sections for a prompt bundle, ordered by order field."""
        stmt = (
            select(PromptSection)
            .where(PromptSection.bundle_id == bundle_id)
            .order_by(PromptSection.order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_all_bundles(self, tenant_id: int | None) -> None:
        """Deactivate all bundles for a tenant (or global)."""
        stmt = (
            select(PromptBundle)
            .where(
                PromptBundle.tenant_id == tenant_id,
                PromptBundle.is_active == True
            )
        )
        result = await self.session.execute(stmt)
        bundles = result.scalars().all()
        for bundle in bundles:
            bundle.is_active = False
        await self.session.commit()

    async def publish_bundle(self, tenant_id: int | None, bundle_id: int) -> PromptBundle | None:
        """Publish a bundle to production."""
        bundle = await self.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None

        old_prod = await self.get_production_bundle(tenant_id)
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

