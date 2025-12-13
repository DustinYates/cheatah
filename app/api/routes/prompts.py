"""Prompt routes for prompt bundle management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_tenant, get_current_user
from app.domain.services.prompt_service import PromptService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class PromptSectionCreate(BaseModel):
    """Prompt section creation request."""

    section_key: str
    content: str
    order: int = 0


class PromptBundleCreate(BaseModel):
    """Prompt bundle creation request."""

    name: str
    version: str = "1.0.0"
    sections: list[PromptSectionCreate]


class PromptBundleResponse(BaseModel):
    """Prompt bundle response."""

    id: int
    tenant_id: int | None
    name: str
    version: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class PromptComposeResponse(BaseModel):
    """Composed prompt response."""

    prompt: str


@router.post("/bundles", response_model=PromptBundleResponse)
async def create_prompt_bundle(
    bundle_data: PromptBundleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleResponse:
    """Create a new prompt bundle."""
    from app.persistence.models.prompt import PromptBundle, PromptSection
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_repo = PromptRepository(db)
    bundle = await prompt_repo.create(
        tenant_id,
        name=bundle_data.name,
        version=bundle_data.version,
        is_active=False,
    )
    
    # Create sections
    for section_data in bundle_data.sections:
        section = PromptSection(
            bundle_id=bundle.id,
            section_key=section_data.section_key,
            content=section_data.content,
            order=section_data.order,
        )
        db.add(section)
    
    await db.commit()
    await db.refresh(bundle)
    
    return PromptBundleResponse(
        id=bundle.id,
        tenant_id=bundle.tenant_id,
        name=bundle.name,
        version=bundle.version,
        is_active=bundle.is_active,
        created_at=bundle.created_at.isoformat(),
    )


@router.get("/bundles", response_model=list[PromptBundleResponse])
async def list_prompt_bundles(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> list[PromptBundleResponse]:
    """List prompt bundles."""
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_repo = PromptRepository(db)
    bundles = await prompt_repo.list(tenant_id, skip=skip, limit=limit)
    
    return [
        PromptBundleResponse(
            id=b.id,
            tenant_id=b.tenant_id,
            name=b.name,
            version=b.version,
            is_active=b.is_active,
            created_at=b.created_at.isoformat(),
        )
        for b in bundles
    ]


@router.put("/bundles/{bundle_id}/activate", response_model=PromptBundleResponse)
async def activate_prompt_bundle(
    bundle_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleResponse:
    """Activate a prompt bundle (deactivates others)."""
    prompt_service = PromptService(db)
    bundle = await prompt_service.activate_bundle(tenant_id, bundle_id)
    
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt bundle not found",
        )
    
    return PromptBundleResponse(
        id=bundle.id,
        tenant_id=bundle.tenant_id,
        name=bundle.name,
        version=bundle.version,
        is_active=bundle.is_active,
        created_at=bundle.created_at.isoformat(),
    )


@router.get("/compose", response_model=PromptComposeResponse)
async def get_composed_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptComposeResponse:
    """Get composed prompt (for testing)."""
    prompt_service = PromptService(db)
    prompt = await prompt_service.compose_prompt(tenant_id)
    
    return PromptComposeResponse(prompt=prompt)

