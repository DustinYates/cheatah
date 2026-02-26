"""Admin SMS configuration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_tenant_admin
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class SmsConfigCreate(BaseModel):
    """SMS configuration creation request."""
    
    is_enabled: bool = False
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    business_hours_enabled: bool = False
    timezone: str = "UTC"
    business_hours: dict | None = None  # {"monday": {"start": "09:00", "end": "17:00"}, ...}
    auto_reply_outside_hours: bool = False
    auto_reply_message: str | None = None
    settings: dict | None = None


class SmsConfigResponse(BaseModel):
    """SMS configuration response."""
    
    id: int
    tenant_id: int
    is_enabled: bool
    twilio_account_sid: str | None = None
    twilio_phone_number: str | None
    business_hours_enabled: bool
    timezone: str
    business_hours: dict | None
    auto_reply_outside_hours: bool
    auto_reply_message: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.post("/config", response_model=SmsConfigResponse)
async def create_or_update_sms_config(
    config_data: SmsConfigCreate,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SmsConfigResponse:
    """Create or update SMS configuration for tenant.
    
    Args:
        config_data: SMS configuration data
        admin_data: Admin user and tenant ID
        db: Database session
        
    Returns:
        SMS configuration
    """
    from sqlalchemy import select
    from app.persistence.models.tenant_sms_config import TenantSmsConfig
    
    current_user, tenant_id = admin_data
    
    # Check if config exists
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    existing_config = result.scalar_one_or_none()
    
    if existing_config:
        # Update existing
        existing_config.is_enabled = config_data.is_enabled
        existing_config.twilio_account_sid = config_data.twilio_account_sid
        existing_config.twilio_auth_token = config_data.twilio_auth_token
        existing_config.twilio_phone_number = config_data.twilio_phone_number
        existing_config.business_hours_enabled = config_data.business_hours_enabled
        existing_config.timezone = config_data.timezone
        existing_config.business_hours = config_data.business_hours
        existing_config.auto_reply_outside_hours = config_data.auto_reply_outside_hours
        existing_config.auto_reply_message = config_data.auto_reply_message
        existing_config.settings = config_data.settings
        
        await db.commit()
        await db.refresh(existing_config)
        config = existing_config
    else:
        # Create new
        config = TenantSmsConfig(
            tenant_id=tenant_id,
            is_enabled=config_data.is_enabled,
            twilio_account_sid=config_data.twilio_account_sid,
            twilio_auth_token=config_data.twilio_auth_token,
            twilio_phone_number=config_data.twilio_phone_number,
            business_hours_enabled=config_data.business_hours_enabled,
            timezone=config_data.timezone,
            business_hours=config_data.business_hours,
            auto_reply_outside_hours=config_data.auto_reply_outside_hours,
            auto_reply_message=config_data.auto_reply_message,
            settings=config_data.settings,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    
    return SmsConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        twilio_account_sid=config.twilio_account_sid,
        twilio_phone_number=config.twilio_phone_number,
        business_hours_enabled=config.business_hours_enabled,
        timezone=config.timezone,
        business_hours=config.business_hours,
        auto_reply_outside_hours=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.get("/config", response_model=SmsConfigResponse)
async def get_sms_config(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SmsConfigResponse:
    """Get SMS configuration for tenant.
    
    Args:
        admin_data: Admin user and tenant ID
        db: Database session
        
    Returns:
        SMS configuration
    """
    from sqlalchemy import select
    from app.persistence.models.tenant_sms_config import TenantSmsConfig
    
    current_user, tenant_id = admin_data
    
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        # Return default config if not found
        return SmsConfigResponse(
            id=0,
            tenant_id=tenant_id,
            is_enabled=False,
            twilio_account_sid=None,
            twilio_phone_number=None,
            business_hours_enabled=False,
            timezone="UTC",
            business_hours=None,
            auto_reply_outside_hours=False,
            auto_reply_message=None,
            created_at="",
            updated_at="",
        )
    
    return SmsConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        twilio_account_sid=config.twilio_account_sid,
        twilio_phone_number=config.twilio_phone_number,
        business_hours_enabled=config.business_hours_enabled,
        timezone=config.timezone,
        business_hours=config.business_hours,
        auto_reply_outside_hours=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


class SendSmsRequest(BaseModel):
    """Send SMS request."""
    
    to: str
    message: str


@router.post("/send", response_model=dict)
async def send_manual_sms(
    sms_data: SendSmsRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Send manual outbound SMS (admin-initiated).

    Args:
        sms_data: SMS send request
        admin_data: Admin user and tenant ID
        db: Database session

    Returns:
        Send result
    """
    import logging
    from app.infrastructure.telephony.factory import TelephonyProviderFactory

    logger = logging.getLogger(__name__)
    current_user, tenant_id = admin_data

    # Use factory to support both Twilio and Telnyx
    factory = TelephonyProviderFactory(db)
    sms_config = await factory.get_config(tenant_id)

    if not sms_config or not sms_config.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMS is not enabled for this tenant",
        )

    from_phone = factory.get_sms_phone_number(sms_config)
    if not from_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No SMS phone number configured for this tenant",
        )

    sms_provider = await factory.get_sms_provider(tenant_id)
    if not sms_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SMS provider not configured for this tenant",
        )

    # Send SMS via the configured provider (Twilio or Telnyx)
    send_result = await sms_provider.send_sms(
        to=sms_data.to,
        from_=from_phone,
        body=sms_data.message,
    )

    logger.info(
        f"Manual SMS sent: tenant={tenant_id}, to={sms_data.to}, "
        f"provider={send_result.provider}, message_id={send_result.message_id}"
    )

    return {
        "status": "sent",
        "message_id": send_result.message_id,
        "provider": send_result.provider,
        "to": sms_data.to,
    }

