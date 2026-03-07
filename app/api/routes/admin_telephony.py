"""Admin telephony configuration endpoints for Telnyx provider."""

import logging
from enum import Enum
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin, require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_sms_config import TenantSmsConfig

logger = logging.getLogger(__name__)

router = APIRouter()


class TelephonyConfigRequest(BaseModel):
    """Request to create or update telephony configuration."""

    # Feature flags
    sms_enabled: bool = False
    voice_enabled: bool = False

    # Telnyx credentials
    telnyx_api_key: str | None = None
    telnyx_messaging_profile_id: str | None = None
    telnyx_connection_id: str | None = None
    telnyx_phone_number: str | None = None  # SMS number

    # Voice phone number (can be different from SMS)
    voice_phone_number: str | None = None


class TelephonyConfigResponse(BaseModel):
    """Telephony configuration response."""

    id: int
    tenant_id: int

    # Feature flags
    sms_enabled: bool
    voice_enabled: bool

    # Telnyx (show only prefix of API key)
    telnyx_api_key_prefix: str | None = None
    telnyx_messaging_profile_id: str | None = None
    telnyx_connection_id: str | None = None
    telnyx_phone_number: str | None = None

    # Voice
    voice_phone_number: str | None = None

    created_at: str
    updated_at: str


class ValidateCredentialsRequest(BaseModel):
    """Request to validate telephony credentials."""

    telnyx_api_key: str | None = None


class ValidateCredentialsResponse(BaseModel):
    """Response from credentials validation."""

    valid: bool
    message: str | None = None
    error: str | None = None


class CredentialField(str, Enum):
    """Credential fields that can be revealed or audited."""

    TELNYX_API_KEY = "telnyx_api_key"


class CredentialAction(str, Enum):
    """Audit actions for credential access."""

    REVEAL = "reveal"
    COPY = "copy"


class CredentialRevealRequest(BaseModel):
    """Request to reveal a credential value."""

    field: CredentialField = Field(..., description="Credential field to reveal")


class CredentialRevealResponse(BaseModel):
    """Response containing revealed credential."""

    value: str


class CredentialAuditRequest(BaseModel):
    """Request to audit credential access."""

    action: CredentialAction = Field(..., description="Action performed on credential")
    field: str = Field(..., description="Credential field identifier")


@router.get("/config", response_model=TelephonyConfigResponse)
async def get_telephony_config(
    _current_user: Annotated[User, Depends(require_global_admin)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelephonyConfigResponse:
    """Get telephony configuration for tenant."""
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        return TelephonyConfigResponse(
            id=0,
            tenant_id=tenant_id,
            sms_enabled=False,
            voice_enabled=False,
            created_at="",
            updated_at="",
        )

    return _config_to_response(config)


@router.post("/config", response_model=TelephonyConfigResponse)
async def create_or_update_telephony_config(
    config_data: TelephonyConfigRequest,
    _current_user: Annotated[User, Depends(require_global_admin)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelephonyConfigResponse:
    """Create or update telephony configuration for tenant."""
    if config_data.sms_enabled and not config_data.telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telnyx API key is required when SMS is enabled",
        )
    if config_data.sms_enabled and not config_data.telnyx_messaging_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telnyx Messaging Profile ID is required for SMS",
        )
    if config_data.sms_enabled and not config_data.telnyx_phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telnyx phone number is required for SMS",
        )

    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    existing_config = result.scalar_one_or_none()

    if existing_config:
        existing_config.provider = "telnyx"
        existing_config.is_enabled = config_data.sms_enabled
        existing_config.voice_enabled = config_data.voice_enabled

        if config_data.telnyx_api_key:
            existing_config.telnyx_api_key = config_data.telnyx_api_key
        if config_data.telnyx_messaging_profile_id is not None:
            existing_config.telnyx_messaging_profile_id = config_data.telnyx_messaging_profile_id
        if config_data.telnyx_connection_id is not None:
            existing_config.telnyx_connection_id = config_data.telnyx_connection_id
        if config_data.telnyx_phone_number is not None:
            existing_config.telnyx_phone_number = config_data.telnyx_phone_number
        if config_data.voice_phone_number is not None:
            existing_config.voice_phone_number = config_data.voice_phone_number

        await db.commit()
        await db.refresh(existing_config)
        config = existing_config
    else:
        config = TenantSmsConfig(
            tenant_id=tenant_id,
            provider="telnyx",
            is_enabled=config_data.sms_enabled,
            voice_enabled=config_data.voice_enabled,
            telnyx_api_key=config_data.telnyx_api_key,
            telnyx_messaging_profile_id=config_data.telnyx_messaging_profile_id,
            telnyx_connection_id=config_data.telnyx_connection_id,
            telnyx_phone_number=config_data.telnyx_phone_number,
            voice_phone_number=config_data.voice_phone_number,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    logger.info(f"Updated telephony config for tenant {tenant_id}")

    return _config_to_response(config)


@router.post("/validate-credentials", response_model=ValidateCredentialsResponse)
async def validate_telephony_credentials(
    credentials: ValidateCredentialsRequest,
    _current_user: Annotated[User, Depends(require_global_admin)],
    _tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ValidateCredentialsResponse:
    """Validate Telnyx credentials without saving."""
    try:
        if not credentials.telnyx_api_key:
            return ValidateCredentialsResponse(
                valid=False,
                error="Telnyx API key is required",
            )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.telnyx.com/v2/phone_numbers",
                headers={"Authorization": f"Bearer {credentials.telnyx_api_key}"},
                params={"page[size]": 1},
                timeout=10.0,
            )

            if response.status_code == 401:
                return ValidateCredentialsResponse(
                    valid=False,
                    error="Invalid Telnyx API key",
                )
            elif response.status_code == 403:
                return ValidateCredentialsResponse(
                    valid=False,
                    error="Telnyx API key does not have required permissions",
                )
            response.raise_for_status()

            return ValidateCredentialsResponse(
                valid=True,
                message="Telnyx credentials verified successfully",
            )

    except httpx.HTTPError as e:
        return ValidateCredentialsResponse(
            valid=False,
            error=f"Network error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error validating credentials: {e}", exc_info=True)
        return ValidateCredentialsResponse(
            valid=False,
            error=f"Validation error: {str(e)}",
        )


@router.post("/credentials/reveal", response_model=CredentialRevealResponse)
async def reveal_telephony_credential(
    request: CredentialRevealRequest,
    current_user: Annotated[User, Depends(require_global_admin)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CredentialRevealResponse:
    """Reveal a sensitive credential value for admins."""
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telephony config not found")

    field_name = request.field.value
    value = getattr(config, field_name, None)

    if not value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not configured")

    logger.info(
        "Telephony credential revealed",
        extra={"tenant_id": tenant_id, "user_id": current_user.id, "field": field_name},
    )

    return CredentialRevealResponse(value=value)


@router.post("/credentials/audit")
async def audit_telephony_credential_action(
    request: CredentialAuditRequest,
    current_user: Annotated[User, Depends(require_global_admin)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> dict:
    """Audit credential actions such as reveal or copy."""
    logger.info(
        "Telephony credential action",
        extra={
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "action": request.action.value,
            "field": request.field,
        },
    )
    return {"ok": True}


def _config_to_response(config: TenantSmsConfig) -> TelephonyConfigResponse:
    """Convert config model to response, hiding secrets."""
    return TelephonyConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        sms_enabled=config.is_enabled,
        voice_enabled=config.voice_enabled if hasattr(config, "voice_enabled") else False,
        telnyx_api_key_prefix=config.telnyx_api_key[:8] + "..." if config.telnyx_api_key else None,
        telnyx_messaging_profile_id=config.telnyx_messaging_profile_id,
        telnyx_connection_id=config.telnyx_connection_id,
        telnyx_phone_number=config.telnyx_phone_number,
        voice_phone_number=config.voice_phone_number if hasattr(config, "voice_phone_number") else None,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )
