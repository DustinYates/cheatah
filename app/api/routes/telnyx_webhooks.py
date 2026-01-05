"""Telnyx webhooks for AI Assistant and SMS."""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.prompt_service import PromptService
from app.domain.services.sms_service import SmsService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.persistence.database import get_db
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class TelnyxDynamicVarsRequest(BaseModel):
    """Request from Telnyx AI Assistant for dynamic variables.

    Telnyx sends call metadata when requesting dynamic variables.
    """

    call_control_id: str | None = None
    to: str | None = None  # The Telnyx number being called
    from_: str | None = None  # The caller's number
    direction: str | None = None  # "inbound" or "outbound"

    class Config:
        populate_by_name = True
        # Allow 'from' as alias since it's a Python keyword
        fields = {"from_": {"alias": "from"}}


@router.post("/dynamic-variables")
async def get_dynamic_variables(
    request: TelnyxDynamicVarsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Return dynamic variables for Telnyx AI Assistant.

    Telnyx calls this webhook to fetch variables like the system prompt (X).
    The tenant is identified by the Telnyx phone number being called.

    Args:
        request: Call metadata from Telnyx
        db: Database session

    Returns:
        Dictionary with dynamic variables, including X (the composed prompt)
    """
    to_number = request.to
    from_number = request.from_

    logger.info(
        f"Telnyx dynamic variables request",
        extra={
            "to": to_number,
            "from": from_number,
            "call_control_id": request.call_control_id,
            "direction": request.direction,
        },
    )

    if not to_number:
        logger.warning("No 'to' number in Telnyx request")
        return {"X": _get_fallback_prompt()}

    # Look up tenant by the Telnyx phone number being called
    # Normalize phone number (remove any formatting)
    normalized_to = _normalize_phone(to_number)

    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == normalized_to
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    # Also try without normalization if not found
    if not config:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.telnyx_phone_number == to_number
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

    if not config:
        logger.warning(f"No tenant found for Telnyx number: {to_number}")
        return {"X": _get_fallback_prompt()}

    tenant_id = config.tenant_id

    # Compose the voice prompt for this tenant
    prompt_service = PromptService(db)
    composed_prompt = await prompt_service.compose_prompt_voice(tenant_id)

    if not composed_prompt:
        logger.warning(f"No prompt configured for tenant {tenant_id}")
        return {"X": _get_fallback_prompt()}

    logger.info(
        f"Returning dynamic variables for tenant",
        extra={
            "tenant_id": tenant_id,
            "to": to_number,
            "prompt_length": len(composed_prompt),
        },
    )

    return {"X": composed_prompt}


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format.

    Args:
        phone: Phone number in various formats

    Returns:
        Normalized phone number
    """
    # Remove spaces, dashes, parentheses
    normalized = "".join(c for c in phone if c.isdigit() or c == "+")

    # Ensure starts with +
    if not normalized.startswith("+"):
        # Assume US number if no country code
        if len(normalized) == 10:
            normalized = "+1" + normalized
        elif len(normalized) == 11 and normalized.startswith("1"):
            normalized = "+" + normalized

    return normalized


def _get_fallback_prompt() -> str:
    """Return a generic fallback prompt when tenant cannot be identified."""
    return (
        "You are a helpful assistant. "
        "Greet the caller warmly and ask how you can help them today. "
        "Be friendly and conversational. "
        "If you cannot answer a question, offer to take their information "
        "so someone can follow up with them."
    )


# =============================================================================
# Telnyx SMS Webhooks
# =============================================================================


class TelnyxSmsPayload(BaseModel):
    """Telnyx SMS webhook payload structure."""

    direction: str | None = None
    id: str | None = None
    type: str | None = None
    text: str | None = None
    from_: dict | None = None
    to: list[dict] | None = None

    class Config:
        populate_by_name = True
        fields = {"from_": {"alias": "from"}}


class TelnyxWebhookData(BaseModel):
    """Telnyx webhook data wrapper."""

    event_type: str | None = None
    id: str | None = None
    payload: dict | None = None


class TelnyxWebhookRequest(BaseModel):
    """Telnyx webhook request structure."""

    data: TelnyxWebhookData | None = None


@router.post("/inbound")
async def telnyx_inbound_sms_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle inbound SMS webhook from Telnyx.

    Telnyx sends webhooks as JSON with the following structure:
    {
        "data": {
            "event_type": "message.received",
            "id": "event-id",
            "payload": {
                "direction": "inbound",
                "from": {"phone_number": "+1234567890"},
                "to": [{"phone_number": "+0987654321"}],
                "text": "Message content",
                "id": "message-id",
                ...
            }
        }
    }

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        JSON response with 200 status
    """
    try:
        # Parse JSON body
        body = await request.json()

        logger.info(
            "Telnyx SMS webhook received",
            extra={"event_type": body.get("data", {}).get("event_type")},
        )

        data = body.get("data", {})
        event_type = data.get("event_type", "")
        payload = data.get("payload", {})

        # Only process inbound messages
        if event_type != "message.received":
            # Handle delivery status updates
            if event_type in ("message.sent", "message.delivered", "message.failed"):
                await _handle_telnyx_delivery_status(event_type, payload, db)
            return JSONResponse(content={"status": "ok"})

        # Extract message details
        from_info = payload.get("from", {})
        to_list = payload.get("to", [])

        from_number = from_info.get("phone_number", "")
        to_number = to_list[0].get("phone_number", "") if to_list else ""
        message_body = payload.get("text", "")
        message_id = payload.get("id", "")

        if not from_number or not to_number:
            logger.warning("Missing phone numbers in Telnyx webhook")
            return JSONResponse(content={"status": "ok"})

        # Look up tenant by Telnyx phone number
        tenant_id = await _get_tenant_from_telnyx_number(to_number, db)

        if not tenant_id:
            logger.warning(f"Could not determine tenant for Telnyx number: {to_number}")
            return JSONResponse(content={"status": "ok"})

        # Queue message for async processing
        if settings.cloud_tasks_worker_url:
            cloud_tasks = CloudTasksClient()
            await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": tenant_id,
                    "phone_number": from_number,
                    "message_body": message_body,
                    "telnyx_message_id": message_id,
                    "to_number": to_number,
                    "provider": "telnyx",
                },
                url=settings.cloud_tasks_worker_url,
            )
        else:
            # Fallback: process synchronously
            logger.warning("Cloud Tasks not configured, processing synchronously")
            sms_service = SmsService(db)
            await sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=from_number,
                message_body=message_body,
                twilio_message_sid=message_id,  # Re-using param name for Telnyx message ID
            )

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing Telnyx SMS webhook: {e}", exc_info=True)
        # Return 200 to avoid retries
        return JSONResponse(content={"status": "error", "message": str(e)})


@router.post("/status")
async def telnyx_sms_status_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle SMS delivery status webhook from Telnyx.

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        JSON response with 200 status
    """
    try:
        body = await request.json()
        data = body.get("data", {})
        event_type = data.get("event_type", "")
        payload = data.get("payload", {})

        await _handle_telnyx_delivery_status(event_type, payload, db)

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing Telnyx status webhook: {e}", exc_info=True)
        return JSONResponse(content={"status": "error"})


async def _get_tenant_from_telnyx_number(
    phone_number: str,
    db: AsyncSession,
) -> int | None:
    """Get tenant ID from Telnyx phone number.

    Args:
        phone_number: Telnyx phone number
        db: Database session

    Returns:
        Tenant ID or None if not found
    """
    # Normalize phone number
    normalized = _normalize_phone(phone_number)

    # Try to find tenant by Telnyx phone number
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == normalized
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        return config.tenant_id

    # Also try without normalization
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == phone_number
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        return config.tenant_id

    return None


async def _handle_telnyx_delivery_status(
    event_type: str,
    payload: dict,
    db: AsyncSession,
) -> None:
    """Handle Telnyx delivery status updates.

    Args:
        event_type: Telnyx event type (message.sent, message.delivered, etc.)
        payload: Webhook payload
        db: Database session
    """
    from app.persistence.models.conversation import Message

    message_id = payload.get("id")
    if not message_id:
        return

    # Map Telnyx event to status
    status_map = {
        "message.sent": "sent",
        "message.delivered": "delivered",
        "message.failed": "failed",
        "message.finalized": "finalized",
    }
    status = status_map.get(event_type, event_type)

    # Find message by Telnyx message ID in metadata
    stmt = select(Message).where(
        Message.message_metadata["telnyx_message_id"].astext == message_id
    )
    result = await db.execute(stmt)
    message = result.scalar_one_or_none()

    if message:
        if message.message_metadata is None:
            message.message_metadata = {}
        message.message_metadata["delivery_status"] = status
        message.message_metadata["status_updated_at"] = str(datetime.now(timezone.utc))

        # Add error info if failed
        if event_type == "message.failed":
            errors = payload.get("errors", [])
            if errors:
                message.message_metadata["delivery_error"] = errors[0].get("detail", "Unknown error")

        await db.commit()

    logger.info(f"Telnyx status update: message_id={message_id}, status={status}")
