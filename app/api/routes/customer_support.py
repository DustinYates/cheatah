"""Customer support configuration API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_tenant_context
from app.persistence.models.tenant import User
from app.persistence.repositories.customer_support_config_repository import CustomerSupportConfigRepository

router = APIRouter()


class CustomerSupportConfigResponse(BaseModel):
    """Customer support config response schema."""

    id: int
    tenant_id: int
    is_enabled: bool
    telnyx_agent_id: str | None
    telnyx_phone_number: str | None
    telnyx_messaging_profile_id: str | None
    support_sms_enabled: bool
    support_voice_enabled: bool
    routing_rules: dict | None
    handoff_mode: str
    transfer_number: str | None
    system_prompt_override: str | None
    settings: dict | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CustomerSupportConfigUpdateRequest(BaseModel):
    """Update customer support config request."""

    is_enabled: bool | None = None
    telnyx_agent_id: str | None = None
    telnyx_phone_number: str | None = None
    telnyx_messaging_profile_id: str | None = None
    support_sms_enabled: bool | None = None
    support_voice_enabled: bool | None = None
    routing_rules: dict | None = None
    handoff_mode: str | None = None
    transfer_number: str | None = None
    system_prompt_override: str | None = None
    settings: dict | None = None


def _serialize_config(config) -> dict:
    """Serialize config to response dict."""
    return {
        "id": config.id,
        "tenant_id": config.tenant_id,
        "is_enabled": config.is_enabled,
        "telnyx_agent_id": config.telnyx_agent_id,
        "telnyx_phone_number": config.telnyx_phone_number,
        "telnyx_messaging_profile_id": config.telnyx_messaging_profile_id,
        "support_sms_enabled": config.support_sms_enabled,
        "support_voice_enabled": config.support_voice_enabled,
        "routing_rules": config.routing_rules,
        "handoff_mode": config.handoff_mode,
        "transfer_number": config.transfer_number,
        "system_prompt_override": config.system_prompt_override,
        "settings": config.settings,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


@router.get("/config", response_model=CustomerSupportConfigResponse | None)
async def get_customer_support_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerSupportConfigResponse | None:
    """Get customer support configuration for tenant."""
    repo = CustomerSupportConfigRepository(db)
    config = await repo.get_by_tenant_id(tenant_id)

    if not config:
        return None

    return CustomerSupportConfigResponse(**_serialize_config(config))


@router.put("/config", response_model=CustomerSupportConfigResponse)
async def update_customer_support_config(
    request: CustomerSupportConfigUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerSupportConfigResponse:
    """Update customer support configuration (creates if doesn't exist)."""
    repo = CustomerSupportConfigRepository(db)

    # Build update dict excluding None values
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}

    config = await repo.create_or_update(tenant_id, **update_data)

    return CustomerSupportConfigResponse(**_serialize_config(config))
