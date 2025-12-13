"""Prompt routes for prompt bundle management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_tenant, get_current_user
from app.domain.services.prompt_service import PromptService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.prompt import PromptStatus, SectionScope
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class PromptSectionCreate(BaseModel):
    """Prompt section creation request."""

    section_key: str
    content: str
    scope: str = SectionScope.CUSTOM.value
    order: int = 0


class PromptSectionResponse(BaseModel):
    """Prompt section response."""

    id: int
    section_key: str
    scope: str
    content: str
    order: int

    class Config:
        from_attributes = True


class PromptBundleCreate(BaseModel):
    """Prompt bundle creation request."""

    name: str
    version: str = "1.0.0"
    sections: list[PromptSectionCreate]


class PromptBundleUpdate(BaseModel):
    """Prompt bundle update request."""

    name: str | None = None
    sections: list[PromptSectionCreate] | None = None


class PromptBundleResponse(BaseModel):
    """Prompt bundle response."""

    id: int
    tenant_id: int | None
    name: str
    version: str
    status: str
    is_active: bool
    published_at: str | None = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PromptBundleDetailResponse(PromptBundleResponse):
    """Prompt bundle detail with sections."""

    sections: list[PromptSectionResponse]


class PromptComposeResponse(BaseModel):
    """Composed prompt response."""

    prompt: str


class PromptTestRequest(BaseModel):
    """Request to test a prompt with a message."""

    message: str
    bundle_id: int | None = None


class PromptTestResponse(BaseModel):
    """Response from prompt test."""

    composed_prompt: str
    response: str


@router.post("/bundles", response_model=PromptBundleResponse)
async def create_prompt_bundle(
    bundle_data: PromptBundleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleResponse:
    """Create a new prompt bundle (starts in draft status)."""
    from app.persistence.models.prompt import PromptBundle, PromptSection
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_repo = PromptRepository(db)
    bundle = await prompt_repo.create(
        tenant_id,
        name=bundle_data.name,
        version=bundle_data.version,
        status=PromptStatus.DRAFT.value,
        is_active=False,
    )
    
    for section_data in bundle_data.sections:
        section = PromptSection(
            bundle_id=bundle.id,
            section_key=section_data.section_key,
            scope=section_data.scope,
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
        status=bundle.status,
        is_active=bundle.is_active,
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
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
            status=b.status,
            is_active=b.is_active,
            published_at=b.published_at.isoformat() if b.published_at else None,
            created_at=b.created_at.isoformat(),
            updated_at=b.updated_at.isoformat(),
        )
        for b in bundles
    ]


@router.get("/bundles/{bundle_id}", response_model=PromptBundleDetailResponse)
async def get_prompt_bundle(
    bundle_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleDetailResponse:
    """Get a prompt bundle with its sections."""
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_repo = PromptRepository(db)
    bundle = await prompt_repo.get_by_id(tenant_id, bundle_id)
    
    if not bundle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt bundle not found",
        )
    
    sections = await prompt_repo.get_sections(bundle_id)
    
    return PromptBundleDetailResponse(
        id=bundle.id,
        tenant_id=bundle.tenant_id,
        name=bundle.name,
        version=bundle.version,
        status=bundle.status,
        is_active=bundle.is_active,
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
        sections=[
            PromptSectionResponse(
                id=s.id,
                section_key=s.section_key,
                scope=s.scope,
                content=s.content,
                order=s.order,
            )
            for s in sections
        ],
    )


@router.put("/bundles/{bundle_id}", response_model=PromptBundleResponse)
async def update_prompt_bundle(
    bundle_id: int,
    bundle_data: PromptBundleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleResponse:
    """Update a prompt bundle (only allowed if in draft status)."""
    from app.persistence.models.prompt import PromptSection
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_repo = PromptRepository(db)
    bundle = await prompt_repo.get_by_id(tenant_id, bundle_id)
    
    if not bundle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt bundle not found",
        )
    
    if bundle.status == PromptStatus.PRODUCTION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit production bundle. Create a new draft or clone this bundle.",
        )
    
    if bundle_data.name:
        bundle.name = bundle_data.name
    
    if bundle_data.sections is not None:
        existing_sections = await prompt_repo.get_sections(bundle_id)
        for section in existing_sections:
            await db.delete(section)
        
        for section_data in bundle_data.sections:
            section = PromptSection(
                bundle_id=bundle.id,
                section_key=section_data.section_key,
                scope=section_data.scope,
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
        status=bundle.status,
        is_active=bundle.is_active,
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
    )


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
        status=bundle.status,
        is_active=bundle.is_active,
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
    )


@router.put("/bundles/{bundle_id}/publish", response_model=PromptBundleResponse)
async def publish_prompt_bundle(
    bundle_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptBundleResponse:
    """Publish a bundle to production (makes it live for the widget)."""
    prompt_service = PromptService(db)
    bundle = await prompt_service.publish_bundle(tenant_id, bundle_id)
    
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
        status=bundle.status,
        is_active=bundle.is_active,
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
    )


@router.post("/test", response_model=PromptTestResponse)
async def test_prompt(
    test_request: PromptTestRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptTestResponse:
    """Test a prompt with a sample message."""
    from app.llm.gemini_client import GeminiClient
    from app.persistence.repositories.prompt_repository import PromptRepository
    
    prompt_service = PromptService(db)
    prompt_repo = PromptRepository(db)
    
    if test_request.bundle_id:
        bundle = await prompt_repo.get_by_id(tenant_id, test_request.bundle_id)
        if not bundle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prompt bundle not found",
            )
        sections = await prompt_repo.get_sections(test_request.bundle_id)
        global_bundle = await prompt_repo.get_global_base_bundle()
        all_sections = []
        if global_bundle:
            global_sections = await prompt_repo.get_sections(global_bundle.id)
            all_sections.extend(global_sections)
        all_sections.extend(sections)
        section_map: dict[str, tuple[str, int]] = {}
        for section in all_sections:
            section_map[section.section_key] = (section.content, section.order)
        sorted_sections = sorted(section_map.items(), key=lambda x: (x[1][1], x[0]))
        composed_prompt = "\n\n".join([content for _, (content, _) in sorted_sections])
    else:
        composed_prompt = await prompt_service.compose_prompt(tenant_id, use_draft=True)
    
    full_prompt = f"{composed_prompt}\n\nUser message: {test_request.message}\n\nAssistant response:"
    
    gemini = GeminiClient()
    response = await gemini.generate(full_prompt)
    
    return PromptTestResponse(
        composed_prompt=composed_prompt,
        response=response,
    )


@router.get("/compose", response_model=PromptComposeResponse)
async def get_composed_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    use_draft: bool = False,
) -> PromptComposeResponse:
    """Get composed prompt (for testing)."""
    prompt_service = PromptService(db)
    prompt = await prompt_service.compose_prompt(tenant_id, use_draft=use_draft)
    
    return PromptComposeResponse(prompt=prompt)
