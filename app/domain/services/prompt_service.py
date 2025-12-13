"""Prompt service for managing prompt bundles and composition."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.prompt import PromptBundle, PromptSection
from app.persistence.repositories.prompt_repository import PromptRepository


class PromptService:
    """Service for prompt bundle management and composition."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize prompt service."""
        self.session = session
        self.prompt_repo = PromptRepository(session)

    async def get_active_bundle(self, tenant_id: int | None) -> PromptBundle | None:
        """Get the active prompt bundle for a tenant.

        Args:
            tenant_id: Tenant ID (None for global)

        Returns:
            Active prompt bundle or None
        """
        return await self.prompt_repo.get_active_bundle(tenant_id)

    async def compose_prompt(
        self, tenant_id: int | None, context: dict | None = None
    ) -> str:
        """Compose final prompt from global base + tenant overrides.

        Args:
            tenant_id: Tenant ID (None for global)
            context: Optional context for prompt composition

        Returns:
            Composed prompt string
        """
        # Get global base bundle
        global_bundle = await self.prompt_repo.get_global_base_bundle()
        
        # Get tenant-specific bundle if tenant_id is provided
        tenant_bundle = None
        if tenant_id is not None:
            tenant_bundle = await self.prompt_repo.get_active_bundle(tenant_id)

        # Build section map from global bundle
        section_map: dict[str, str] = {}
        if global_bundle:
            global_sections = await self.prompt_repo.get_sections(global_bundle.id)
            for section in global_sections:
                section_map[section.section_key] = section.content

        # Override with tenant-specific sections if they exist
        if tenant_bundle:
            tenant_sections = await self.prompt_repo.get_sections(tenant_bundle.id)
            for section in tenant_sections:
                section_map[section.section_key] = section.content

        # Compose final prompt from sections
        # Order sections by their order field (if available) or alphabetically
        sorted_keys = sorted(section_map.keys())
        prompt_parts = [section_map[key] for key in sorted_keys]
        
        return "\n\n".join(prompt_parts)

    async def activate_bundle(
        self, tenant_id: int | None, bundle_id: int
    ) -> PromptBundle | None:
        """Activate a prompt bundle (deactivates others).

        Args:
            tenant_id: Tenant ID (None for global)
            bundle_id: Bundle ID to activate

        Returns:
            Activated bundle or None if not found
        """
        # Get bundle
        bundle = await self.prompt_repo.get_by_id(tenant_id, bundle_id)
        if not bundle:
            return None

        # Deactivate all other bundles for this tenant
        await self.prompt_repo.deactivate_all_bundles(tenant_id)

        # Activate this bundle
        bundle.is_active = True
        await self.session.commit()
        await self.session.refresh(bundle)
        return bundle

