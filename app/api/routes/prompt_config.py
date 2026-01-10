"""Routes for JSON-based prompt configuration (v2 system)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user, require_global_admin
from app.domain.prompts.assembler import PromptAssembler
from app.domain.prompts.base_configs import get_base_config
from app.domain.prompts.schemas.v1.bss_schema import BSSTenantConfig
from app.domain.services.prompt_service import PromptService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.tenant_prompt_config_repository import TenantPromptConfigRepository

router = APIRouter(dependencies=[Depends(require_global_admin)])


class PromptConfigRequest(BaseModel):
    """Request to upload tenant prompt config."""

    config: dict[str, Any]
    schema_version: str = "bss_chatbot_prompt_v1"
    business_type: str = "bss"


class PromptConfigResponse(BaseModel):
    """Prompt config response."""

    id: int
    tenant_id: int
    schema_version: str
    business_type: str
    config: dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str


class PromptPreviewRequest(BaseModel):
    """Request to preview assembled prompt."""

    channel: str = "chat"
    context: dict[str, Any] | None = None


class PromptPreviewResponse(BaseModel):
    """Preview of assembled prompt."""

    prompt: str
    channel: str
    config_id: int | None = None


class ValidationErrorDetail(BaseModel):
    """Validation error detail."""

    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    detail: str
    errors: list[ValidationErrorDetail]


@router.post(
    "/config",
    response_model=PromptConfigResponse,
    responses={
        400: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def upsert_prompt_config(
    request: PromptConfigRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptConfigResponse:
    """Create or update tenant prompt configuration.

    Validates the JSON config against the schema before saving.
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required for prompt configuration",
        )

    # Validate JSON against schema
    try:
        BSSTenantConfig.model_validate(request.config)
    except ValidationError as e:
        errors = [
            ValidationErrorDetail(
                loc=[str(loc) for loc in err["loc"]],
                msg=err["msg"],
                type=err["type"],
            )
            for err in e.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid configuration JSON",
        ) from e

    # Upsert config
    repo = TenantPromptConfigRepository(db)
    config = await repo.upsert(
        tenant_id=tenant_id,
        config_json=request.config,
        schema_version=request.schema_version,
        business_type=request.business_type,
    )

    return PromptConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        schema_version=config.schema_version,
        business_type=config.business_type,
        config=config.config_json,
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.get("/config", response_model=PromptConfigResponse | None)
async def get_prompt_config(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptConfigResponse | None:
    """Get current tenant prompt configuration."""
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required for prompt configuration",
        )

    repo = TenantPromptConfigRepository(db)
    config = await repo.get_by_tenant_id(tenant_id)

    if config is None:
        return None

    return PromptConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        schema_version=config.schema_version,
        business_type=config.business_type,
        config=config.config_json,
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.post("/preview", response_model=PromptPreviewResponse)
async def preview_prompt(
    request: PromptPreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptPreviewResponse:
    """Preview the assembled prompt for a tenant.

    This shows what the final system prompt looks like after
    combining base config + tenant JSON config.
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required for prompt preview",
        )

    prompt_service = PromptService(db)
    prompt = await prompt_service.compose_prompt_v2(
        tenant_id=tenant_id,
        channel=request.channel,
        context=request.context,
    )

    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No v2 prompt configuration found for this tenant",
        )

    # Get config ID
    repo = TenantPromptConfigRepository(db)
    config = await repo.get_by_tenant_id(tenant_id)

    return PromptPreviewResponse(
        prompt=prompt,
        channel=request.channel,
        config_id=config.id if config else None,
    )


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_config(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete tenant prompt configuration.

    This will cause the tenant to fall back to v1 prompt system.
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required for prompt configuration",
        )

    repo = TenantPromptConfigRepository(db)
    config = await repo.get_by_tenant_id(tenant_id)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prompt configuration found for this tenant",
        )

    await repo.delete(config)


@router.get("/base-config")
async def get_base_config_sections(
    business_type: str = "bss",
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> dict[str, Any]:
    """Get the base config sections (hardcoded rules).

    Returns the base configuration that will be combined with tenant JSON.
    """
    base_config = get_base_config(business_type)
    sections = base_config.get_all_sections()
    section_order = base_config.default_section_order

    return {
        "business_type": business_type,
        "schema_version": base_config.schema_version,
        "sections": sections,
        "section_order": section_order,
        "tenant_sections": [
            "business_info",
            "locations",
            "program_basics",
            "levels",
            "level_placement_rules",
            "tuition",
            "fees",
            "discounts",
            "policies",
            "registration",
        ],
    }


@router.post("/validate", response_model=dict[str, Any])
async def validate_config(
    request: PromptConfigRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Validate a config JSON without saving it.

    Returns validation result and any errors found.
    """
    try:
        validated = BSSTenantConfig.model_validate(request.config)
        return {
            "valid": True,
            "message": "Configuration is valid",
            "tenant_id": validated.tenant_id,
            "display_name": validated.display_name,
            "sections_count": {
                "locations": len(validated.locations) if validated.locations else 0,
                "levels": validated.levels.items_count if validated.levels else 0,
                "tuition": validated.tuition.items_count if validated.tuition else 0,
                "policies": len(validated.policies.items) if validated.policies else 0,
            },
        }
    except ValidationError as e:
        return {
            "valid": False,
            "message": "Configuration validation failed",
            "errors": [
                {
                    "location": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in e.errors()
            ],
        }


@router.post("/preview-from-json", response_model=PromptPreviewResponse)
async def preview_from_json(
    config: dict[str, Any],
    channel: str = "chat",
    business_type: str = "bss",
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> PromptPreviewResponse:
    """Preview assembled prompt from JSON without saving.

    Useful for testing config changes before deploying.
    """
    # Validate JSON against schema
    try:
        tenant_config = BSSTenantConfig.model_validate(config)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {e.errors()}",
        ) from e

    # Assemble prompt
    assembler = PromptAssembler(business_type=business_type)
    prompt = assembler.assemble(
        tenant_config=tenant_config,
        channel=channel,
        context=None,
    )

    return PromptPreviewResponse(
        prompt=prompt,
        channel=channel,
        config_id=None,
    )
