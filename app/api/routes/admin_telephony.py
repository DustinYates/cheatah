"""Admin telephony configuration endpoints for provider selection (Twilio/Telnyx)."""

import logging
from enum import Enum
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_admin
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_sms_config import TenantSmsConfig

logger = logging.getLogger(__name__)

router = APIRouter()


class TelephonyProvider(str, Enum):
    """Supported telephony providers."""

    TWILIO = "twilio"
    TELNYX = "telnyx"


class TelephonyConfigRequest(BaseModel):
    """Request to create or update telephony configuration."""

    provider: TelephonyProvider = TelephonyProvider.TWILIO

    # Feature flags
    sms_enabled: bool = False
    voice_enabled: bool = False

    # Twilio credentials
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None  # SMS number

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
    provider: TelephonyProvider

    # Feature flags
    sms_enabled: bool
    voice_enabled: bool

    # Twilio (don't expose auth token)
    twilio_account_sid: str | None = None
    has_twilio_auth_token: bool = False
    twilio_phone_number: str | None = None

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

    provider: TelephonyProvider

    # Twilio
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None

    # Telnyx
    telnyx_api_key: str | None = None


class ValidateCredentialsResponse(BaseModel):
    """Response from credentials validation."""

    valid: bool
    message: str | None = None
    error: str | None = None


@router.get("/config", response_model=TelephonyConfigResponse)
async def get_telephony_config(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelephonyConfigResponse:
    """Get telephony configuration for tenant.

    Args:
        admin_data: Admin user and tenant ID
        db: Database session

    Returns:
        Telephony configuration
    """
    current_user, tenant_id = admin_data

    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        # Return default config
        return TelephonyConfigResponse(
            id=0,
            tenant_id=tenant_id,
            provider=TelephonyProvider.TWILIO,
            sms_enabled=False,
            voice_enabled=False,
            has_twilio_auth_token=False,
            created_at="",
            updated_at="",
        )

    return _config_to_response(config)


@router.post("/config", response_model=TelephonyConfigResponse)
async def create_or_update_telephony_config(
    config_data: TelephonyConfigRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelephonyConfigResponse:
    """Create or update telephony configuration for tenant.

    This endpoint allows admins to configure either Twilio or Telnyx
    as the telephony provider for their tenant.

    Args:
        config_data: Telephony configuration data
        admin_data: Admin user and tenant ID
        db: Database session

    Returns:
        Updated telephony configuration
    """
    current_user, tenant_id = admin_data

    # Validate provider-specific credentials
    if config_data.provider == TelephonyProvider.TELNYX:
        if config_data.sms_enabled and not config_data.telnyx_api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telnyx API key is required when SMS is enabled with Telnyx",
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
    else:  # Twilio
        if config_data.sms_enabled and not config_data.twilio_account_sid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twilio Account SID is required when SMS is enabled with Twilio",
            )
        if config_data.sms_enabled and not config_data.twilio_phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twilio phone number is required for SMS",
            )

    # Check if config exists
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    existing_config = result.scalar_one_or_none()

    if existing_config:
        # Update existing
        existing_config.provider = config_data.provider.value
        existing_config.is_enabled = config_data.sms_enabled
        existing_config.voice_enabled = config_data.voice_enabled

        # Update Twilio fields
        if config_data.twilio_account_sid:
            existing_config.twilio_account_sid = config_data.twilio_account_sid
        if config_data.twilio_auth_token:  # Only update if provided
            existing_config.twilio_auth_token = config_data.twilio_auth_token
        if config_data.twilio_phone_number is not None:
            existing_config.twilio_phone_number = config_data.twilio_phone_number

        # Update Telnyx fields
        if config_data.telnyx_api_key:
            existing_config.telnyx_api_key = config_data.telnyx_api_key
        if config_data.telnyx_messaging_profile_id is not None:
            existing_config.telnyx_messaging_profile_id = config_data.telnyx_messaging_profile_id
        if config_data.telnyx_connection_id is not None:
            existing_config.telnyx_connection_id = config_data.telnyx_connection_id
        if config_data.telnyx_phone_number is not None:
            existing_config.telnyx_phone_number = config_data.telnyx_phone_number

        # Update voice phone number
        if config_data.voice_phone_number is not None:
            existing_config.voice_phone_number = config_data.voice_phone_number

        await db.commit()
        await db.refresh(existing_config)
        config = existing_config
    else:
        # Create new
        config = TenantSmsConfig(
            tenant_id=tenant_id,
            provider=config_data.provider.value,
            is_enabled=config_data.sms_enabled,
            voice_enabled=config_data.voice_enabled,
            twilio_account_sid=config_data.twilio_account_sid,
            twilio_auth_token=config_data.twilio_auth_token,
            twilio_phone_number=config_data.twilio_phone_number,
            telnyx_api_key=config_data.telnyx_api_key,
            telnyx_messaging_profile_id=config_data.telnyx_messaging_profile_id,
            telnyx_connection_id=config_data.telnyx_connection_id,
            telnyx_phone_number=config_data.telnyx_phone_number,
            voice_phone_number=config_data.voice_phone_number,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    logger.info(f"Updated telephony config for tenant {tenant_id}: provider={config_data.provider.value}")

    return _config_to_response(config)


@router.post("/validate-credentials", response_model=ValidateCredentialsResponse)
async def validate_telephony_credentials(
    credentials: ValidateCredentialsRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
) -> ValidateCredentialsResponse:
    """Validate telephony credentials without saving.

    Tests connection to provider API to verify credentials work.

    Args:
        credentials: Credentials to validate
        admin_data: Admin user and tenant ID

    Returns:
        Validation result
    """
    try:
        if credentials.provider == TelephonyProvider.TELNYX:
            if not credentials.telnyx_api_key:
                return ValidateCredentialsResponse(
                    valid=False,
                    error="Telnyx API key is required",
                )

            # Test Telnyx credentials by fetching phone numbers
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
        else:  # Twilio
            if not credentials.twilio_account_sid or not credentials.twilio_auth_token:
                return ValidateCredentialsResponse(
                    valid=False,
                    error="Twilio Account SID and Auth Token are required",
                )

            # Test Twilio credentials
            from twilio.rest import Client as TwilioClient
            from twilio.base.exceptions import TwilioException

            try:
                client = TwilioClient(
                    credentials.twilio_account_sid,
                    credentials.twilio_auth_token,
                )
                # Try to fetch account info
                account = client.api.accounts(credentials.twilio_account_sid).fetch()

                return ValidateCredentialsResponse(
                    valid=True,
                    message=f"Twilio credentials verified for {account.friendly_name}",
                )
            except TwilioException as e:
                return ValidateCredentialsResponse(
                    valid=False,
                    error=f"Twilio validation failed: {str(e)}",
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


def _config_to_response(config: TenantSmsConfig) -> TelephonyConfigResponse:
    """Convert config model to response, hiding secrets."""
    return TelephonyConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        provider=TelephonyProvider(config.provider) if config.provider else TelephonyProvider.TWILIO,
        sms_enabled=config.is_enabled,
        voice_enabled=config.voice_enabled if hasattr(config, "voice_enabled") else False,
        twilio_account_sid=config.twilio_account_sid,
        has_twilio_auth_token=bool(config.twilio_auth_token),
        twilio_phone_number=config.twilio_phone_number,
        telnyx_api_key_prefix=config.telnyx_api_key[:8] + "..." if config.telnyx_api_key else None,
        telnyx_messaging_profile_id=config.telnyx_messaging_profile_id,
        telnyx_connection_id=config.telnyx_connection_id,
        telnyx_phone_number=config.telnyx_phone_number,
        voice_phone_number=config.voice_phone_number if hasattr(config, "voice_phone_number") else None,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )
