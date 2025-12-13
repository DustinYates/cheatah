"""Prompt repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.prompt import PromptBundle, PromptSection
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

    async def get_global_base_bundle(self) -> PromptBundle | None:
        """Get the global base prompt bundle (tenant_id is NULL)."""
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

