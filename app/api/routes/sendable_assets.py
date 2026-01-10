"""API routes for managing sendable assets (registration links, schedules, etc.)."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_tenant
from app.persistence.database import get_db
from app.persistence.models.tenant_prompt_config import TenantPromptConfig

logger = logging.getLogger(__name__)

router = APIRouter()


class SendableAsset(BaseModel):
    """A sendable asset configuration."""

    sms_template: str = Field(..., description="SMS template with {name} and {url} placeholders")
    url: str = Field(..., description="URL to send")
    enabled: bool = Field(default=True, description="Whether this asset is active")


class SendableAssetsConfig(BaseModel):
    """Configuration for all sendable assets."""

    registration_link: SendableAsset | None = None
    schedule: SendableAsset | None = None
    pricing: SendableAsset | None = None
    info: SendableAsset | None = None


class SendableAssetsResponse(BaseModel):
    """Response containing sendable assets configuration."""

    assets: dict[str, SendableAsset]
    has_config: bool


class UpsertSendableAssetRequest(BaseModel):
    """Request to create or update a single sendable asset."""

    asset_type: str = Field(..., description="Asset type: registration_link, schedule, pricing, info")
    sms_template: str = Field(..., description="SMS template with {name} and {url} placeholders")
    url: str = Field(..., description="URL to send")
    enabled: bool = Field(default=True)


@router.get("/assets", response_model=SendableAssetsResponse)
async def get_sendable_assets(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> SendableAssetsResponse:
    """Get all sendable assets for the current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Get tenant prompt config
    stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    prompt_config = result.scalar_one_or_none()

    if not prompt_config or not prompt_config.config_json:
        return SendableAssetsResponse(assets={}, has_config=False)

    config = prompt_config.config_json
    if isinstance(config, str):
        import json
        config = json.loads(config)

    sendable_assets = config.get("sendable_assets", {})

    return SendableAssetsResponse(
        assets=sendable_assets,
        has_config=True,
    )


@router.put("/assets/{asset_type}", response_model=dict)
async def upsert_sendable_asset(
    asset_type: str,
    request: UpsertSendableAssetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> dict[str, Any]:
    """Create or update a sendable asset."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Validate asset type
    valid_types = ["registration_link", "schedule", "pricing", "info"]
    if asset_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid asset type. Must be one of: {', '.join(valid_types)}",
        )

    # Validate template has required placeholders
    if "{url}" not in request.sms_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMS template must contain {url} placeholder",
        )

    # Get or create tenant prompt config
    stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    prompt_config = result.scalar_one_or_none()

    if not prompt_config:
        # Create new prompt config
        prompt_config = TenantPromptConfig(
            tenant_id=tenant_id,
            config_json={},
            schema_version="v1",
            business_type="general",
            is_active=True,
        )
        db.add(prompt_config)

    # Update config_json with sendable asset
    config = prompt_config.config_json or {}
    if isinstance(config, str):
        import json
        config = json.loads(config)

    if "sendable_assets" not in config:
        config["sendable_assets"] = {}

    config["sendable_assets"][asset_type] = {
        "sms_template": request.sms_template,
        "url": request.url,
        "enabled": request.enabled,
    }

    prompt_config.config_json = config
    flag_modified(prompt_config, "config_json")
    await db.commit()

    logger.info(f"Updated sendable asset '{asset_type}' for tenant {tenant_id}")

    return {
        "status": "success",
        "asset_type": asset_type,
        "message": f"Sendable asset '{asset_type}' saved successfully",
    }


@router.delete("/assets/{asset_type}", response_model=dict)
async def delete_sendable_asset(
    asset_type: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> dict[str, Any]:
    """Delete a sendable asset."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Get tenant prompt config
    stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    prompt_config = result.scalar_one_or_none()

    if not prompt_config or not prompt_config.config_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sendable assets configured",
        )

    config = prompt_config.config_json
    if isinstance(config, str):
        import json
        config = json.loads(config)

    sendable_assets = config.get("sendable_assets", {})
    if asset_type not in sendable_assets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset type '{asset_type}' not found",
        )

    del config["sendable_assets"][asset_type]
    prompt_config.config_json = config
    flag_modified(prompt_config, "config_json")
    await db.commit()

    logger.info(f"Deleted sendable asset '{asset_type}' for tenant {tenant_id}")

    return {
        "status": "success",
        "message": f"Sendable asset '{asset_type}' deleted successfully",
    }


class TestSendAssetRequest(BaseModel):
    """Request to test send an asset via SMS."""

    asset_type: str = Field(..., description="Asset type to send: registration_link, schedule, pricing, info")
    phone_number: str = Field(..., description="Phone number to send to (E.164 or 10-digit)")
    name: str = Field(default="Test User", description="Name to use in the template")


@router.post("/test-send", response_model=dict)
async def test_send_asset(
    request: TestSendAssetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> dict[str, Any]:
    """Test send an asset via SMS to a specified phone number."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    from app.domain.services.promise_detector import DetectedPromise
    from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService

    # Create a mock promise for the asset type
    promise = DetectedPromise(
        asset_type=request.asset_type,
        confidence=1.0,
        original_text=f"Test send of {request.asset_type}",
    )

    fulfillment_service = PromiseFulfillmentService(db)

    result = await fulfillment_service.fulfill_promise(
        tenant_id=tenant_id,
        conversation_id=0,  # Test - no real conversation
        promise=promise,
        phone=request.phone_number,
        name=request.name,
    )

    logger.info(f"Test send result for tenant {tenant_id}: {result}")

    return {
        "status": result.get("status"),
        "message_id": result.get("message_id"),
        "to": result.get("to"),
        "error": result.get("error"),
    }
