"""Voxie webhook endpoints for SMS."""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.domain.services.sms_service import SmsService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.persistence.database import get_db
from app.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def voxie_health() -> JSONResponse:
    """Health check endpoint for Voxie webhook verification."""
    return JSONResponse(content={"status": "ok", "provider": "voxie"})


@router.post("/sms/inbound")
async def inbound_sms_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle inbound SMS webhook from Voxie.

    Voxie sends CloudEvents format webhooks with the following structure:
    - specversion: "1.0"
    - id: unique event ID
    - source: event source
    - type: "com.voxie.message.received" for inbound SMS
    - datacontenttype: "application/json"
    - time: ISO 8601 timestamp
    - data: message payload

    The data payload for received messages includes:
    - team_id: Voxie team ID
    - contact_id: Contact identifier
    - message_id: Message identifier
    - channel: "sms"
    - from: Sender phone number (E.164)
    - to: Recipient phone number (E.164, Voxie number)
    - content: Message text

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        JSON response acknowledging receipt
    """
    try:
        # Log the raw request body for debugging
        raw_body = await request.body()
        logger.info(f"Voxie inbound webhook received: {raw_body.decode()}")

        # Parse CloudEvents payload
        body = await request.json()

        # Validate CloudEvents structure
        event_type = body.get("type", "")
        if event_type != "com.voxie.message.received":
            # Not an inbound message event, acknowledge and skip
            logger.debug(f"Ignoring Voxie event type: {event_type}")
            return JSONResponse(content={"status": "ignored", "type": event_type})

        # Extract message data
        data = body.get("data", {})
        from_number = data.get("from", "")
        to_number = data.get("to", "")
        message_body = data.get("content", "")
        message_id = data.get("message_id", "") or body.get("id", "")
        voxie_team_id = str(data.get("team_id", ""))

        if not from_number or not message_body:
            logger.warning(f"Missing required fields in Voxie webhook: from={from_number}")
            return JSONResponse(
                content={"status": "error", "message": "Missing required fields"},
                status_code=400,
            )

        # Validate webhook signature (optional but recommended)
        # signature = request.headers.get("Signature")
        # signature_input = request.headers.get("Signature-Input")
        # if signature:
        #     from app.infrastructure.telephony.voxie_provider import VoxieSmsProvider
        #     # Implement proper ECDSA signature validation here
        #     pass

        # Look up tenant by Voxie phone number or team ID
        tenant_id = await _get_tenant_from_voxie(to_number, voxie_team_id, db)

        if not tenant_id:
            logger.warning(f"Could not determine tenant for Voxie number: {to_number}, team: {voxie_team_id}")
            return JSONResponse(content={"status": "ok", "message": "tenant not found"})

        # Queue message for async processing
        if settings.cloud_tasks_worker_url:
            cloud_tasks = CloudTasksClient()
            await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": tenant_id,
                    "phone_number": from_number,
                    "message_body": message_body,
                    "voxie_message_id": message_id,
                    "to_number": to_number,
                    "provider": "voxie",
                },
                url=settings.cloud_tasks_worker_url,
            )
        else:
            # Fallback: process synchronously (not recommended for production)
            logger.warning("Cloud Tasks worker URL not configured, processing synchronously")
            sms_service = SmsService(db)
            await sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=from_number,
                message_body=message_body,
                provider_message_id=message_id,
            )

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing Voxie inbound SMS webhook: {e}", exc_info=True)
        # Return 200 to avoid Voxie retries
        return JSONResponse(content={"status": "error", "message": str(e)})


@router.post("/sms/status")
async def sms_status_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle SMS delivery status callback from Voxie.

    Voxie sends status events for:
    - com.voxie.message.sent: Message queued for sending
    - com.voxie.message.delivered: Message delivered
    - com.voxie.message.failed: Message failed
    - com.voxie.message.expired: Message expired

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        JSON response acknowledging receipt
    """
    try:
        body = await request.json()
        event_type = body.get("type", "")
        data = body.get("data", {})

        message_id = data.get("message_id", "") or body.get("id", "")

        # Map Voxie event types to status
        status_map = {
            "com.voxie.message.sent": "sent",
            "com.voxie.message.delivered": "delivered",
            "com.voxie.message.failed": "failed",
            "com.voxie.message.expired": "expired",
        }

        message_status = status_map.get(event_type)

        if message_status and message_id:
            # Update message metadata with delivery status
            from sqlalchemy import select
            from app.persistence.models.conversation import Message

            # Find message by Voxie message ID in metadata
            stmt = select(Message).where(
                Message.message_metadata["voxie_message_id"].astext == message_id
            )
            result = await db.execute(stmt)
            message = result.scalar_one_or_none()

            if message:
                if message.message_metadata is None:
                    message.message_metadata = {}
                message.message_metadata["delivery_status"] = message_status
                message.message_metadata["status_updated_at"] = str(datetime.now(timezone.utc))
                await db.commit()

            logger.info(f"Voxie SMS status update: MessageId={message_id}, Status={message_status}")

    except Exception as e:
        logger.error(f"Error processing Voxie SMS status callback: {e}", exc_info=True)

    # Always return 200
    return JSONResponse(content={"status": "ok"})


def _normalize_phone_variants(phone_number: str) -> list[str]:
    """Generate multiple phone number format variants for flexible matching.

    Args:
        phone_number: Original phone number

    Returns:
        List of phone number variants to try
    """
    if not phone_number:
        return []

    variants = [phone_number]

    # Clean to digits and + only
    cleaned = ''.join(c for c in phone_number if c.isdigit() or c == '+')
    if cleaned and cleaned not in variants:
        variants.append(cleaned)

    # If starts with +, also try without +
    if cleaned.startswith('+'):
        without_plus = cleaned[1:]
        if without_plus not in variants:
            variants.append(without_plus)
    else:
        # If doesn't start with +, try with + and with +1
        with_plus = f'+{cleaned}'
        if with_plus not in variants:
            variants.append(with_plus)

        # Try with +1 country code
        if not cleaned.startswith('1') and len(cleaned) == 10:
            with_country = f'+1{cleaned}'
            if with_country not in variants:
                variants.append(with_country)

    return variants


async def _get_tenant_from_voxie(
    phone_number: str,
    team_id: str,
    db: AsyncSession,
) -> int | None:
    """Get tenant ID from Voxie phone number or team ID.

    Attempts to match the phone number using multiple format variants
    to handle differences between how Voxie sends phone numbers and
    how they're stored in the database.

    Args:
        phone_number: Voxie phone number
        team_id: Voxie team ID
        db: Database session

    Returns:
        Tenant ID or None if not found
    """
    from sqlalchemy import select
    from app.persistence.models.tenant_sms_config import TenantSmsConfig

    # Generate phone number variants to try
    phone_variants = _normalize_phone_variants(phone_number)
    logger.info(f"Looking up tenant for Voxie: phone_variants={phone_variants}, team_id={team_id}")

    # Try to find tenant by phone number variants
    for variant in phone_variants:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.voxie_phone_number == variant
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            logger.info(f"Found tenant {config.tenant_id} by Voxie phone {variant}")
            return config.tenant_id

    # Try to find by Voxie team ID
    if team_id:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.voxie_team_id == team_id
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            logger.info(f"Found tenant {config.tenant_id} by Voxie team_id {team_id}")
            return config.tenant_id

    logger.warning(f"No tenant found for Voxie: phone={phone_number}, team_id={team_id}")
    return None
