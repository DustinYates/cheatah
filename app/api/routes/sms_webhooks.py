"""SMS webhook endpoints for Twilio."""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import Response
from twilio.request_validator import RequestValidator

from app.domain.services.sms_service import SmsService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.redis import redis_client
from app.persistence.database import get_db
from app.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# TTL for message deduplication (5 minutes - enough to handle retries)
MESSAGE_DEDUP_TTL_SECONDS = 300


async def _validate_twilio_signature(
    request: Request,
    auth_token: str,
) -> bool:
    """Validate Twilio webhook signature.

    Args:
        request: FastAPI request
        auth_token: Twilio auth token for the account

    Returns:
        True if signature is valid, False otherwise
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        return False

    # Get the full URL as Twilio sees it
    url = str(request.url)

    # Get form data for validation
    form_data = await request.form()
    params = {key: form_data[key] for key in form_data}

    validator = RequestValidator(auth_token)
    return validator.validate(url, params, signature)

router = APIRouter()


@router.post("/inbound")
async def inbound_sms_webhook(
    request: Request,
    From: Annotated[str, Form()],  # Twilio sends as Form data
    To: Annotated[str, Form()],
    Body: Annotated[str, Form()],
    MessageSid: Annotated[str, Form()],
    AccountSid: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Handle inbound SMS webhook from Twilio.
    
    This endpoint:
    - Receives webhook from Twilio
    - Validates signature (optional, can be enabled)
    - Immediately returns 200 ACK
    - Queues message for async processing via Cloud Tasks
    
    Args:
        request: FastAPI request
        From: Sender phone number
        To: Recipient phone number (Twilio number)
        Body: Message body
        MessageSid: Twilio message SID
        AccountSid: Twilio account SID
        db: Database session
        
    Returns:
        TwiML response (empty for ACK)
    """
    try:
        # Deduplicate by MessageSid to prevent processing same message twice
        # (handles Twilio retries, webhook replay attacks, etc.)
        dedup_key = f"sms_msg_processed:{MessageSid}"
        if not await redis_client.setnx(dedup_key, "1", ttl=MESSAGE_DEDUP_TTL_SECONDS):
            # MONITORING: Log duplicate webhook with structured data for alerting
            logger.warning(
                "[DUPLICATE_WEBHOOK] Duplicate inbound SMS webhook ignored",
                extra={
                    "event_type": "duplicate_webhook_blocked",
                    "provider": "twilio",
                    "message_sid": MessageSid,
                    "from_number": From,
                    "to_number": To,
                },
            )
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        # Extract tenant_id and config from To number or AccountSid
        tenant_id, sms_config = await _get_tenant_and_config_from_phone_number(To, AccountSid, db)

        if not tenant_id:
            logger.warning(f"Could not determine tenant for phone number: {To}")
            # Return 200 to Twilio even if we can't process
            return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")

        # Validate Twilio signature in production
        if sms_config and sms_config.twilio_auth_token:
            is_valid = await _validate_twilio_signature(request, sms_config.twilio_auth_token)
            if not is_valid:
                if settings.environment == "production":
                    logger.warning(f"Invalid Twilio signature for tenant {tenant_id}")
                    raise HTTPException(status_code=403, detail="Invalid signature")
                else:
                    logger.warning(f"Invalid Twilio signature for tenant {tenant_id} (ignored in dev)")
        
        # Queue message for async processing
        if settings.cloud_tasks_worker_url:
            cloud_tasks = CloudTasksClient()
            await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": tenant_id,
                    "phone_number": From,
                    "message_body": Body,
                    "twilio_message_sid": MessageSid,
                    "to_number": To,
                },
                url=settings.cloud_tasks_worker_url,
            )
        else:
            # Fallback: process synchronously (not recommended for production)
            logger.warning("Cloud Tasks worker URL not configured, processing synchronously")
            sms_service = SmsService(db)
            await sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=From,
                message_body=Body,
                twilio_message_sid=MessageSid,
            )
        
        # Return immediate ACK to Twilio (TwiML)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )
        
    except Exception as e:
        logger.error(f"Error processing inbound SMS webhook: {e}", exc_info=True)
        # Still return 200 to Twilio to avoid retries
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )


@router.post("/status")
async def sms_status_callback(
    request: Request,
    MessageSid: Annotated[str, Form()],
    MessageStatus: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Handle SMS delivery status callback from Twilio.
    
    Args:
        request: FastAPI request
        MessageSid: Twilio message SID
        MessageStatus: Delivery status (queued, sent, delivered, failed, etc.)
        db: Database session
        
    Returns:
        Empty response (200 OK)
    """
    try:
        # Update message metadata with delivery status
        from sqlalchemy import select, cast, String
        from app.persistence.models.conversation import Message

        # Find message by Twilio SID in metadata
        # Use cast() instead of .astext for generic JSON columns
        stmt = select(Message).where(
            cast(Message.message_metadata["twilio_message_sid"], String) == MessageSid
        )
        result = await db.execute(stmt)
        message = result.scalar_one_or_none()
        
        if message:
            if message.message_metadata is None:
                message.message_metadata = {}
            message.message_metadata["delivery_status"] = MessageStatus
            message.message_metadata["status_updated_at"] = str(datetime.now(timezone.utc))
            await db.commit()
        
        logger.info(f"SMS status update: MessageSid={MessageSid}, Status={MessageStatus}")
        
    except Exception as e:
        logger.error(f"Error processing SMS status callback: {e}", exc_info=True)
    
    # Always return 200
    return Response(status_code=200)


async def _get_tenant_and_config_from_phone_number(
    phone_number: str,
    account_sid: str,
    db: AsyncSession,
) -> tuple[int | None, Any]:
    """Get tenant ID and SMS config from phone number or account SID.

    Args:
        phone_number: Twilio phone number
        account_sid: Twilio account SID
        db: Database session

    Returns:
        Tuple of (Tenant ID, TenantSmsConfig) or (None, None) if not found
    """
    from sqlalchemy import select
    from app.persistence.models.tenant_sms_config import TenantSmsConfig

    # Try to find tenant by Twilio phone number
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.twilio_phone_number == phone_number
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        return config.tenant_id, config

    # Try to find by account SID
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.twilio_account_sid == account_sid
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        return config.tenant_id, config

    return None, None

