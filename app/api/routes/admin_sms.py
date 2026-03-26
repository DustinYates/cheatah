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
    telnyx_api_key_prefix: str | None = None
    telnyx_messaging_profile_id: str | None = None
    telnyx_phone_number: str | None = None
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
    telnyx_api_key_prefix: str | None = None
    telnyx_phone_number: str | None
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
        existing_config.telnyx_api_key = config_data.telnyx_api_key_prefix
        existing_config.telnyx_messaging_profile_id = config_data.telnyx_messaging_profile_id
        existing_config.telnyx_phone_number = config_data.telnyx_phone_number
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
            telnyx_api_key=config_data.telnyx_api_key_prefix,
            telnyx_messaging_profile_id=config_data.telnyx_messaging_profile_id,
            telnyx_phone_number=config_data.telnyx_phone_number,
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
        telnyx_api_key_prefix=config.telnyx_api_key[:8] + "..." if config.telnyx_api_key else None,
        telnyx_phone_number=config.telnyx_phone_number,
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
            telnyx_api_key_prefix=None,
            telnyx_phone_number=None,
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
        telnyx_api_key_prefix=config.telnyx_api_key[:8] + "..." if config.telnyx_api_key else None,
        telnyx_phone_number=config.telnyx_phone_number,
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

    # Use factory to get the configured SMS provider
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

    # Send SMS via the configured provider
    import httpx

    try:
        send_result = await sms_provider.send_sms(
            to=sms_data.to,
            from_=from_phone,
            body=sms_data.message,
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        try:
            error_body = e.response.json()
            detail = error_body.get("errors", [{}])[0].get("detail", "") or error_body.get("detail", "")
        except Exception:
            detail = e.response.text[:200] if e.response.text else ""

        if status_code == 504 or status_code == 502:
            msg = "Telnyx API is temporarily unavailable. Please try again in a moment."
        elif status_code >= 500:
            msg = f"Telnyx server error ({status_code}). Please try again."
        else:
            msg = f"Telnyx rejected the message ({status_code}): {detail}" if detail else f"Telnyx rejected the message ({status_code})"

        logger.error(f"Telnyx SMS API error: tenant={tenant_id}, to={sms_data.to}, status={status_code}, detail={detail}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)
    except httpx.TimeoutException:
        logger.error(f"Telnyx SMS timeout: tenant={tenant_id}, to={sms_data.to}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Telnyx API timed out. Please try again.",
        )

    logger.info(
        f"Manual SMS sent: tenant={tenant_id}, to={sms_data.to}, "
        f"provider={send_result.provider}, message_id={send_result.message_id}"
    )

    # Record the outbound message in the conversation timeline
    try:
        from app.domain.services.conversation_service import ConversationService
        from app.persistence.repositories.conversation_repository import ConversationRepository
        from app.core.phone import normalize_phone_for_dedup
        from sqlalchemy import select

        # Normalize recipient phone number
        normalized_phone = normalize_phone_for_dedup(sms_data.to)

        # Get or create conversation for this phone
        conv_repo = ConversationRepository(db)
        conversation = await conv_repo.get_by_phone_number(
            tenant_id, normalized_phone, channel="sms"
        )

        if not conversation:
            # Create new conversation
            conv_service = ConversationService(db)
            conversation = await conv_service.create_conversation(
                tenant_id=tenant_id,
                channel="sms",
                external_id=None,
            )
            conversation.phone_number = normalized_phone
            await db.commit()
            await db.refresh(conversation)

        conv_service = ConversationService(db)

        # Add message to conversation with metadata tracking the Telnyx message ID
        await conv_service.add_message(
            tenant_id,
            conversation.id,
            "assistant",
            sms_data.message,
            metadata={
                "source": "manual_send",
                "provider": send_result.provider,
                "telnyx_message_id": send_result.message_id,
                "delivery_status": "sent",
            },
        )

        logger.info(
            f"Recorded outbound SMS message: tenant={tenant_id}, "
            f"conversation={conversation.id}, to={normalized_phone}"
        )
    except Exception as e:
        logger.error(
            f"Failed to record outbound SMS message: tenant={tenant_id}, to={sms_data.to}, error={e}",
            exc_info=True,
        )
        # Don't fail the SMS send if message recording fails
        # The SMS was already sent successfully

    return {
        "status": "sent",
        "message_id": send_result.message_id,
        "provider": send_result.provider,
        "to": sms_data.to,
    }


class BulkSmsRequest(BaseModel):
    """Bulk SMS send request."""

    phones: list[str]
    message: str


@router.post("/send-bulk", response_model=dict)
async def send_bulk_sms(
    bulk_data: BulkSmsRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Send the same SMS message to multiple phone numbers."""
    import logging
    from app.infrastructure.telephony.factory import TelephonyProviderFactory
    from app.domain.services.conversation_service import ConversationService
    from app.persistence.repositories.conversation_repository import ConversationRepository
    from app.core.phone import normalize_phone_for_dedup

    logger = logging.getLogger(__name__)
    current_user, tenant_id = admin_data

    if not bulk_data.phones:
        raise HTTPException(status_code=400, detail="No phone numbers provided")
    if len(bulk_data.phones) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 recipients per bulk send")
    if not bulk_data.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    factory = TelephonyProviderFactory(db)
    sms_config = await factory.get_config(tenant_id)

    if not sms_config or not sms_config.is_enabled:
        raise HTTPException(status_code=400, detail="SMS is not enabled for this tenant")

    from_phone = factory.get_sms_phone_number(sms_config)
    if not from_phone:
        raise HTTPException(status_code=400, detail="No SMS phone number configured")

    sms_provider = await factory.get_sms_provider(tenant_id)
    if not sms_provider:
        raise HTTPException(status_code=400, detail="SMS provider not configured")

    results = {"sent": 0, "failed": 0, "errors": []}
    conv_repo = ConversationRepository(db)
    conv_service = ConversationService(db)

    for phone in bulk_data.phones:
        try:
            send_result = await sms_provider.send_sms(
                to=phone, from_=from_phone, body=bulk_data.message.strip(),
            )
            results["sent"] += 1

            # Record in conversation timeline
            try:
                normalized = normalize_phone_for_dedup(phone)
                conversation = await conv_repo.get_by_phone_number(
                    tenant_id, normalized, channel="sms"
                )
                if not conversation:
                    conversation = await conv_service.create_conversation(
                        tenant_id=tenant_id, channel="sms", external_id=None,
                    )
                    conversation.phone_number = normalized
                    await db.commit()
                    await db.refresh(conversation)

                await conv_service.add_message(
                    tenant_id, conversation.id, "assistant", bulk_data.message.strip(),
                    metadata={
                        "source": "bulk_send",
                        "provider": send_result.provider,
                        "telnyx_message_id": send_result.message_id,
                        "delivery_status": "sent",
                    },
                )
            except Exception as rec_err:
                logger.error(f"Failed to record bulk SMS message: {phone}, error={rec_err}")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"phone": phone, "error": str(e)})
            logger.error(f"Bulk SMS failed: tenant={tenant_id}, to={phone}, error={e}")

    logger.info(
        f"Bulk SMS complete: tenant={tenant_id}, sent={results['sent']}, "
        f"failed={results['failed']}, total={len(bulk_data.phones)}"
    )
    return results

