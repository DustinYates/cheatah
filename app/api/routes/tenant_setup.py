"""Tenant setup routes for configuring prompts and FAQs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_tenant_admin
from app.domain.services.prompt_service import PromptService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class PromptSectionData(BaseModel):
    """Prompt section data."""

    section_key: str  # e.g., "system", "business_info", "faq", "rules"
    content: str
    order: int = 0


class TenantPromptSetup(BaseModel):
    """Tenant prompt setup request."""

    name: str = "Default Prompt Bundle"
    business_prompt: str  # Main business description and instructions
    faq: str | None = None  # FAQ section
    rules: str | None = None  # Rules and guidelines
    additional_sections: list[PromptSectionData] | None = None


class TenantPromptSetupResponse(BaseModel):
    """Tenant prompt setup response."""

    bundle_id: int
    message: str


@router.post("/setup-prompt", response_model=TenantPromptSetupResponse)
async def setup_tenant_prompt(
    setup_data: TenantPromptSetup,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantPromptSetupResponse:
    """Set up tenant prompt bundle with business info, FAQs, and rules.
    
    This endpoint allows tenant admins to:
    - Set their business description and instructions
    - Add FAQ content
    - Add rules and guidelines
    - Create additional custom sections
    
    The prompt bundle will be automatically activated.
    """
    from app.persistence.models.prompt import PromptBundle, PromptSection
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    current_user, tenant_id = admin_data
    prompt_service = PromptService(db)
    prompt_repo = PromptRepository(db)
    
    # Create prompt bundle
    bundle = await prompt_repo.create(
        tenant_id,
        name=setup_data.name,
        version="1.0.0",
        is_active=False,  # Will activate after adding sections
    )
    
    # Create sections
    sections = []
    
    # System/base prompt (always first)
    sections.append(PromptSection(
        bundle_id=bundle.id,
        section_key="system",
        content="You are a helpful customer service assistant. Be friendly, professional, and concise.",
        order=0,
    ))
    
    # Business prompt
    sections.append(PromptSection(
        bundle_id=bundle.id,
        section_key="business_info",
        content=setup_data.business_prompt,
        order=1,
    ))
    
    # FAQ section (if provided)
    if setup_data.faq:
        sections.append(PromptSection(
            bundle_id=bundle.id,
            section_key="faq",
            content=f"Frequently Asked Questions:\n\n{setup_data.faq}",
            order=2,
        ))
    
    # Rules section (if provided)
    if setup_data.rules:
        sections.append(PromptSection(
            bundle_id=bundle.id,
            section_key="rules",
            content=f"Rules and Guidelines:\n\n{setup_data.rules}",
            order=3,
        ))
    
    # Additional sections
    if setup_data.additional_sections:
        for section_data in setup_data.additional_sections:
            sections.append(PromptSection(
                bundle_id=bundle.id,
                section_key=section_data.section_key,
                content=section_data.content,
                order=section_data.order if section_data.order > 0 else 4,
            ))
    
    # Add all sections to database
    for section in sections:
        db.add(section)
    
    await db.commit()
    
    # Activate the bundle
    activated_bundle = await prompt_service.activate_bundle(tenant_id, bundle.id)
    
    if not activated_bundle:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate prompt bundle",
        )
    
    return TenantPromptSetupResponse(
        bundle_id=activated_bundle.id,
        message="Prompt bundle created and activated successfully",
    )


@router.get("/current-prompt")
async def get_current_tenant_prompt(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get the current active prompt for the tenant (composed)."""
    current_user, tenant_id = admin_data
    prompt_service = PromptService(db)
    prompt = await prompt_service.compose_prompt(tenant_id)
    
    return {
        "prompt": prompt,
        "tenant_id": tenant_id,
    }

