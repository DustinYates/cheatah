"""SMS webhook endpoints for Twilio."""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import Response

from app.domain.services.sms_service import SmsService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.persistence.database import get_db
from app.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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
        # Extract tenant_id from To number or AccountSid
        # In production, you'd map Twilio numbers to tenant IDs
        # For now, we'll need to determine tenant from To number or config
        tenant_id = await _get_tenant_from_phone_number(To, AccountSid, db)
        
        if not tenant_id:
            logger.warning(f"Could not determine tenant for phone number: {To}")
            # Return 200 to Twilio even if we can't process
            return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")
        
        # Validate Twilio signature (optional but recommended)
        # signature = request.headers.get("X-Twilio-Signature")
        # if signature:
        #     twilio_client = TwilioSmsClient()
        #     if not twilio_client.validate_webhook_signature(str(request.url), dict(request.form()), signature):
        #         raise HTTPException(status_code=403, detail="Invalid signature")
        
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


async def _get_tenant_from_phone_number(
    phone_number: str,
    account_sid: str,
    db: AsyncSession,
) -> int | None:
    """Get tenant ID from phone number or account SID.
    
    Args:
        phone_number: Twilio phone number
        account_sid: Twilio account SID
        db: Database session
        
    Returns:
        Tenant ID or None if not found
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
        return config.tenant_id
    
    # Try to find by account SID
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.twilio_account_sid == account_sid
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if config:
        return config.tenant_id
    
    return None

