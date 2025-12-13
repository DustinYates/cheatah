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

        # Collect all sections with their order values
        all_sections = []
        
        # Add global sections first (lower priority)
        if global_bundle:
            global_sections = await self.prompt_repo.get_sections(global_bundle.id)
            all_sections.extend(global_sections)
        
        # Add tenant sections (higher priority, will override global)
        if tenant_bundle:
            tenant_sections = await self.prompt_repo.get_sections(tenant_bundle.id)
            all_sections.extend(tenant_sections)

        # If no sections found, return default prompt
        if not all_sections:
            return (
                "You are a helpful customer service assistant. "
                "Be friendly, professional, and concise. "
                "Answer questions based on the business information provided."
            )
        
        # Build section map (tenant sections override global)
        section_map: dict[str, tuple[str, int]] = {}  # (content, order)
        for section in all_sections:
            section_map[section.section_key] = (section.content, section.order)
        
        # Sort sections by order, then by section_key for consistent ordering
        sorted_sections = sorted(
            section_map.items(),
            key=lambda x: (x[1][1], x[0])  # Sort by order, then by key
        )
        
        # Build prompt from ordered sections
        prompt_parts = [content for _, (content, _) in sorted_sections]
        
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

