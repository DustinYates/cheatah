"""Telnyx webhooks for AI Assistant and SMS."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_, select, cast, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.domain.services.sms_service import SmsService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.redis import redis_client
from app.persistence.database import get_db
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.settings import settings
from app.core.phone import normalize_phone_for_dedup

logger = logging.getLogger(__name__)

# Maximum age in seconds for Telnyx webhook timestamps (5 minutes)
TELNYX_TIMESTAMP_MAX_AGE = 300

# TTL for message deduplication (5 minutes - enough to handle retries)
MESSAGE_DEDUP_TTL_SECONDS = 300

# TTL for event ID-based dedup (10 minutes - prevents processing same webhook twice)
EVENT_DEDUP_TTL_SECONDS = 600

# TTL for phone-based registration SMS dedup (3 minutes - matches promise_fulfillment TTL)
# This prevents duplicate SMS when multiple webhook events arrive for the same call
PHONE_SMS_DEDUP_TTL_SECONDS = 180

# Voice call event types from Telnyx (any call.* event is a voice interaction)
VOICE_EVENT_TYPES = {
    "call.initiated",
    "call.answered",
    "call.hangup",
    "call.conversation.ended",
    "call.conversation_insights.generated",
}

# SMS/text event types from Telnyx (any message.* event is an SMS interaction)
SMS_EVENT_TYPES = {
    "message.received",
    "message.sent",
    "message.delivered",
    "message.failed",
    "message.finalized",
}


def _verify_telnyx_webhook(request: Request) -> bool:
    """Verify Telnyx webhook signature and timestamp.

    Telnyx webhooks include:
    - telnyx-signature-ed25519: ED25519 signature
    - telnyx-timestamp: Unix timestamp when the webhook was sent

    This function validates:
    1. Required headers are present
    2. Timestamp is recent (prevents replay attacks)

    Note: Full cryptographic signature verification requires the Telnyx SDK
    or PyNaCl. This implementation provides timestamp-based replay protection.

    Args:
        request: FastAPI request

    Returns:
        True if verification passes, False otherwise
    """
    signature = request.headers.get("telnyx-signature-ed25519", "")
    timestamp_str = request.headers.get("telnyx-timestamp", "")

    # Check for required headers
    if not signature or not timestamp_str:
        logger.warning(
            "Missing Telnyx webhook headers",
            extra={"has_signature": bool(signature), "has_timestamp": bool(timestamp_str)},
        )
        return False

    # Validate timestamp is recent (prevents replay attacks)
    try:
        webhook_timestamp = int(timestamp_str)
        current_timestamp = int(time.time())
        age = current_timestamp - webhook_timestamp

        if age > TELNYX_TIMESTAMP_MAX_AGE:
            logger.warning(
                f"Telnyx webhook timestamp too old: {age}s (max {TELNYX_TIMESTAMP_MAX_AGE}s)"
            )
            return False

        if age < -60:  # Allow 1 minute clock skew into the future
            logger.warning(f"Telnyx webhook timestamp in future: {-age}s")
            return False

    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid Telnyx timestamp format: {timestamp_str}, error: {e}")
        return False

    return True

router = APIRouter()


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


async def _detect_language_from_phone(
    to_number: str,
    db: AsyncSession,
) -> str | None:
    """Detect call language based on which phone number received the call.

    The voice_phone_number field is used for Spanish lines, while telnyx_phone_number
    is typically the English line.

    Args:
        to_number: The phone number that received the call
        db: Database session

    Returns:
        'spanish', 'english', or None if unable to determine
    """
    if not to_number:
        return None

    normalized_to = _normalize_phone(to_number)

    # Check if this number matches the voice_phone_number (Spanish line)
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.voice_phone_number == normalized_to
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        logger.info(f"Call to voice_phone_number {to_number} detected as Spanish")
        return "spanish"

    # Also try without normalization
    if not config:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.voice_phone_number == to_number
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            logger.info(f"Call to voice_phone_number {to_number} detected as Spanish (unnormalized)")
            return "spanish"

    # Check if this number matches the telnyx_phone_number (English line)
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == normalized_to
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        logger.info(f"Call to telnyx_phone_number {to_number} detected as English")
        return "english"

    # Also try without normalization
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == to_number
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        logger.info(f"Call to telnyx_phone_number {to_number} detected as English (unnormalized)")
        return "english"

    logger.info(f"Could not determine language for phone number {to_number}")
    return None


async def _sync_lead_to_contact(
    db: AsyncSession,
    tenant_id: int,
    lead: "Lead",
    phone: str | None = None,
    email: str | None = None,
    name: str | None = None,
) -> int | None:
    """Sync lead information to a matching contact, creating one if needed.

    Finds a contact by phone or email and updates it with the lead's information.
    If no contact exists and the lead has sufficient info, creates a new contact.

    Args:
        db: Database session
        tenant_id: Tenant ID
        lead: The lead to sync from
        phone: Phone number (normalized)
        email: Email address
        name: Contact name

    Returns:
        Contact ID if found/created, None otherwise
    """
    from app.persistence.models.contact import Contact

    # Use lead fields if not provided
    phone = phone or lead.phone
    email = email or lead.email
    name = name or lead.name

    if not phone and not email:
        return None

    # Find existing contact by phone OR email
    contact = None

    if phone:
        result = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.phone == phone,
                Contact.deleted_at.is_(None),
            ).order_by(Contact.created_at.desc()).limit(1)
        )
        contact = result.scalar_one_or_none()

    if not contact and email:
        result = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.email == email,
                Contact.deleted_at.is_(None),
            ).order_by(Contact.created_at.desc()).limit(1)
        )
        contact = result.scalar_one_or_none()

    if contact:
        # Update existing contact with new information (overwrite, not just fill missing)
        updated = False
        if name and name != contact.name and not name.startswith("Caller ") and not name.startswith("SMS Contact "):
            contact.name = name
            updated = True
        if email and email != contact.email:
            contact.email = email
            updated = True
        if phone and phone != contact.phone:
            contact.phone = phone
            updated = True

        if updated:
            logger.info(f"Updated contact {contact.id} from lead {lead.id}: name={name}, email={email}, phone={phone}")
    else:
        # Create new contact if we have enough info (at least name + phone or email)
        if name and (phone or email) and not name.startswith("Caller ") and not name.startswith("SMS Contact "):
            contact = Contact(
                tenant_id=tenant_id,
                name=name,
                phone=phone,
                email=email,
                source="lead_conversion",
            )
            db.add(contact)
            await db.flush()
            logger.info(f"Created new contact {contact.id} from lead {lead.id}: name={name}, email={email}, phone={phone}")

    # Link lead to contact
    if contact and lead.contact_id != contact.id:
        lead.contact_id = contact.id

    return contact.id if contact else None


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


@router.post("/sms/inbound")
@router.post("/inbound")  # Alternate path for backwards compatibility
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
        # Verify Telnyx webhook signature in production
        if settings.environment == "production":
            if not _verify_telnyx_webhook(request):
                logger.warning("Invalid Telnyx webhook signature - rejecting request")
                raise HTTPException(status_code=403, detail="Invalid webhook signature")
        else:
            # Log warning in development but don't block
            if not _verify_telnyx_webhook(request):
                logger.warning("Invalid Telnyx webhook signature (ignored in dev)")

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

        # Deduplicate by message_id to prevent processing same message twice
        # (handles Telnyx retries, webhook replay attacks, etc.)
        if message_id:
            dedup_key = f"sms_msg_processed:{message_id}"
            if not await redis_client.setnx(dedup_key, "1", ttl=MESSAGE_DEDUP_TTL_SECONDS):
                # MONITORING: Log duplicate webhook with structured data for alerting
                logger.warning(
                    "[DUPLICATE_WEBHOOK] Duplicate inbound SMS webhook ignored",
                    extra={
                        "event_type": "duplicate_webhook_blocked",
                        "provider": "telnyx",
                        "message_id": message_id,
                        "from_number": from_number,
                        "to_number": to_number,
                    },
                )
                return JSONResponse(content={"status": "ok"})

        if not from_number or not to_number:
            logger.warning("Missing phone numbers in Telnyx webhook")
            return JSONResponse(content={"status": "ok"})

        # Look up tenant by Telnyx phone number
        logger.info(f"Looking up tenant for Telnyx number: {to_number}")
        tenant_id = await _get_tenant_from_telnyx_number(to_number, db)

        if not tenant_id:
            logger.warning(f"Could not determine tenant for Telnyx number: {to_number}")
            return JSONResponse(content={"status": "ok"})

        logger.info(f"Found tenant_id={tenant_id} for Telnyx number: {to_number}")

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
            result = await sms_service.process_inbound_sms(
                tenant_id=tenant_id,
                phone_number=from_number,
                message_body=message_body,
                twilio_message_sid=message_id,  # Re-using param name for Telnyx message ID
            )
            logger.info(f"SMS processed for tenant_id={tenant_id}, response_sent={bool(result.message_sid)}")

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing Telnyx SMS webhook: {e}", exc_info=True)
        # Return 200 to avoid retries
        return JSONResponse(content={"status": "error", "message": str(e)})


@router.post("/sms/status")
@router.post("/status")  # Alternate path for backwards compatibility
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
        # Verify Telnyx webhook signature in production
        if settings.environment == "production":
            if not _verify_telnyx_webhook(request):
                logger.warning("Invalid Telnyx status webhook signature - rejecting")
                raise HTTPException(status_code=403, detail="Invalid webhook signature")

        body = await request.json()
        data = body.get("data", {})
        event_type = data.get("event_type", "")
        payload = data.get("payload", {})

        await _handle_telnyx_delivery_status(event_type, payload, db)

        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing Telnyx status webhook: {e}", exc_info=True)
        return JSONResponse(content={"status": "error"})


async def _send_sms_immediately(
    db: AsyncSession,
    tenant_id: int,
    phone: str,
    caller_name: str | None,
    summary: str | None,
    caller_intent: str | None,
    transcript: str | None,
    conversation_id: int,
    redis_dedup_key: str | None,
) -> None:
    """Send SMS registration link immediately (fallback when delayed send fails).

    Args:
        db: Database session
        tenant_id: Tenant ID
        phone: Customer phone number
        caller_name: Customer name
        summary: Conversation summary
        caller_intent: Caller intent
        transcript: Conversation transcript
        conversation_id: Conversation ID
        redis_dedup_key: Redis dedup key to release on failure
    """
    from app.domain.services.promise_detector import DetectedPromise
    from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService

    try:
        promise = DetectedPromise(
            asset_type="registration_link",
            confidence=0.9,
            original_text=summary or "User requested registration information via SMS",
        )

        ai_response_text = f"{summary or ''}\n{caller_intent or ''}\n{transcript or ''}"
        logger.info("=" * 60)
        logger.info("[FALLBACK] SENDING SMS REGISTRATION LINK (IMMEDIATE)")
        logger.info(f"Tenant: {tenant_id}, Phone: {phone}, Name: {caller_name}")
        logger.info(f"Summary (first 200 chars): {(summary or 'NONE')[:200]}")
        logger.info("=" * 60)

        fulfillment_service = PromiseFulfillmentService(db)
        result = await fulfillment_service.fulfill_promise(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            promise=promise,
            phone=phone,
            name=caller_name,
            ai_response=ai_response_text,
        )

        logger.info(
            f"[FALLBACK] SMS registration link result - tenant_id={tenant_id}, "
            f"status={result.get('status')}, phone={phone}"
        )

        # Release Redis lock if send failed
        if result.get("status") != "sent" and redis_dedup_key:
            try:
                await redis_client.delete(redis_dedup_key)
                logger.info(f"[FALLBACK] Released Redis dedup lock: {redis_dedup_key}")
            except Exception as redis_err:
                logger.warning(f"[FALLBACK] Failed to release Redis dedup lock: {redis_err}")

    except Exception as e:
        logger.error(f"[FALLBACK] Failed to send SMS registration link: {e}", exc_info=True)
        if redis_dedup_key:
            try:
                await redis_client.delete(redis_dedup_key)
            except Exception:
                pass


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

    # Try to find tenant by Telnyx phone number OR voice phone number (for Spanish line etc.)
    # Use .limit(1) to handle cases where multiple configs match (e.g., same number in different columns)
    stmt = select(TenantSmsConfig).where(
        or_(
            TenantSmsConfig.telnyx_phone_number == normalized,
            TenantSmsConfig.voice_phone_number == normalized,
        )
    ).limit(1)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        logger.info(f"Found tenant {config.tenant_id} for phone {phone_number}")
        return config.tenant_id

    # Also try without normalization
    stmt = select(TenantSmsConfig).where(
        or_(
            TenantSmsConfig.telnyx_phone_number == phone_number,
            TenantSmsConfig.voice_phone_number == phone_number,
        )
    ).limit(1)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config:
        logger.info(f"Found tenant {config.tenant_id} for phone {phone_number} (unnormalized)")
        return config.tenant_id

    logger.warning(f"No tenant found for phone {phone_number}")
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
    # Use cast() instead of .astext for generic JSON columns
    stmt = select(Message).where(
        cast(Message.message_metadata["telnyx_message_id"], String) == message_id
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


# =============================================================================
# Telnyx AI Assistant Call Completion / Insights Webhook
# =============================================================================


@router.post("/ai-call-complete")
async def telnyx_ai_call_complete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle call completion and insights webhooks from Telnyx AI Assistant.

    This endpoint receives data when:
    - An AI Assistant call ends (call.conversation.ended)
    - Conversation insights are generated (call.conversation_insights.generated)
    - Post-call insights webhook fires from Insight Groups

    The data is stored in the database and can trigger lead creation.

    Args:
        request: FastAPI request with call data
        db: Database session

    Returns:
        JSON response with 200 status
    """
    from app.persistence.models.call import Call
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.contact import Contact
    from app.persistence.models.lead import Lead
    import json

    try:
        # Try JSON first, fall back to form data
        content_type = request.headers.get("content-type", "")
        body = {}

        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception as e:
                logger.warning(f"Failed to parse JSON body: {e}")
                raw = await request.body()
                logger.info(f"Raw body (non-JSON): {raw[:500]}")
        elif "form" in content_type:
            form_data = await request.form()
            body = dict(form_data)
            logger.info(f"Received form data: {body}")
        else:
            # Try JSON anyway
            try:
                body = await request.json()
            except Exception:
                raw = await request.body()
                logger.info(f"Raw body (unknown content-type {content_type}): {raw[:500]}")
                # Try to parse as JSON if it looks like JSON
                if raw and raw.strip().startswith(b'{'):
                    try:
                        body = json.loads(raw)
                    except Exception:
                        pass

        # Log full payload for debugging (in message for Cloud Run visibility)
        body_str = json.dumps(body)[:3000] if isinstance(body, dict) else str(body)[:500]
        logger.info(f"Telnyx AI webhook payload: {body_str}")

        # ========== CALL WEBHOOK RECEIVED ==========
        logger.info("=" * 60)
        logger.info("TELNYX AI CALL WEBHOOK RECEIVED")
        logger.info("=" * 60)

        # Telnyx webhooks typically have: {data: {event_type: ..., payload: {...}}}
        # But Insights webhooks have: {event_type: ..., payload: {metadata: {to, from, ...}, results: [...]}}
        data = body.get("data", body)
        event_type = data.get("event_type") or body.get("event_type") or "unknown"
        payload = data.get("payload") or body.get("payload") or data

        logger.info(f"Telnyx event type: {event_type}")

        # EVENT-BASED DEDUP: Prevent processing the same webhook event twice
        # This is the primary dedup layer - uses the Telnyx event ID with short TTL
        webhook_event_id = (
            data.get("id")  # Standard Telnyx event ID
            or body.get("id")
            or (payload.get("event_id") if isinstance(payload, dict) else None)
        )
        if webhook_event_id:
            event_dedup_key = f"telnyx_event:{webhook_event_id}"
            try:
                await redis_client.connect()
                is_new_event = await redis_client.setnx(event_dedup_key, "1", ttl=EVENT_DEDUP_TTL_SECONDS)
                if not is_new_event:
                    logger.info(f"[EVENT-DEDUP] Duplicate webhook event ignored: {webhook_event_id}")
                    return JSONResponse(content={"status": "ok", "message": "duplicate event"})
                logger.info(f"[EVENT-DEDUP] New event processing: {webhook_event_id}")
            except Exception as e:
                logger.warning(f"[EVENT-DEDUP] Redis check failed, continuing: {e}")

        # For insights webhook, metadata contains call info
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        conversation = body.get("conversation", {}) or data.get("conversation", {})

        # Extract call details - try multiple possible field names
        # TeXML status callbacks use PascalCase (CallControlId, From, To, etc.)
        call_id = (
            body.get("CallControlId")  # TeXML PascalCase
            or body.get("CallSessionId")
            or body.get("CallSid")
            or metadata.get("call_control_id")
            or metadata.get("call_session_id")
            or payload.get("conversation_id")
            or payload.get("call_control_id")
            or payload.get("call_id")
            or data.get("call_control_id")
            or data.get("CallControlId")
            or data.get("conversation_id")
            or body.get("conversation_id")
            or conversation.get("id")
            or data.get("id")
            or ""
        )

        # Extract assistant ID to distinguish voice vs text assistant
        assistant_id = (
            body.get("assistant_id")
            or payload.get("assistant_id")
            or metadata.get("assistant_id")
            or data.get("assistant_id")
            or conversation.get("assistant_id")
            or ""
        )
        logger.info(f"Telnyx assistant_id: {assistant_id}")

        # [SMS-DEBUG] Log all potential phone number sources for transfer debugging
        logger.info(
            f"[SMS-DEBUG] Phone number sources - "
            f"body.From={body.get('From')}, body.Caller={body.get('Caller')}, "
            f"metadata.from={metadata.get('from')}, metadata.telnyx_end_user_target={metadata.get('telnyx_end_user_target')}, "
            f"payload.from={payload.get('from') if isinstance(payload, dict) else 'N/A'}, "
            f"conversation.end_user_target={conversation.get('end_user_target')}, "
            f"conversation.from={conversation.get('from')}"
        )

        # Phone numbers - TeXML uses PascalCase: From, To
        from_number = (
            body.get("From")  # TeXML PascalCase
            or body.get("Caller")
            or metadata.get("from")
            or metadata.get("telnyx_end_user_target")
            or payload.get("from")
            or payload.get("From")
            or payload.get("caller_id")
            or payload.get("end_user_target")
            or data.get("from")
            or data.get("From")
            or data.get("end_user_target")
            or body.get("end_user_target")
            or conversation.get("end_user_target")
            or conversation.get("from")
            or ""
        )
        to_number = (
            body.get("To")  # TeXML PascalCase
            or body.get("Called")
            or metadata.get("to")
            or metadata.get("telnyx_agent_target")
            or payload.get("to")
            or payload.get("To")
            or payload.get("called_number")
            or payload.get("agent_target")
            or data.get("to")
            or data.get("To")
            or data.get("agent_target")
            or body.get("agent_target")
            or conversation.get("agent_target")
            or conversation.get("to")
            or ""
        )

        # ========== PHONE NUMBERS EXTRACTED ==========
        logger.info(f"CALL PHONE NUMBERS: from={from_number}, to={to_number}")
        logger.info(f"EVENT TYPE: {event_type}")

        # Duration - log available fields to help debug missing duration
        logger.info(f"Telnyx duration debug - payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not dict'}")
        logger.info(f"Telnyx duration debug - data keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
        logger.info(f"Telnyx duration debug - metadata keys: {list(metadata.keys()) if isinstance(metadata, dict) else 'not dict'}")
        logger.info(f"Telnyx duration debug - conversation keys: {list(conversation.keys()) if isinstance(conversation, dict) else 'not dict'}")
        logger.info(f"Telnyx duration debug - full body: {json.dumps(body)[:2000] if isinstance(body, dict) else str(body)[:500]}")

        # Try multiple possible field names for duration (in seconds)
        # TeXML uses PascalCase: CallDuration
        duration = (
            body.get("CallDuration")  # TeXML PascalCase - this is the main one!
            or body.get("Duration")
            or payload.get("CallDuration")
            or payload.get("duration")
            or payload.get("call_duration")
            or payload.get("call_length")
            or payload.get("duration_seconds")
            or payload.get("total_duration")
            or payload.get("duration_secs")
            or data.get("CallDuration")
            or data.get("duration")
            or data.get("call_duration")
            or data.get("duration_seconds")
            or metadata.get("duration")
            or metadata.get("call_duration")
            or conversation.get("duration")
            or conversation.get("duration_seconds")
            or 0
        )

        # If no direct duration, try to calculate from timestamps
        call_start_time = None
        call_end_time = None
        if not duration:
            # Check body first for PascalCase TeXML fields
            call_start_time = body.get("AnsweredTime") or body.get("StartTime")
            call_end_time = body.get("EndTime") or body.get("Timestamp")

            # Look for start/end timestamps in various locations
            for source in [payload, data, metadata, conversation]:
                if isinstance(source, dict):
                    if not call_start_time:
                        call_start_time = (
                            source.get("AnsweredTime") or source.get("StartTime") or
                            source.get("start_time") or source.get("started_at") or
                            source.get("call_start_time") or source.get("begin_time")
                        )
                    if not call_end_time:
                        call_end_time = (
                            source.get("EndTime") or source.get("Timestamp") or
                            source.get("end_time") or source.get("ended_at") or
                            source.get("call_end_time") or source.get("hangup_time")
                        )

            if call_start_time and call_end_time:
                try:
                    from dateutil import parser as date_parser
                    start_dt = date_parser.parse(str(call_start_time))
                    end_dt = date_parser.parse(str(call_end_time))
                    duration = int((end_dt - start_dt).total_seconds())
                    logger.info(f"Telnyx duration calculated from timestamps: {duration}s (start={call_start_time}, end={call_end_time})")
                except Exception as e:
                    logger.warning(f"Failed to parse timestamps for duration: {e}")

        logger.info(f"Telnyx duration extracted: {duration}")

        # Transcript and insights - try multiple formats
        transcript = ""
        summary = ""

        # Check for transcript in various locations
        if "transcript" in payload:
            transcript = payload["transcript"]
        elif "conversation" in payload:
            transcript = payload["conversation"]
        elif "messages" in payload:
            # List of message objects
            msgs = payload["messages"]
            if isinstance(msgs, list):
                transcript = "\n".join(
                    f"{m.get('role', 'unknown')}: {m.get('content', m.get('text', ''))}"
                    for m in msgs
                )

        # Check for insights data - Telnyx Insights webhook uses "results" array
        # Multiple insights: summary, caller_name, caller_email, caller_intent
        results = payload.get("results", [])
        caller_name = ""
        caller_email = ""
        caller_intent = ""
        import re

        # Log raw results for debugging name extraction issues
        logger.info(f"Telnyx insights results: {json.dumps(results)[:1500] if results else 'empty'}")

        if isinstance(results, list) and results:
            for result_item in results:
                if isinstance(result_item, dict):
                    # Check if result has a "name" field that identifies the insight type
                    insight_name = (
                        result_item.get("name", "")
                        or result_item.get("insight_name", "")
                        or result_item.get("type", "")
                        or result_item.get("insight_type", "")
                        or ""
                    ).lower()
                    result_text = (
                        result_item.get("result", "")
                        or result_item.get("value", "")
                        or result_item.get("text", "")
                        or ""
                    )

                    logger.info(f"Telnyx insight item: name='{insight_name}', result='{result_text[:100] if result_text else ''}'")

                    # If insight has an identifying name, use it directly
                    if insight_name:
                        result_clean = result_text.strip() if result_text else ""
                        result_lower = result_clean.lower()

                        # Check for name-related insights
                        if ("name" in insight_name and "email" not in insight_name) or insight_name in ["caller_name", "customer_name", "contact_name"]:
                            if result_clean and result_lower not in ["unknown", "none", "not provided", "n/a", ""]:
                                caller_name = result_clean
                                logger.info(f"Extracted caller_name from labeled insight '{insight_name}': {caller_name}")
                        # Check for email-related insights
                        elif "email" in insight_name:
                            if result_text and "@" in result_text:
                                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', result_text)
                                if email_match:
                                    caller_email = email_match.group(0)
                                    logger.info(f"Extracted caller_email from labeled insight: {caller_email}")
                        # Check for summary/intent insights
                        elif "summary" in insight_name or "intent" in insight_name:
                            if result_clean:
                                if not summary:
                                    summary = result_clean
                                elif not caller_intent:
                                    caller_intent = result_clean
                        continue  # Skip heuristic detection for labeled insights

                elif isinstance(result_item, str):
                    result_text = result_item
                else:
                    continue

                if not result_text:
                    continue

                result_lower = result_text.lower().strip()

                # Fallback: Identify result type by content (heuristics for unlabeled results)
                # Email detection (contains @ and looks like email)
                if "@" in result_text and not caller_email:
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', result_text)
                    if email_match:
                        caller_email = email_match.group(0)
                    elif result_lower not in ["none", "unknown", "not provided", "n/a"]:
                        caller_email = result_text.strip()
                # Name detection (short text, not email, not "unknown")
                elif len(result_text) < 100 and "@" not in result_text and not caller_name:
                    if result_lower not in ["unknown", "none", "not provided", "n/a", ""]:
                        # Check if it looks like a name (not a full sentence)
                        if not any(word in result_lower for word in ["the caller", "they", "was", "were", "is", "are"]):
                            caller_name = result_text.strip()
                            logger.info(f"Extracted caller_name via heuristics: {caller_name}")
                # Intent/Summary detection (longer text)
                elif len(result_text) > 50:
                    if not summary:
                        summary = result_text
                    elif not caller_intent:
                        caller_intent = result_text

            # If we still don't have a summary, use first long result
            if not summary and results:
                first_result = results[0]
                if isinstance(first_result, dict):
                    summary = first_result.get("result", "") or first_result.get("value", "")
                elif isinstance(first_result, str):
                    summary = first_result

        # Also check for insights in other formats
        insights = payload.get("insights", {})
        if not summary:
            if isinstance(insights, dict):
                summary = insights.get("summary", "")
                if not transcript and "transcript" in insights:
                    transcript = insights["transcript"]
            elif isinstance(insights, list):
                # Multiple insights
                for insight in insights:
                    if insight.get("name") == "call_summary" or insight.get("type") == "summary":
                        summary = insight.get("value", insight.get("result", ""))
                    if insight.get("name") == "transcript":
                        transcript = insight.get("value", insight.get("result", ""))
                    if insight.get("name") == "caller_name":
                        caller_name = insight.get("value", insight.get("result", ""))
                    if insight.get("name") == "caller_email":
                        caller_email = insight.get("value", insight.get("result", ""))
                    if insight.get("name") == "caller_intent":
                        caller_intent = insight.get("value", insight.get("result", ""))

        # Also check for summary at top level
        if not summary:
            summary = payload.get("summary") or payload.get("call_summary") or data.get("summary") or ""

        recording_url = payload.get("recording_url") or payload.get("recording") or ""

        # Handle nested phone number formats
        if isinstance(from_number, dict):
            from_number = from_number.get("phone_number", "")
        if isinstance(to_number, dict):
            to_number = to_number.get("phone_number", "")

        # Handle transcript as list of messages
        if isinstance(transcript, list):
            transcript = "\n".join(
                f"{msg.get('role', 'unknown')}: {msg.get('content', msg.get('text', ''))}"
                for msg in transcript
            )

        logger.info(
            f"AI call data extracted: name={caller_name}, email={caller_email}, intent={caller_intent[:50] if caller_intent else 'none'}"
        )

        # WORKAROUND: Telnyx Insights webhooks not firing for voice calls
        # If we have no insights data, try to fetch transcript from Telnyx API directly
        if not caller_name and not caller_email and call_id and settings.telnyx_api_key:
            try:
                from app.infrastructure.telephony.telnyx_provider import TelnyxAIService
                telnyx_ai = TelnyxAIService(settings.telnyx_api_key)

                logger.info(f"No insights from webhook, fetching transcript from Telnyx API for call_control_id={call_id}")

                # Wait for Telnyx to finish writing the transcript
                # Race condition: webhook fires before transcript is fully saved
                # Increased from 2s to 5s based on production observation
                import asyncio
                await asyncio.sleep(5)

                # Find the conversation by call_control_id
                conversation = await telnyx_ai.find_conversation_by_call_control_id(call_id)

                if conversation:
                    conv_id = conversation.get("id")
                    logger.info(f"Found conversation {conv_id}, fetching messages")

                    # Retry logic for race condition - Telnyx may not have messages ready yet
                    # Increased retries and delay based on production observation
                    max_retries = 5
                    retry_delay = 3  # seconds
                    extracted = None

                    for attempt in range(max_retries):
                        # Get messages from the conversation
                        messages = await telnyx_ai.get_conversation_messages(conv_id)
                        logger.info(f"Attempt {attempt + 1}: Got {len(messages)} messages from Telnyx API")

                        if messages:
                            # Check if we have user messages (not just assistant greeting)
                            user_messages = [m for m in messages if m.get("role") == "user" and m.get("text")]
                            logger.info(f"Attempt {attempt + 1}: Found {len(user_messages)} user messages")

                            if user_messages:
                                # Log the user messages for debugging
                                for i, um in enumerate(user_messages[:3]):  # Log first 3
                                    logger.info(f"User message {i+1}: {um.get('text', '')[:100]}")

                                # Extract insights using Gemini LLM for better accuracy
                                extracted = await telnyx_ai.extract_insights_with_llm(messages)

                                # If we got a name or email, we're done
                                if extracted.get("name") or extracted.get("email"):
                                    logger.info(f"Successfully extracted data on attempt {attempt + 1}")
                                    break
                                else:
                                    logger.info(f"Attempt {attempt + 1}: LLM returned no name/email, will retry")
                            else:
                                logger.info(f"Attempt {attempt + 1}: No user messages yet, Telnyx still writing transcript")

                        # Wait before retry (unless last attempt)
                        if attempt < max_retries - 1:
                            logger.info(f"Waiting {retry_delay}s before retry...")
                            await asyncio.sleep(retry_delay)

                    if extracted:
                        # Use extracted data if we didn't get it from webhook
                        if extracted.get("name") and not caller_name:
                            caller_name = extracted["name"]
                            logger.info(f"Extracted caller_name from transcript: {caller_name}")
                        if extracted.get("email") and not caller_email:
                            caller_email = extracted["email"]
                            logger.info(f"Extracted caller_email from transcript: {caller_email}")
                        if extracted.get("intent") and not caller_intent:
                            caller_intent = extracted["intent"]
                            logger.info(f"Extracted caller_intent from transcript: {caller_intent}")
                        if extracted.get("summary") and not summary:
                            summary = extracted["summary"]
                            logger.info(f"Extracted summary from transcript (first 100 chars): {summary[:100]}")
                        if extracted.get("transcript") and not transcript:
                            transcript = extracted["transcript"]

                    logger.info(f"Final extracted data: name={caller_name}, email={caller_email}, intent={caller_intent}")
                else:
                    logger.info(f"Could not find conversation for call_control_id={call_id}")
            except Exception as e:
                logger.warning(f"Failed to fetch transcript from Telnyx API: {e}")

        # FALLBACK: Try to get transcript from our own database
        # The voice_webhooks.py stores messages in the Conversation table during the call
        if not caller_name and not caller_email and from_number:
            try:
                # Get tenant_id first (we need it for the query)
                temp_tenant_id = await _get_tenant_from_telnyx_number(to_number, db) if to_number else None
                if temp_tenant_id:
                    from app.persistence.models.conversation import Conversation, Message

                    normalized_phone = _normalize_phone(from_number)
                    time_window = datetime.utcnow() - timedelta(minutes=10)

                    # Find the most recent voice conversation for this phone
                    conv_result = await db.execute(
                        select(Conversation).where(
                            Conversation.tenant_id == temp_tenant_id,
                            Conversation.phone_number == normalized_phone,
                            Conversation.channel == "voice",
                            Conversation.created_at >= time_window,
                        ).order_by(Conversation.created_at.desc()).limit(1)
                    )
                    voice_conv = conv_result.scalar_one_or_none()

                    if voice_conv:
                        logger.info(f"Found voice conversation {voice_conv.id} in database for phone {normalized_phone}")

                        # Get messages from this conversation
                        msg_result = await db.execute(
                            select(Message).where(
                                Message.conversation_id == voice_conv.id
                            ).order_by(Message.sequence_number)
                        )
                        messages = msg_result.scalars().all()

                        if messages:
                            # Build transcript from messages
                            transcript_lines = []
                            user_text = ""
                            for msg in messages:
                                role = "User" if msg.role == "user" else "Assistant"
                                transcript_lines.append(f"{role}: {msg.content}")
                                if msg.role == "user":
                                    user_text += " " + msg.content

                            if not transcript:
                                transcript = "\n".join(transcript_lines)

                            logger.info(f"Built transcript from {len(messages)} messages in database")

                            # Extract name from user text using regex patterns
                            import re
                            name_patterns = [
                                r"(?:I'?m|I am|my name is|this is|im|name's|it's)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
                                r"(?:call me|you can call me)\s+([a-zA-Z]+)",
                            ]
                            for pattern in name_patterns:
                                match = re.search(pattern, user_text, re.IGNORECASE)
                                if match:
                                    potential_name = match.group(1).strip()
                                    # Filter out common false positives
                                    false_positives = ["good", "great", "fine", "okay", "ok", "yes", "no", "well", "here", "there", "sure", "interested", "calling", "looking"]
                                    if potential_name.lower() not in false_positives and len(potential_name) > 1:
                                        caller_name = potential_name.title()
                                        logger.info(f"Extracted caller_name from database transcript: {caller_name}")
                                        break

                            # Extract email from user text
                            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                            email_match = re.search(email_pattern, user_text)
                            if email_match and not caller_email:
                                caller_email = email_match.group(0)
                                logger.info(f"Extracted caller_email from database transcript: {caller_email}")
                    else:
                        logger.info(f"No recent voice conversation found in database for phone {normalized_phone}")
            except Exception as e:
                logger.warning(f"Failed to extract from database: {e}")

        if not to_number:
            logger.warning("No 'to' number in AI call webhook")
            return JSONResponse(content={"status": "ok", "message": "no to_number"})

        # Look up tenant by phone number
        tenant_id = await _get_tenant_from_telnyx_number(to_number, db)

        if not tenant_id:
            # Try from_number as fallback (for outbound calls)
            if from_number:
                tenant_id = await _get_tenant_from_telnyx_number(from_number, db)

        if not tenant_id:
            logger.warning(f"Could not determine tenant for call: to={to_number}, from={from_number}")
            return JSONResponse(content={"status": "ok", "message": "tenant_not_found"})

        logger.info(f"Found tenant_id={tenant_id} for AI call")

        # Determine if this is a voice call vs SMS/chat interaction
        # PRIMARY: Use event_type as the definitive classifier
        # SECONDARY: Use duration only for capturing call metrics, not classification

        # Normalize event_type for comparison
        normalized_event_type = event_type.lower().strip() if event_type else ""

        # Check if event type indicates voice call (any call.* event)
        is_voice_event = (
            normalized_event_type.startswith("call.") or
            normalized_event_type in VOICE_EVENT_TYPES
        )

        # Check if event type indicates SMS/text (any message.* event)
        is_sms_event = (
            normalized_event_type.startswith("message.") or
            normalized_event_type in SMS_EVENT_TYPES
        )

        # Voice signals (used for metrics/logging, not classification)
        has_voice_signals = (
            bool(duration and int(duration) > 0) or
            bool(recording_url)
        )

        # Final classification based on event type (not duration)
        if is_sms_event:
            is_voice_call = False
            is_sms_interaction = True
        elif is_voice_event:
            is_voice_call = True
            is_sms_interaction = False
        else:
            # Unknown event type - check metadata for channel info before defaulting
            conversation_channel = metadata.get("telnyx_conversation_channel", "")
            if conversation_channel == "phone_call":
                logger.info(f"Unknown event type '{event_type}', but telnyx_conversation_channel=phone_call - classifying as voice")
                is_voice_call = True
                is_sms_interaction = False
            else:
                logger.warning(f"Unknown event type '{event_type}', defaulting to SMS classification")
                is_voice_call = False
                is_sms_interaction = True

        logger.info(
            f"Channel classification: is_voice_call={is_voice_call}, is_sms_interaction={is_sms_interaction}, "
            f"event_type={event_type}, is_voice_event={is_voice_event}, is_sms_event={is_sms_event}, "
            f"has_voice_signals={has_voice_signals}, duration={duration}"
        )

        if is_sms_interaction or (not is_voice_call and not call_id):
            logger.info(f"Skipping Call record creation for non-voice interaction: event_type={event_type}, call_id={call_id}, assistant_id={assistant_id}")
            # Create/update Conversation and Messages for SMS AI Assistant (for usage tracking)
            now = datetime.utcnow()
            if from_number:
                normalized_from = _normalize_phone(from_number)

                # Create or find SMS conversation for usage tracking
                from app.persistence.models.conversation import Conversation, Message
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.phone_number == normalized_from,
                        Conversation.channel == "sms",
                    ).order_by(Conversation.created_at.desc()).limit(1)
                )
                sms_conversation = conv_result.scalar_one_or_none()

                if not sms_conversation:
                    sms_conversation = Conversation(
                        tenant_id=tenant_id,
                        channel="sms",
                        phone_number=normalized_from,
                        external_id=f"telnyx_sms_{now.timestamp()}",
                    )
                    db.add(sms_conversation)
                    await db.flush()
                    logger.info(f"Created SMS conversation for usage tracking: id={sms_conversation.id}")

                # Add messages from the SMS interaction
                # Try to fetch actual conversation messages from Telnyx API
                actual_messages_stored = False
                actual_assistant_transcript = None  # Will hold real bot messages for registration link
                ai_sent_registration_url = False  # Track if AI already sent registration URL
                telnyx_conv_id = conversation.get("id")  # Telnyx conversation ID from webhook

                # Try multiple paths to find conversation ID for fetching messages
                telnyx_conv_id = (
                    conversation.get("id")
                    or payload.get("conversation_id")
                    or data.get("conversation_id")
                    or body.get("conversation_id")
                    or metadata.get("conversation_id")
                    or call_id  # Fall back to call_id which might be conversation_id
                )

                # Debug logging for conversation ID extraction
                logger.info(f"[SMS-MESSAGES] Attempting to fetch actual messages")
                logger.info(f"[SMS-MESSAGES] conversation dict: {json.dumps(conversation)[:500] if conversation else 'empty'}")
                logger.info(f"[SMS-MESSAGES] payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'not dict'}")
                logger.info(f"[SMS-MESSAGES] telnyx_conv_id={telnyx_conv_id}, call_id={call_id}, has_api_key={bool(settings.telnyx_api_key)}")

                if not telnyx_conv_id:
                    logger.warning(f"[SMS-MESSAGES] No conversation ID available - cannot fetch actual messages. "
                                   f"Checked: conversation.id, payload.conversation_id, data.conversation_id, body.conversation_id, metadata.conversation_id, call_id")
                elif not settings.telnyx_api_key:
                    logger.warning(f"[SMS-MESSAGES] No Telnyx API key configured - cannot fetch actual messages")

                if telnyx_conv_id and settings.telnyx_api_key:
                    try:
                        from app.infrastructure.telephony.telnyx_provider import TelnyxAIService
                        sms_telnyx_ai = TelnyxAIService(settings.telnyx_api_key)

                        logger.info(f"[SMS-MESSAGES] Fetching actual SMS messages from Telnyx for conv_id={telnyx_conv_id}")
                        actual_messages = await sms_telnyx_ai.get_conversation_messages(telnyx_conv_id)
                        logger.info(f"[SMS-MESSAGES] Telnyx API returned {len(actual_messages) if actual_messages else 0} messages")

                        if actual_messages:
                            # Log sample message structure for debugging
                            if actual_messages:
                                sample_msg = actual_messages[0]
                                logger.info(f"[SMS-MESSAGES] Sample message keys: {list(sample_msg.keys())}, sample: {str(sample_msg)[:500]}")

                            # Get next sequence number
                            msg_result = await db.execute(
                                select(Message).where(
                                    Message.conversation_id == sms_conversation.id
                                ).order_by(Message.sequence_number.desc()).limit(1)
                            )
                            last_msg = msg_result.scalar_one_or_none()
                            next_seq = (last_msg.sequence_number + 1) if last_msg else 1

                            # Store each actual message individually
                            # Filter out tool call results and API error responses
                            for msg in actual_messages:
                                msg_role = msg.get("role", "user")
                                msg_content = msg.get("text", msg.get("content", ""))

                                # Skip tool/function messages (these are API call results)
                                if msg_role in ("tool", "function", "system"):
                                    logger.debug(f"Skipping {msg_role} message from Telnyx AI conversation")
                                    continue

                                # Skip messages that look like API error responses
                                if msg_content and msg_content.strip():
                                    content_stripped = msg_content.strip()
                                    # Check if content looks like a JSON error response
                                    if content_stripped.startswith("{") and (
                                        '"http_status"' in content_stripped
                                        or '"errors"' in content_stripped
                                        or '"error"' in content_stripped
                                        or '"http_body"' in content_stripped
                                    ):
                                        logger.warning(f"Skipping API error response from Telnyx AI conversation: {content_stripped[:200]}")
                                        continue

                                    new_msg = Message(
                                        conversation_id=sms_conversation.id,
                                        role=msg_role,
                                        content=msg_content,
                                        sequence_number=next_seq,
                                        message_metadata={"source": "telnyx_ai_assistant", "assistant_id": assistant_id},
                                    )
                                    db.add(new_msg)
                                    next_seq += 1

                            actual_messages_stored = True
                            logger.info(f"Stored {len(actual_messages)} actual SMS messages from Telnyx API: conversation_id={sms_conversation.id}")

                            # Build transcript from assistant messages for class level detection
                            # The assistant messages contain specific class recommendations like "Young Adult Level 3"
                            # Filter out error responses and tool messages
                            assistant_texts = []
                            for msg in actual_messages:
                                if msg.get("role") != "assistant":
                                    continue
                                content = msg.get("text", msg.get("content", ""))
                                if not content or not content.strip():
                                    continue
                                # Skip if it looks like an API error response
                                content_stripped = content.strip()
                                if content_stripped.startswith("{") and (
                                    '"http_status"' in content_stripped
                                    or '"errors"' in content_stripped
                                    or '"error"' in content_stripped
                                ):
                                    continue
                                assistant_texts.append(content)
                            if assistant_texts:
                                actual_assistant_transcript = "\n".join(assistant_texts)
                                logger.info(f"Built actual assistant transcript ({len(actual_assistant_transcript)} chars) for registration link")

                            # Check if AI already sent a registration URL in the conversation
                            # This prevents our fallback from sending a duplicate
                            ai_sent_registration_url = False
                            for msg in actual_messages:
                                msg_text = msg.get("text", msg.get("content", "")) or ""
                                if "britishswimschool.com" in msg_text and "register" in msg_text:
                                    ai_sent_registration_url = True
                                    logger.info(f"[SMS-AI-DEDUP] AI already sent registration URL in conversation: {msg_text[:100]}")
                                    break

                            # Extract location/level from tool_calls in conversation messages
                            # When the AI called send_registration_link, the tool_calls contain
                            # the location and level that the text summary may not mention
                            tool_call_location = None
                            tool_call_level = None
                            for msg in actual_messages:
                                tool_calls = msg.get("tool_calls")
                                if not tool_calls:
                                    continue
                                for tc in tool_calls:
                                    fn = tc.get("function", tc) if isinstance(tc, dict) else {}
                                    fn_name = fn.get("name", "")
                                    if "registration" in fn_name.lower() or "send_registration" in fn_name.lower():
                                        args = fn.get("arguments", {})
                                        if isinstance(args, str):
                                            try:
                                                args = json.loads(args)
                                            except Exception:
                                                args = {}
                                        tool_call_location = args.get("location")
                                        tool_call_level = args.get("level")
                                        logger.info(
                                            f"[SMS-TOOL-EXTRACT] Found tool call with "
                                            f"location={tool_call_location}, level={tool_call_level}"
                                        )
                                        break
                                if tool_call_location:
                                    break

                            # If we found tool call params, build a URL to inject into the text
                            tool_call_url = None
                            if tool_call_location:
                                try:
                                    from app.utils.registration_url_builder import build_registration_url
                                    tc_loc_code = _map_location_to_code(tool_call_location)
                                    tc_level_name = _normalize_level_name(tool_call_level) if tool_call_level else None
                                    if tc_loc_code:
                                        tool_call_url = build_registration_url(tc_loc_code, tc_level_name)
                                        logger.info(f"[SMS-TOOL-EXTRACT] Built URL from tool call: {tool_call_url}")
                                except Exception as e:
                                    logger.warning(f"[SMS-TOOL-EXTRACT] Failed to build URL from tool call: {e}")

                    except Exception as e:
                        logger.warning(f"Failed to fetch actual SMS messages from Telnyx API: {e}")

                # Fallback: store transcript/summary if we couldn't get actual messages
                if not actual_messages_stored and (transcript or summary):
                    logger.warning(f"[SMS-MESSAGES] Using FALLBACK - storing summary instead of actual messages. "
                                   f"actual_messages_stored={actual_messages_stored}, has_transcript={bool(transcript)}, has_summary={bool(summary)}")
                    # Get next sequence number
                    msg_result = await db.execute(
                        select(Message).where(
                            Message.conversation_id == sms_conversation.id
                        ).order_by(Message.sequence_number.desc()).limit(1)
                    )
                    last_msg = msg_result.scalar_one_or_none()
                    next_seq = (last_msg.sequence_number + 1) if last_msg else 1

                    # Add user message with transcript if available, otherwise summary
                    user_msg = Message(
                        conversation_id=sms_conversation.id,
                        role="user",
                        content=transcript or summary or "SMS interaction",
                        sequence_number=next_seq,
                        message_metadata={"source": "telnyx_ai_assistant", "assistant_id": assistant_id, "fallback": True},
                    )
                    db.add(user_msg)

                    # Add assistant response message
                    assistant_msg = Message(
                        conversation_id=sms_conversation.id,
                        role="assistant",
                        content=summary or "Response provided",
                        sequence_number=next_seq + 1,
                        message_metadata={"source": "telnyx_ai_assistant", "assistant_id": assistant_id, "fallback": True},
                    )
                    db.add(assistant_msg)
                    logger.info(f"Added SMS messages (fallback) for usage tracking: conversation_id={sms_conversation.id}")

                # Still create/update Lead from SMS AI Assistant interactions
                existing_lead = await db.execute(
                    select(Lead).where(
                        Lead.tenant_id == tenant_id,
                        Lead.phone == normalized_from,
                    ).order_by(Lead.created_at.desc()).limit(1)
                )
                lead = existing_lead.scalar_one_or_none()

                if not lead:
                    # Use phone number as fallback name if no name extracted
                    display_name = caller_name if caller_name else f"SMS Contact {normalized_from}"
                    lead = Lead(
                        tenant_id=tenant_id,
                        phone=normalized_from,
                        name=display_name,
                        email=caller_email or None,
                        status="new",
                        extra_data={"source": "sms_ai_assistant", "summary": summary},
                        conversation_id=sms_conversation.id if sms_conversation else None,
                    )
                    db.add(lead)
                    await db.flush()
                    logger.info(f"Created Lead from SMS AI interaction: phone={normalized_from}, conversation_id={sms_conversation.id if sms_conversation else None}")
                else:
                    # Update lead with new info (overwrite empty fields)
                    if caller_name and (not lead.name or lead.name.startswith("SMS Contact ")):
                        lead.name = caller_name
                    if caller_email and not lead.email:
                        lead.email = caller_email
                    # Update conversation_id if not set (link to latest SMS conversation)
                    if sms_conversation and not lead.conversation_id:
                        lead.conversation_id = sms_conversation.id
                    logger.info(f"Updated existing Lead from SMS AI interaction: id={lead.id}, conversation_id={lead.conversation_id}")

                # Sync lead info to matching contact (find/update/create contact)
                contact_id = await _sync_lead_to_contact(
                    db=db,
                    tenant_id=tenant_id,
                    lead=lead,
                    phone=normalized_from,
                    email=caller_email,
                    name=caller_name,
                )
                if contact_id:
                    logger.info(f"Synced SMS lead {lead.id} to contact {contact_id}")

                await db.commit()

                # =============================================================
                # Email Promise Detection for Telnyx SMS
                # =============================================================
                # Check if the conversation summary mentions email promises
                # and alert the tenant so they can follow up manually
                combined_text = f"{summary or ''} {caller_intent or ''}".lower()
                email_promise_patterns = [
                    "email you", "e-mail you", "send you an email", "send an email",
                    "email that", "email the", "emailing you", "i'll email",
                    "will email", "receive an email", "get that to your email",
                    "send to your email", "send to your inbox",
                ]

                email_promise_detected = any(pattern in combined_text for pattern in email_promise_patterns)

                if email_promise_detected:
                    logger.info(
                        f"Email promise detected in SMS - tenant_id={tenant_id}, "
                        f"phone={from_number}, summary={summary[:100] if summary else 'none'}"
                    )
                    try:
                        from app.infrastructure.notifications import NotificationService
                        notification_service = NotificationService(db)

                        # Extract what the customer wanted from the summary
                        # Look for common request patterns
                        topic = "information"  # default
                        topic_keywords = {
                            "registration": ["registration", "register", "sign up", "signup", "enroll"],
                            "pricing": ["pricing", "price", "cost", "fee", "rate", "tuition"],
                            "schedule": ["schedule", "class time", "hours", "availability", "when"],
                            "details": ["details", "information", "info", "brochure"],
                        }
                        for topic_name, keywords in topic_keywords.items():
                            if any(kw in combined_text for kw in keywords):
                                topic = topic_name
                                break

                        await notification_service.notify_email_promise(
                            tenant_id=tenant_id,
                            customer_name=caller_name,
                            customer_phone=normalized_from,
                            customer_email=caller_email,
                            conversation_id=sms_conversation.id if sms_conversation else None,
                            channel="sms",
                            topic=topic,
                        )
                        logger.info(f"Email promise alert sent for SMS tenant_id={tenant_id}, topic={topic}")
                    except Exception as e:
                        logger.error(f"Failed to send email promise alert for SMS: {e}", exc_info=True)

                # =============================================================
                # Registration Link Sending for Telnyx SMS
                # =============================================================
                # Check if the conversation includes a registration request
                # and send the registration link via SMS (same as voice calls)
                registration_keywords_sms = [
                    # English
                    "registration", "register", "sign up", "signup", "enroll",
                    "enrollment", "registration link", "registration info",
                    # Spanish
                    "registro", "registrarse", "registrar", "inscripción", "inscribir",
                    "enlace de registro", "información de registro", "enlace de inscripción",
                    "solicitar registro", "solicitar información", "enviar enlace",
                    "mandar enlace", "link de registro",
                ]

                is_registration_request_sms = any(kw in combined_text for kw in registration_keywords_sms)

                # Check if link was already sent during conversation
                already_sent_indicators_sms = [
                    "link was sent", "link was shared", "link was provided",
                    "sent the link", "sent a link", "sent registration",
                    "text with the link", "text you the link", "texted the link",
                    "enlace fue enviado", "enlace enviado", "envié el enlace",
                ]
                link_already_sent_sms = any(ind in combined_text for ind in already_sent_indicators_sms)

                logger.info(
                    f"[SMS-DEBUG] SMS registration check - tenant_id={tenant_id}, "
                    f"is_registration_request={is_registration_request_sms}, "
                    f"link_already_sent={link_already_sent_sms}, ai_sent_url={ai_sent_registration_url}, phone={from_number}"
                )

                # Skip if AI already sent a registration URL in this conversation
                if ai_sent_registration_url:
                    logger.info(f"[SMS-AI-DEDUP] Skipping fallback SMS - AI already sent registration URL to {from_number}")

                # Only trust ai_sent_registration_url (actual Telnyx message check), not
                # link_already_sent_sms (summary text match). The AI often says "I sent the link"
                # in the summary but didn't actually send a URL via SMS.
                if is_registration_request_sms and normalized_from and not ai_sent_registration_url:
                    # IMMEDIATE SMS SEND: Send registration link right away
                    # Use consistent phone normalization for dedup keys (last 10 digits)
                    normalized_for_dedup = normalize_phone_for_dedup(from_number)
                    redis_dedup_key_sms = f"registration_sms:{tenant_id}:{normalized_for_dedup}"

                    # DATABASE-BASED DEDUP: Check if SMS was already sent recently
                    db_sms_already_sent = False
                    if lead:
                        await db.refresh(lead)
                        lead_extra = lead.extra_data or {}
                        last_sms_sent = lead_extra.get("sms_registration_sent_at")
                        if last_sms_sent:
                            try:
                                last_sent_time = datetime.fromisoformat(last_sms_sent.replace("Z", "+00:00"))
                                # Skip if SMS was sent within the last 3 minutes
                                if (datetime.utcnow().replace(tzinfo=None) - last_sent_time.replace(tzinfo=None)).total_seconds() < 180:
                                    db_sms_already_sent = True
                                    logger.info(f"[SMS] DB dedup - skipping, sent at {last_sms_sent}")
                            except Exception as parse_err:
                                logger.warning(f"[SMS] Failed to parse last_sms_sent: {parse_err}")

                    if db_sms_already_sent:
                        logger.info(f"[SMS] Skipping - already sent (DB dedup): phone={from_number}")
                    else:
                        # Mark in DB that we're sending (claim before send)
                        if lead:
                            lead_extra = lead.extra_data or {}
                            lead_extra["sms_registration_sent_at"] = datetime.utcnow().isoformat()
                            lead.extra_data = lead_extra
                            flag_modified(lead, "extra_data")
                            await db.commit()
                            logger.info(f"[SMS] Claimed SMS send in DB for lead_id={lead.id}")

                        # Try Redis dedup (optional, falls back to DB dedup if Redis unavailable)
                        redis_dedup_ok = True
                        try:
                            await redis_client.connect()
                            sms_already_sent = not await redis_client.setnx(redis_dedup_key_sms, "1", ttl=PHONE_SMS_DEDUP_TTL_SECONDS)
                            if sms_already_sent:
                                logger.info(f"[SMS] Skipping - already sent (Redis dedup): {redis_dedup_key_sms}")
                                redis_dedup_ok = False
                        except Exception as e:
                            logger.warning(f"[SMS] Redis dedup check failed (continuing anyway): {e}")

                        if redis_dedup_ok:
                            # Send SMS immediately
                            # If we extracted a URL from tool_calls, inject it into the transcript
                            # so fulfill_promise's extract_url_from_ai_response() picks it up
                            effective_transcript = actual_assistant_transcript or transcript or ""
                            if tool_call_url:
                                effective_transcript = f"{effective_transcript}\nRegistration link: {tool_call_url}"
                                logger.info(f"[SMS] Injected tool_call_url into transcript: {tool_call_url}")
                            logger.info(f"[SMS] Sending registration link immediately - tenant_id={tenant_id}, phone={from_number}")
                            await _send_sms_immediately(
                                db, tenant_id, from_number, caller_name,
                                summary, caller_intent, effective_transcript,
                                sms_conversation.id if sms_conversation else 0,
                                redis_dedup_key_sms,
                            )

            return JSONResponse(content={
                "status": "ok",
                "message": "sms_interaction_processed",
                "tenant_id": tenant_id,
            })

        # Create or update Call record (use naive datetime for DB compatibility)
        now = datetime.utcnow()

        # Use actual timestamps from webhook if available, otherwise use now
        actual_start = now
        actual_end = now
        if call_start_time:
            try:
                from dateutil import parser as date_parser
                actual_start = date_parser.parse(str(call_start_time)).replace(tzinfo=None)
            except Exception:
                pass
        if call_end_time:
            try:
                from dateutil import parser as date_parser
                actual_end = date_parser.parse(str(call_end_time)).replace(tzinfo=None)
            except Exception:
                pass

        # First, check if a Call record already exists with this call_id
        # This handles the case where TeXML status callback arrives before insights webhook
        call_sid_to_use = call_id or f"telnyx_ai_{now.timestamp()}"
        existing_call_result = await db.execute(
            select(Call).where(Call.call_sid == call_sid_to_use)
        )
        call = existing_call_result.scalar_one_or_none()

        # If not found by call_sid, try to find by phone number within last 10 minutes
        # This helps match insights webhooks to TeXML callbacks which use different IDs
        if not call and from_number:
            time_window = now - timedelta(minutes=10)
            normalized_from = _normalize_phone(from_number)
            recent_call_result = await db.execute(
                select(Call).where(
                    Call.tenant_id == tenant_id,
                    Call.from_number == normalized_from,
                    Call.created_at >= time_window,
                ).order_by(Call.created_at.desc()).limit(1)
            )
            call = recent_call_result.scalar_one_or_none()
            if call:
                logger.info(f"Found existing Call by phone number match: id={call.id}, call_sid={call.call_sid}")

        if call:
            # Update existing call with any new data
            logger.info(f"Found existing Call record: id={call.id}, updating with insights data")
            # Only update fields if we have new non-empty values
            if duration and int(duration) > 0 and (not call.duration or call.duration == 0):
                call.duration = int(duration)
            if recording_url and not call.recording_url:
                call.recording_url = recording_url
            # Update timestamps if they're more accurate
            if actual_start != now and (not call.started_at or call.started_at == call.ended_at):
                call.started_at = actual_start
            if actual_end != now and (not call.ended_at or call.ended_at == call.started_at):
                call.ended_at = actual_end
            # Detect and set language if not already set
            if not call.language and to_number:
                call.language = await _detect_language_from_phone(to_number, db)
        else:
            # Detect language from phone number routing
            detected_language = await _detect_language_from_phone(to_number, db) if to_number else None

            # Create new Call record
            call = Call(
                tenant_id=tenant_id,
                call_sid=call_sid_to_use,
                from_number=from_number,
                to_number=to_number,
                direction="inbound",
                status="completed",
                duration=int(duration) if duration else 0,
                recording_url=recording_url or None,
                started_at=actual_start,
                ended_at=actual_end,
                language=detected_language,
            )
            db.add(call)
            await db.flush()  # Get the call ID
            logger.info(f"Created new Call record: id={call.id}, language={detected_language}")

        # If duration is still 0, try to calculate from Telnyx API conversation timestamps
        if (not call.duration or call.duration == 0) and call_id and settings.telnyx_api_key:
            try:
                from app.infrastructure.telephony.telnyx_provider import TelnyxAIService
                telnyx_ai_duration = TelnyxAIService(settings.telnyx_api_key)
                conv_data = await telnyx_ai_duration.find_conversation_by_call_control_id(call_id)
                if conv_data:
                    conv_created = conv_data.get("created_at")
                    conv_updated = conv_data.get("updated_at")
                    if conv_created and conv_updated and conv_created != conv_updated:
                        from dateutil import parser as date_parser
                        start_dt = date_parser.parse(str(conv_created))
                        end_dt = date_parser.parse(str(conv_updated))
                        calculated_duration = int((end_dt - start_dt).total_seconds())
                        if calculated_duration > 0:
                            call.duration = calculated_duration
                            call.started_at = start_dt.replace(tzinfo=None)
                            call.ended_at = end_dt.replace(tzinfo=None)
                            logger.info(f"Calculated duration from Telnyx conversation timestamps: {calculated_duration}s")
                    else:
                        # Fallback: use conversation messages timestamps
                        conv_id = conv_data.get("id")
                        if conv_id:
                            msgs = await telnyx_ai_duration.get_conversation_messages(conv_id)
                            if msgs and len(msgs) >= 2:
                                first_ts = msgs[0].get("created_at") or msgs[0].get("timestamp")
                                last_ts = msgs[-1].get("created_at") or msgs[-1].get("timestamp")
                                if first_ts and last_ts:
                                    from dateutil import parser as date_parser
                                    start_dt = date_parser.parse(str(first_ts))
                                    end_dt = date_parser.parse(str(last_ts))
                                    calculated_duration = int((end_dt - start_dt).total_seconds())
                                    if calculated_duration > 0:
                                        call.duration = calculated_duration
                                        call.started_at = start_dt.replace(tzinfo=None)
                                        call.ended_at = end_dt.replace(tzinfo=None)
                                        logger.info(f"Calculated duration from message timestamps: {calculated_duration}s")
            except Exception as e:
                logger.warning(f"Failed to calculate duration from Telnyx API: {e}")

        # Store transcript and summary in call metadata or separate table
        # For now, we'll create a lead with the information

        # Create Lead from caller (always create new lead, link to existing contact)
        lead = None
        if from_number:
            normalized_from = _normalize_phone(from_number)

            call_data = {
                "source": "voice_call",
                "call_id": call.id,
                "call_date": now.strftime("%Y-%m-%d %H:%M"),
                "summary": summary,
                "caller_name": caller_name or None,
                "caller_email": caller_email or None,
                "caller_intent": caller_intent or None,
                "transcript": transcript[:2000] if transcript else None,
            }

            # Always create new lead for each call
            display_name = caller_name if caller_name else f"Caller {normalized_from}"
            lead = Lead(
                tenant_id=tenant_id,
                phone=normalized_from,
                name=display_name,
                email=caller_email or None,
                status="new",
                extra_data={"voice_calls": [call_data]},
            )
            db.add(lead)
            await db.flush()

            # Sync lead info to matching contact (find/update/create contact)
            contact_id = await _sync_lead_to_contact(
                db=db,
                tenant_id=tenant_id,
                lead=lead,
                phone=normalized_from,
                email=caller_email,
                name=caller_name,
            )
            logger.info(f"Created new Lead from AI call: phone={normalized_from}, name={caller_name}, email={caller_email}, contact_id={contact_id}")

            lead_id = lead.id if lead else None
        else:
            lead_id = None

        # Create or update CallSummary record for the Calls page
        # Determine outcome based on extracted data
        if caller_name and caller_email:
            outcome = "lead_created"
        elif caller_name or caller_email:
            outcome = "lead_created"
        elif lead_id:
            outcome = "info_provided"
        else:
            outcome = "incomplete"

        # Use extracted intent or default to general_inquiry
        final_intent = caller_intent if caller_intent in [
            "pricing_info", "hours_location", "booking_request",
            "support_request", "wrong_number", "general_inquiry"
        ] else "general_inquiry"

        # Check if CallSummary already exists (upsert logic)
        existing_summary_result = await db.execute(
            select(CallSummary).where(CallSummary.call_id == call.id)
        )
        existing_summary = existing_summary_result.scalar_one_or_none()

        if existing_summary:
            # Update existing summary
            existing_summary.lead_id = lead_id
            existing_summary.intent = final_intent
            existing_summary.outcome = outcome
            existing_summary.summary_text = summary or None
            existing_summary.extracted_fields = {
                "name": caller_name or None,
                "email": caller_email or None,
                "reason": caller_intent or (summary[:200] if summary else None),
            }
            logger.info(f"Updated existing CallSummary for call_id={call.id}, intent={final_intent}, outcome={outcome}, name={caller_name}")
        else:
            # Create new summary
            call_summary = CallSummary(
                call_id=call.id,
                lead_id=lead_id,
                intent=final_intent,
                outcome=outcome,
                summary_text=summary or None,
                extracted_fields={
                    "name": caller_name or None,
                    "email": caller_email or None,
                    "reason": caller_intent or (summary[:200] if summary else None),
                },
            )
            db.add(call_summary)
            logger.info(f"Created CallSummary for call_id={call.id}, intent={final_intent}, outcome={outcome}, name={caller_name}")

        await db.commit()

        # =============================================================
        # Auto-send registration SMS if user requested registration info
        # =============================================================
        # Check if summary/intent mentions registration requests
        # This handles both voice calls AND SMS chat via Telnyx AI Assistant
        combined_text = f"{summary or ''} {caller_intent or ''}".lower()
        registration_keywords = [
            # English
            "registration", "register", "sign up", "signup", "enroll",
            "enrollment", "registration link", "registration info",
            # Spanish
            "registro", "registrarse", "registrar", "inscripción", "inscribir",
            "enlace de registro", "información de registro", "enlace de inscripción",
            "solicitar registro", "solicitar información", "enviar enlace",
            "mandar enlace", "link de registro",
        ]

        # Check if link was ALREADY sent during the call (don't send again)
        # Also check for broken/looped conversations that shouldn't trigger SMS
        already_sent_indicators = [
            # English
            "link was sent",
            "link was shared",
            "link was provided",
            "sent the link",
            "sent a link",
            "sent registration",
            "sent the registration",
            "provided the link",
            "provided a link",
            "received a link",
            "sent to the user",
            "sent to their phone",
            "sent to your phone",
            "texted the link",
            "link shared",
            "link provided",
            "registration link sent",
            # Spanish
            "enlace fue enviado",
            "enlace enviado",
            "ya se envió",
            "ya envié",
            "se envió el enlace",
            "le envié el enlace",
            "le mandé el enlace",
            "enlace compartido",
            "enlace proporcionado",
            "información enviada",
            "mensaje enviado",
            "recibió el enlace",
            "ya tiene el enlace",
            # Indicators of broken/looped conversations - don't send SMS
            "repeated message",
            "series of repeated",
            "shared multiple times",
            "link multiple times",
            "no conversation to summarize",
            "there is no conversation",
            "conversation has just begun",
            "conversation has just started",
            "no context or details",
            "identical automated messages",
            "nothing to summarize",
            # Spanish broken conversation indicators
            "mensaje repetido",
            "mensajes repetidos",
            "no hay conversación",
            "nada que resumir",
        ]
        link_indicator_matched = any(indicator in combined_text for indicator in already_sent_indicators)

        # Check if URL was properly formatted (has ?loc= and &type= parameters)
        # If AI sent just the base URL without parameters, we should still send the correct one
        url_was_properly_formatted = False
        if link_indicator_matched:
            # Look for URLs in the combined text (summary + caller_intent + transcript would have the URL)
            import re
            url_pattern = r'https://britishswimschool\.com/cypress-spring/register/[^\s\)\"\'<>]*'
            found_urls = re.findall(url_pattern, combined_text)

            # Also check in transcript if available
            full_text = f"{combined_text} {transcript or ''}".lower()
            all_urls = re.findall(url_pattern, full_text)

            for url in all_urls:
                # Check if URL has proper parameters
                if '?loc=' in url and '&type=' in url:
                    url_was_properly_formatted = True
                    logger.info(f"[SMS-DEBUG] Found properly formatted URL in conversation: {url}")
                    break
                elif '?loc=' in url:
                    # Has location but no type - still consider it acceptable
                    url_was_properly_formatted = True
                    logger.info(f"[SMS-DEBUG] Found URL with location only (acceptable): {url}")
                    break

            if not url_was_properly_formatted and all_urls:
                logger.warning(
                    f"[SMS-DEBUG] Link was sent but URL was NOT properly formatted! "
                    f"URLs found: {all_urls[:3]}. Will send correct URL post-call."
                )

        # Only skip post-call SMS if the in-call link was PROPERLY formatted
        # If AI sent bad URL (no params), we need to send the correct one
        link_already_sent = link_indicator_matched and url_was_properly_formatted

        is_registration_request = any(kw in combined_text for kw in registration_keywords)

        # [SMS-DEBUG] Log which keywords matched for debugging
        matched_reg_keywords = [kw for kw in registration_keywords if kw in combined_text]
        matched_sent_indicators = [ind for ind in already_sent_indicators if ind in combined_text]
        logger.info(
            f"[SMS-DEBUG] Keyword matching - "
            f"matched_registration_keywords={matched_reg_keywords}, "
            f"matched_sent_indicators={matched_sent_indicators}, "
            f"link_indicator_matched={link_indicator_matched}, "
            f"url_was_properly_formatted={url_was_properly_formatted}"
        )

        # [SMS-DEBUG] Log registration detection for transfer debugging
        logger.info(
            f"[SMS-DEBUG] Telnyx registration check - tenant_id={tenant_id}, "
            f"is_registration_request={is_registration_request}, link_already_sent={link_already_sent}, "
            f"from_number={from_number}, event_type={event_type}, "
            f"combined_text_preview={combined_text[:200] if combined_text else 'empty'}"
        )

        # =============================================================
        # EVENT TYPE FILTER: Only auto-send SMS on specific event types
        # =============================================================
        # Telnyx sends multiple events: conversation.ended, insights.generated, retries
        # Only trigger auto-send on the primary end-of-call event to reduce duplicates
        allowed_sms_events = [
            "call.conversation.ended",
            "conversation.ended",
            "conversation_insight_result",  # Insights webhook - needed for transfers
        ]
        is_allowed_sms_event = event_type in allowed_sms_events
        if is_registration_request and not is_allowed_sms_event:
            logger.info(
                f"Skipping registration SMS - event_type={event_type} not in allowed events: "
                f"tenant_id={tenant_id}, phone={from_number}"
            )
            is_registration_request = False  # Disable SMS for non-allowed events

        # =============================================================
        # DEDUPLICATION: Check if we've already sent SMS for this call
        # =============================================================
        # Telnyx sends multiple events per call (conversation.ended, insights.generated, retries)
        # Use database-backed dedup with "claim before send" to prevent race conditions
        # IMPORTANT: Use normalize_phone_for_dedup (last 10 digits) to match promise_fulfillment_service
        sms_already_sent_for_call = False
        normalized_from_for_dedup = normalize_phone_for_dedup(from_number) if from_number else None
        redis_dedup_key = (
            f"registration_sms:{tenant_id}:{normalized_from_for_dedup}"
            if normalized_from_for_dedup
            else None
        )

        # Test phone whitelist - bypass dedup for testing
        # WARNING: Keep this empty in production to prevent duplicate SMS
        TEST_PHONE_WHITELIST: set[str] = set()
        is_test_phone = normalized_from_for_dedup in TEST_PHONE_WHITELIST if normalized_from_for_dedup else False
        if is_test_phone:
            logger.info(f"Test phone whitelist - bypassing voice dedup for {normalized_from_for_dedup}")

        # LAYER 1: DB check - query sent_assets table for recent sends to this phone
        # This is the most reliable check - works even if Redis is down
        if is_registration_request and normalized_from_for_dedup and not sms_already_sent_for_call and not is_test_phone:
            try:
                from app.persistence.models.sent_asset import SentAsset

                # Check if registration_link was sent to this phone in the last 3 minutes
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=3)
                existing_send = await db.execute(
                    select(SentAsset.id).where(
                        SentAsset.tenant_id == tenant_id,
                        SentAsset.phone_normalized == normalized_from_for_dedup,
                        SentAsset.asset_type == "registration_link",
                        SentAsset.sent_at >= cutoff_time,
                    ).limit(1)
                )
                if existing_send.scalar_one_or_none():
                    sms_already_sent_for_call = True
                    logger.info(
                        f"Skipping registration SMS - DB sent_assets check found recent send: "
                        f"tenant_id={tenant_id}, phone={normalized_from_for_dedup}"
                    )
            except Exception as e:
                logger.warning(f"DB sent_assets dedup check failed: {e}")

        # LAYER 1.5: Check if AI already sent registration URL in conversation messages
        # This prevents duplicates when AI sends link directly via Telnyx messaging
        # Also extract location/level from tool_calls for URL building
        ai_sent_registration_url_voice = False
        voice_tool_call_url = None
        if is_registration_request and not sms_already_sent_for_call and not is_test_phone:
            try:
                telnyx_conv_id_for_check = (
                    payload.get("conversation_id")
                    or metadata.get("conversation_id")
                    or data.get("conversation_id")
                )
                if telnyx_conv_id_for_check and settings.telnyx_api_key:
                    from app.infrastructure.telephony.telnyx_provider import TelnyxAIService
                    voice_telnyx_ai = TelnyxAIService(settings.telnyx_api_key)
                    voice_messages = await voice_telnyx_ai.get_conversation_messages(telnyx_conv_id_for_check)
                    if voice_messages:
                        for msg in voice_messages:
                            msg_text = msg.get("text", msg.get("content", "")) or ""
                            if "britishswimschool.com" in msg_text and "register" in msg_text:
                                ai_sent_registration_url_voice = True
                                logger.info(f"[VOICE-AI-DEDUP] AI already sent registration URL: {msg_text[:100]}")
                                break

                        # Extract location/level from tool_calls in conversation messages
                        for msg in voice_messages:
                            tool_calls_voice = msg.get("tool_calls")
                            if not tool_calls_voice:
                                continue
                            for tc in tool_calls_voice:
                                fn = tc.get("function", tc) if isinstance(tc, dict) else {}
                                fn_name = fn.get("name", "")
                                if "registration" in fn_name.lower() or "send_registration" in fn_name.lower():
                                    args = fn.get("arguments", {})
                                    if isinstance(args, str):
                                        try:
                                            args = json.loads(args)
                                        except Exception:
                                            args = {}
                                    tc_location = args.get("location")
                                    tc_level = args.get("level")
                                    if tc_location:
                                        try:
                                            from app.utils.registration_url_builder import build_registration_url
                                            tc_loc_code = _map_location_to_code(tc_location)
                                            tc_level_name = _normalize_level_name(tc_level) if tc_level else None
                                            if tc_loc_code:
                                                voice_tool_call_url = build_registration_url(tc_loc_code, tc_level_name)
                                                logger.info(f"[VOICE-TOOL-EXTRACT] Built URL from tool call: {voice_tool_call_url}")
                                        except Exception as e:
                                            logger.warning(f"[VOICE-TOOL-EXTRACT] Failed to build URL: {e}")
                                    break
                            if voice_tool_call_url:
                                break
            except Exception as e:
                logger.warning(f"[VOICE-AI-DEDUP] Failed to check conversation messages: {e}")

        if ai_sent_registration_url_voice:
            sms_already_sent_for_call = True
            logger.info(f"[VOICE-AI-DEDUP] Skipping fallback SMS - AI already sent registration URL to {from_number}")

        # LAYER 2: Redis atomic setnx (fast-path, works even if lead is missing)
        # CRITICAL: Use setnx to atomically claim the right to send SMS
        # This prevents race conditions where multiple webhook events arrive simultaneously
        redis_dedup_claimed = False
        if is_registration_request and redis_dedup_key and not sms_already_sent_for_call and not is_test_phone:
            try:
                await redis_client.connect()
                # setnx returns True if key was set (we got the lock), False if already exists
                redis_dedup_claimed = await redis_client.setnx(redis_dedup_key, "1", ttl=PHONE_SMS_DEDUP_TTL_SECONDS)
                if not redis_dedup_claimed:
                    sms_already_sent_for_call = True
                    logger.info(
                        f"Skipping registration SMS - redis setnx dedup blocked: {redis_dedup_key}"
                    )
                else:
                    logger.info(f"Claimed Redis dedup lock for SMS: {redis_dedup_key}")
            except Exception as e:
                logger.warning(f"Redis dedup setnx failed for {redis_dedup_key}: {e}")

        # LAYER 3: Lead-based check (skip for test phones)
        if lead and call and is_registration_request and from_number and not sms_already_sent_for_call and not is_test_phone:
            # Refresh lead from DB to get latest data (in case another event updated it)
            await db.refresh(lead)
            lead_extra = lead.extra_data or {}
            sent_call_ids = lead_extra.get("registration_sms_sent_call_ids", [])

            if call.id in sent_call_ids or str(call.id) in sent_call_ids:
                sms_already_sent_for_call = True
                logger.info(
                    f"Skipping registration SMS - already sent for call_id={call.id}: "
                    f"tenant_id={tenant_id}, phone={from_number}"
                )
            else:
                # CLAIM: Mark this call as "SMS being sent" BEFORE actually sending
                # This prevents race conditions where multiple events try to send simultaneously
                try:
                    sent_call_ids.append(call.id)
                    lead_extra["registration_sms_sent_call_ids"] = sent_call_ids
                    lead.extra_data = lead_extra
                    flag_modified(lead, "extra_data")
                    await db.commit()
                    logger.info(f"Claimed SMS send for call_id={call.id}, lead_id={lead.id}")
                except Exception as claim_err:
                    # If claim fails (e.g., another event already claimed), skip SMS
                    logger.warning(f"Failed to claim SMS send for call_id={call.id}: {claim_err}")
                    sms_already_sent_for_call = True

        # [SMS-DEBUG] Log final SMS decision
        logger.info(
            f"[SMS-DEBUG] SMS decision - tenant_id={tenant_id}, "
            f"link_already_sent={link_already_sent}, ai_sent_url_voice={ai_sent_registration_url_voice}, "
            f"sms_already_sent_for_call={sms_already_sent_for_call}, "
            f"is_registration_request={is_registration_request}, has_phone={bool(from_number)}, "
            f"will_send={is_registration_request and from_number and not (link_already_sent and ai_sent_registration_url_voice) and not sms_already_sent_for_call}"
        )

        # Only trust link_already_sent if AI actually sent a URL (confirmed by message check).
        # The AI often says "I sent the link" in the summary but didn't actually send a URL.
        link_confirmed_sent = link_already_sent and ai_sent_registration_url_voice
        if link_already_sent and not ai_sent_registration_url_voice:
            logger.info(
                f"[SMS-DEBUG] Summary says link sent but AI didn't actually send URL - overriding link_already_sent: "
                f"tenant_id={tenant_id}, phone={from_number}"
            )

        if link_confirmed_sent:
            logger.info(
                f"Skipping registration SMS - link already sent during call (confirmed by AI messages): "
                f"tenant_id={tenant_id}, phone={from_number}"
            )
        elif sms_already_sent_for_call:
            pass  # Already logged above
        elif is_registration_request and from_number:
            logger.info(
                f"Registration request detected from Telnyx AI - "
                f"tenant_id={tenant_id}, phone={from_number}, summary={summary[:100] if summary else 'none'}"
            )
            try:
                from app.domain.services.promise_detector import DetectedPromise
                from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService

                # Create promise object for registration
                promise = DetectedPromise(
                    asset_type="registration_link",
                    confidence=0.9,  # High confidence since Telnyx AI identified the request
                    original_text=summary or "User requested registration information",
                )

                # Use conversation_id from Telnyx if available, otherwise use call.id
                conversation_id = (
                    payload.get("conversation_id") or
                    metadata.get("telnyx_conversation_id") or
                    call.id
                )

                # Fulfill the promise (send SMS with registration info)
                # Pass summary, caller_intent, and transcript so dynamic URL can be built from context
                # IMPORTANT: caller_intent contains the location/level details needed for URL building
                # If we extracted a URL from tool_calls, inject it so extract_url_from_ai_response picks it up
                ai_response_text = f"{summary or ''}\n{caller_intent or ''}\n{transcript or ''}"
                if voice_tool_call_url:
                    ai_response_text = f"{ai_response_text}\nRegistration link: {voice_tool_call_url}"
                    logger.info(f"[VOICE] Injected tool_call_url into ai_response: {voice_tool_call_url}")
                logger.info("=" * 60)
                logger.info("SENDING POST-CALL REGISTRATION SMS")
                logger.info(f"Tenant: {tenant_id}, Phone: {from_number}, Name: {caller_name}")
                logger.info(f"Summary (first 200 chars): {(summary or 'NONE')[:200]}")
                logger.info(f"Caller Intent (first 200 chars): {(caller_intent or 'NONE')[:200]}")
                logger.info(f"Transcript (first 200 chars): {(transcript or 'NONE')[:200]}")
                logger.info("=" * 60)

                fulfillment_service = PromiseFulfillmentService(db)
                result = await fulfillment_service.fulfill_promise(
                    tenant_id=tenant_id,
                    conversation_id=int(conversation_id) if str(conversation_id).isdigit() else call.id,
                    promise=promise,
                    phone=from_number,
                    name=caller_name,
                    ai_response=ai_response_text,  # Include both for URL extraction
                )

                logger.info(
                    f"Registration SMS fulfillment result - tenant_id={tenant_id}, "
                    f"status={result.get('status')}, phone={from_number}, call_id={call.id if call else 'none'}"
                )
                # Redis key was already set by setnx before sending
                # If send failed, release the Redis lock so retry is possible
                if result.get("status") != "sent":
                    if redis_dedup_key and redis_dedup_claimed:
                        try:
                            await redis_client.delete(redis_dedup_key)
                            logger.info(f"Released Redis dedup lock after failed send: {redis_dedup_key}")
                        except Exception as e:
                            logger.warning(f"Failed to release Redis dedup lock {redis_dedup_key}: {e}")
                if result.get("status") != "sent" and lead and call:
                    # ROLLBACK: If send failed, remove claim so retry is possible
                    try:
                        await db.refresh(lead)
                        lead_extra = lead.extra_data or {}
                        sent_call_ids = lead_extra.get("registration_sms_sent_call_ids", [])
                        if call.id in sent_call_ids:
                            sent_call_ids.remove(call.id)
                            lead_extra["registration_sms_sent_call_ids"] = sent_call_ids
                            lead.extra_data = lead_extra
                            flag_modified(lead, "extra_data")
                            await db.commit()
                            logger.info(f"Rolled back SMS claim for call_id={call.id} after failed send")
                    except Exception as rollback_err:
                        logger.warning(f"Failed to rollback SMS claim for call_id={call.id}: {rollback_err}")
            except Exception as e:
                logger.error(f"Failed to auto-send registration SMS: {e}", exc_info=True)
                # ROLLBACK: On exception, release Redis lock so retry is possible
                if redis_dedup_key and redis_dedup_claimed:
                    try:
                        await redis_client.delete(redis_dedup_key)
                        logger.info(f"Released Redis dedup lock after exception: {redis_dedup_key}")
                    except Exception as redis_err:
                        logger.warning(f"Failed to release Redis dedup lock {redis_dedup_key}: {redis_err}")
                # ROLLBACK: Also remove lead claim
                if lead and call:
                    try:
                        await db.refresh(lead)
                        lead_extra = lead.extra_data or {}
                        sent_call_ids = lead_extra.get("registration_sms_sent_call_ids", [])
                        if call.id in sent_call_ids:
                            sent_call_ids.remove(call.id)
                            lead_extra["registration_sms_sent_call_ids"] = sent_call_ids
                            lead.extra_data = lead_extra
                            flag_modified(lead, "extra_data")
                            await db.commit()
                            logger.info(f"Rolled back SMS claim for call_id={call.id} after exception")
                    except Exception as rollback_err:
                        logger.warning(f"Failed to rollback SMS claim for call_id={call.id}: {rollback_err}")

        return JSONResponse(content={
            "status": "ok",
            "call_id": call.id,
            "tenant_id": tenant_id,
            "lead_created": bool(from_number),
        })

    except Exception as e:
        logger.error(f"Error processing Telnyx AI call webhook: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)})


# =============================================================================
# Telnyx Call Progress Events
# =============================================================================


@router.post("/call-progress")
async def telnyx_call_progress(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle call progress events from Telnyx.

    This endpoint receives TeXML call progress events during call lifecycle:
    - call.initiated, call.answered, call.hangup, etc.

    Args:
        request: FastAPI request with call event data
        db: Database session

    Returns:
        JSON response with 200 status
    """
    from app.persistence.models.call import Call
    import json

    try:
        # Handle different content types (JSON or form data)
        content_type = request.headers.get("content-type", "")
        body = {}

        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                raw = await request.body()
                logger.info(f"call-progress: Failed to parse JSON, raw body: {raw[:500]}")
        elif "form" in content_type:
            form_data = await request.form()
            body = dict(form_data)
        else:
            # Try JSON anyway
            try:
                body = await request.json()
            except Exception:
                raw = await request.body()
                if raw:
                    logger.info(f"call-progress: Unknown content-type, raw body: {raw[:500]}")

        logger.info(f"Telnyx call-progress webhook: {json.dumps(body)[:2000] if body else 'empty'}")

        # Extract event data - Telnyx format: {data: {event_type, payload}}
        data = body.get("data", body)
        event_type = data.get("event_type", "unknown")
        payload = data.get("payload", data)

        logger.info(f"Telnyx call-progress event_type: {event_type}")

        # Extract call identifiers
        call_control_id = (
            payload.get("call_control_id")
            or payload.get("call_session_id")
            or data.get("call_control_id")
            or ""
        )

        # Handle call.initiated or call.answered - create Call record early
        # This ensures the Call record exists when tools like send_registration_link
        # are called during the call (they need to look up caller phone by call_control_id)
        if event_type in ("call.initiated", "call.answered") and call_control_id:
            # Check if Call record already exists
            stmt = select(Call).where(Call.call_sid == call_control_id)
            result = await db.execute(stmt)
            existing_call = result.scalar_one_or_none()

            if not existing_call:
                # Extract phone numbers from payload
                from_number = (
                    payload.get("from")
                    or payload.get("caller_id_number")
                    or payload.get("from_number")
                    or ""
                )
                to_number = (
                    payload.get("to")
                    or payload.get("called_number")
                    or payload.get("to_number")
                    or ""
                )

                # Look up tenant by the Telnyx phone number (to_number)
                tenant_id = None
                if to_number:
                    tenant_id = await _get_tenant_from_telnyx_number(to_number, db)

                if tenant_id and from_number:
                    # Create Call record so tools can look it up during the call
                    new_call = Call(
                        tenant_id=tenant_id,
                        call_sid=call_control_id,
                        from_number=from_number,
                        to_number=to_number,
                        direction="inbound",
                        status="in-progress",
                        duration=0,
                        started_at=datetime.utcnow(),
                    )
                    db.add(new_call)
                    await db.commit()
                    logger.info(
                        f"Created Call record on {event_type}: id={new_call.id}, "
                        f"call_sid={call_control_id}, from={from_number}, to={to_number}"
                    )
                else:
                    logger.warning(
                        f"Could not create Call record on {event_type}: "
                        f"tenant_id={tenant_id}, from={from_number}, to={to_number}"
                    )
            else:
                logger.debug(f"Call record already exists for {call_control_id}")

        # Handle call.hangup event - update duration
        elif event_type == "call.hangup":
            # Try to find existing call record
            if call_control_id:
                stmt = select(Call).where(Call.call_sid == call_control_id)
                result = await db.execute(stmt)
                call = result.scalar_one_or_none()

                if call:
                    # Update ended_at and calculate duration
                    call.ended_at = datetime.utcnow()
                    call.status = "completed"

                    # Get duration from payload if available
                    duration_secs = payload.get("duration_seconds") or payload.get("duration") or 0
                    if duration_secs and int(duration_secs) > 0:
                        call.duration = int(duration_secs)
                    elif call.started_at:
                        # Calculate from timestamps
                        call.duration = int((call.ended_at - call.started_at).total_seconds())

                    await db.commit()
                    logger.info(f"Updated call {call.id} on hangup: duration={call.duration}s")

        return JSONResponse(content={"status": "ok", "event_type": event_type})

    except Exception as e:
        logger.error(f"Error processing call-progress webhook: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)})


# =============================================================================
# Voice Fallback (TeXML)
# =============================================================================


@router.post("/voice-fallback")
async def voice_fallback(request: Request) -> Response:
    """Fallback endpoint for when Telnyx AI Assistant is unavailable.

    This endpoint is called when the primary AI Assistant webhook fails or times out.
    It returns TeXML that plays an apology message and takes a voicemail.

    Args:
        request: FastAPI request

    Returns:
        TeXML response with apology message and voicemail recording
    """
    logger.warning("Voice fallback triggered - AI Assistant may be unavailable")

    # Log request details for debugging
    try:
        body = await request.body()
        logger.info(f"Voice fallback request body: {body.decode()[:500] if body else 'empty'}")
    except Exception:
        pass

    # TeXML response: apology message + voicemail
    texml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">We apologize, but we are experiencing technical difficulties and cannot take your call right now. Please leave a message after the beep and we will call you back as soon as possible.</Say>
    <Record maxLength="120" finishOnKey="#" playBeep="true"/>
    <Say voice="Polly.Joanna">Thank you for your message. Goodbye.</Say>
    <Hangup/>
</Response>'''

    return Response(content=texml, media_type="application/xml")


# =============================================================================
# ETL: Sync Calls to Leads
# =============================================================================


@router.post("/sync-calls-to-leads")
async def sync_calls_to_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """ETL endpoint to sync Call records to Lead records.

    This finds all calls that don't have associated leads and creates
    lead records from the call data (phone number, name, email from CallSummary).

    Can be called manually or via cron/scheduler.

    Args:
        db: Database session

    Returns:
        JSON response with count of leads created/updated
    """
    from app.persistence.models.call import Call
    from app.persistence.models.call_summary import CallSummary
    from app.persistence.models.lead import Lead
    from sqlalchemy.orm import joinedload

    try:
        # Find all calls with summaries that don't have lead_id set
        stmt = (
            select(Call)
            .options(joinedload(Call.summary))
            .where(Call.from_number.isnot(None))
            .order_by(Call.created_at.desc())
        )
        result = await db.execute(stmt)
        calls = result.unique().scalars().all()

        leads_created = 0
        leads_updated = 0
        calls_processed = 0

        for call in calls:
            if not call.from_number or not call.tenant_id:
                continue

            normalized_phone = _normalize_phone(call.from_number)

            # Check if lead exists for this phone number (get most recent if multiple)
            lead_stmt = select(Lead).where(
                Lead.tenant_id == call.tenant_id,
                Lead.phone == normalized_phone,
            ).order_by(Lead.created_at.desc()).limit(1)
            lead_result = await db.execute(lead_stmt)
            lead = lead_result.scalar_one_or_none()

            # Get name/email/summary from CallSummary if available
            caller_name = None
            caller_email = None
            summary_text = None
            caller_intent = None

            if call.summary:
                extracted = call.summary.extracted_fields or {}
                caller_name = extracted.get("name")
                caller_email = extracted.get("email")
                caller_intent = extracted.get("reason")
                summary_text = call.summary.summary_text

            # Build call data for lead's extra_data
            call_data = {
                "source": "voice_call",
                "call_id": call.id,
                "call_date": call.created_at.strftime("%Y-%m-%d %H:%M") if call.created_at else None,
                "summary": summary_text,
                "caller_name": caller_name,
                "caller_email": caller_email,
                "caller_intent": caller_intent,
                "duration": call.duration,
            }

            if not lead:
                # Create new lead - use phone number as fallback name
                display_name = caller_name if caller_name else f"Caller {normalized_phone}"
                lead = Lead(
                    tenant_id=call.tenant_id,
                    phone=normalized_phone,
                    name=display_name,
                    email=caller_email,
                    status="new",
                    extra_data={"voice_calls": [call_data]},
                )
                db.add(lead)
                leads_created += 1
                logger.info(f"ETL: Created lead for phone {normalized_phone}")
            else:
                # Check if this call is already in the lead's voice_calls
                existing_data = dict(lead.extra_data) if lead.extra_data else {}
                voice_calls = existing_data.get("voice_calls", [])

                # Check if call already exists (by call_id)
                existing_call_ids = [vc.get("call_id") for vc in voice_calls if isinstance(vc, dict)]

                if call.id not in existing_call_ids:
                    # Add this call to the lead
                    voice_calls = list(voice_calls)
                    voice_calls.append(call_data)
                    existing_data["voice_calls"] = voice_calls
                    lead.extra_data = existing_data
                    flag_modified(lead, "extra_data")

                    # Update name/email if we have new info
                    if caller_name and not lead.name:
                        lead.name = caller_name
                    if caller_email and not lead.email:
                        lead.email = caller_email

                    leads_updated += 1
                    logger.info(f"ETL: Updated lead {lead.id} with call {call.id}")

            # Update CallSummary with lead_id if not set
            if call.summary and not call.summary.lead_id:
                await db.flush()  # Ensure lead.id is set
                call.summary.lead_id = lead.id

            calls_processed += 1

        await db.commit()

        logger.info(f"ETL complete: processed={calls_processed}, created={leads_created}, updated={leads_updated}")

        return JSONResponse(content={
            "status": "ok",
            "calls_processed": calls_processed,
            "leads_created": leads_created,
            "leads_updated": leads_updated,
        })

    except Exception as e:
        logger.error(f"Error in ETL sync-calls-to-leads: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# =============================================================================
# Telnyx AI Assistant Webhook Tools
# =============================================================================


class SendRegistrationLinkRequest(BaseModel):
    """Request body for send_registration_link webhook tool.

    The AI extracts these from the conversation and passes them to the tool.
    """
    location: str | None = None  # "Cypress", "Langham Creek", or "Spring"
    level: str | None = None  # "Adult Level 3", "Tadpole", etc.


@router.post("/tools/send-registration-link")
async def send_registration_link_tool(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Async webhook tool for Telnyx AI Assistant to send registration links.

    Called when the AI Assistant needs to send a registration link to the caller.
    This is an async tool - it returns immediately and the SMS is sent in the background.

    Telnyx provides:
    - x-]telnyx-call-control-id header: For live message injection
    - x-]telnyx-from header: Caller's phone number
    - Body: {location, level} extracted by AI from conversation

    Args:
        request: FastAPI request with Telnyx headers and body
        db: Database session

    Returns:
        JSON response with status
    """
    try:
        # Debug: Print all headers to see what Telnyx sends
        print(f"[TOOL DEBUG] === send_registration_link called ===")
        print(f"[TOOL DEBUG] Headers: {dict(request.headers)}")

        # Parse body
        try:
            body = await request.json()
        except Exception:
            body = {}

        print(f"[TOOL DEBUG] Body: {body}")

        # Get call_control_id from Telnyx header
        call_control_id = request.headers.get("x-telnyx-call-control-id", "")

        # Look up the caller's phone from our Call table using call_control_id
        # This is more reliable than expecting the AI to pass the phone number
        caller_phone = None
        tenant_id = None
        to_number = None

        if call_control_id:
            from app.persistence.models.call import Call
            stmt = select(Call).where(Call.call_sid == call_control_id)
            result = await db.execute(stmt)
            call_record = result.scalar_one_or_none()

            if call_record:
                caller_phone = call_record.from_number
                tenant_id = call_record.tenant_id
                to_number = call_record.to_number
                print(f"[TOOL DEBUG] Found call record - from={caller_phone}, tenant={tenant_id}")
            else:
                print(f"[TOOL DEBUG] No call record found for call_control_id={call_control_id}")
                # Fallback: query Telnyx API to get caller phone from call_control_id
                if settings.telnyx_api_key:
                    try:
                        import httpx
                        async with httpx.AsyncClient(
                            base_url="https://api.telnyx.com/v2",
                            headers={"Authorization": f"Bearer {settings.telnyx_api_key}"},
                            timeout=10.0,
                        ) as client:
                            resp = await client.get(f"/calls/{call_control_id}")
                            if resp.status_code == 200:
                                call_data = resp.json().get("data", {})
                                caller_phone = call_data.get("from") or call_data.get("from_display_name")
                                to_number = call_data.get("to")
                                print(f"[TOOL DEBUG] Telnyx API lookup - from={caller_phone}, to={to_number}")
                            else:
                                print(f"[TOOL DEBUG] Telnyx API call lookup failed: {resp.status_code} {resp.text[:200]}")
                    except Exception as e:
                        print(f"[TOOL DEBUG] Telnyx API call lookup error: {e}")

        # Fallback: check body for phone number (from AI parameter)
        if not caller_phone:
            caller_phone = body.get("caller_phone", "") or body.get("from", "")
            # Filter out test/placeholder numbers
            if caller_phone and caller_phone.startswith("+1555"):
                print(f"[TOOL DEBUG] Ignoring test phone number: {caller_phone}")
                caller_phone = None

        logger.info(
            f"[TOOL] send_registration_link called - "
            f"call_control_id={call_control_id}, caller={caller_phone}, "
            f"location={body.get('location')}, level={body.get('level')}"
        )

        if not caller_phone:
            # Can't send SMS right now - will be sent post-call by ai-call-complete webhook.
            # Return a success-like response so the AI continues the conversation naturally.
            logger.info(
                "[TOOL] No caller phone found - SMS will be sent via ai-call-complete webhook. "
                "Returning success to AI so it continues talking."
            )
            return JSONResponse(content={
                "status": "ok",
                "result": "The registration link will be sent to the caller's phone via text message momentarily. "
                          "Let the caller know the text is on its way and ask if there is anything else you can help with."
            })

        # Look up tenant by the Telnyx number if not already found
        if not tenant_id and to_number:
            tenant_id = await _get_tenant_from_telnyx_number(to_number, db)

        # Fallback: default to tenant 3 (BSS)
        if not tenant_id:
            tenant_id = 3
            logger.warning(f"[TOOL] Could not determine tenant, defaulting to {tenant_id}")

        # Extract location and level from body
        location = body.get("location", "")
        level = body.get("level", "")

        # Map location name to location code
        location_code = _map_location_to_code(location)

        if not location_code:
            logger.warning(f"[TOOL] Could not map location '{location}' to code")
            return JSONResponse(content={
                "status": "error",
                "message": f"Unknown location: {location}"
            })

        # Build the registration URL
        from app.utils.registration_url_builder import build_registration_url, LEVEL_NAME_TO_TYPE_CODE

        # Try to map level name to standard name
        level_name = _normalize_level_name(level) if level else None

        try:
            registration_url = build_registration_url(location_code, level_name)
            logger.info(f"[TOOL] Built registration URL: {registration_url}")
        except Exception as e:
            logger.error(f"[TOOL] Failed to build URL: {e}")
            return JSONResponse(content={
                "status": "error",
                "message": f"Failed to build URL: {e}"
            })

        # Send the SMS
        from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
        from app.domain.services.promise_detector import DetectedPromise

        fulfillment_service = PromiseFulfillmentService(db)

        # Create a synthetic promise for the fulfillment service
        promise = DetectedPromise(
            asset_type="registration_link",
            confidence=1.0,  # Tool call = high confidence
            original_text=f"Tool call: send registration link for {level} at {location}",
        )

        # Fulfill the promise (sends SMS)
        # Include the full URL in ai_response so fulfillment service can extract it
        result = await fulfillment_service.fulfill_promise(
            tenant_id=tenant_id,
            conversation_id=None,  # No conversation ID for tool calls
            promise=promise,
            phone=caller_phone,
            name=None,  # Could extract from call if needed
            messages=None,
            ai_response=f"Here is the registration link: {registration_url}",
        )

        logger.info(f"[TOOL] Registration link send result: {result}")

        # TODO: Use call_control_id to inject confirmation message back into live call
        # This would require calling Telnyx's live message injection API

        return JSONResponse(content={
            "status": result.get("status", "unknown"),
            "message_id": result.get("message_id"),
            "url_sent": registration_url if result.get("status") == "sent" else None,
        })

    except Exception as e:
        logger.error(f"[TOOL] Error in send_registration_link: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@router.post("/tools/send-link")
async def send_link_tool(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Webhook tool for Telnyx AI Assistant to send a Jackrabbit registration link via SMS.

    Replaces the external Railway service. Called by the Telnyx AI agent when
    a caller wants to register for a class.

    Body params:
        to: Caller phone number (required)
        org_id: Jackrabbit org ID (required, e.g. "545911")
        class_id: Jackrabbit class ID (optional)
        class_name: Class name for logging (optional)
        first_name, last_name, email, students: Optional caller info
    """
    try:
        # Parse body
        try:
            body = await request.json()
        except Exception:
            body = {}

        to_phone = body.get("to", "")
        org_id = body.get("org_id", "545911")
        class_id = body.get("class_id")
        class_name = body.get("class_name", "")

        logger.info(
            f"[TOOL] send_link called - to={to_phone}, org_id={org_id}, "
            f"class_id={class_id}, class_name={class_name}"
        )

        if not to_phone:
            logger.warning("[TOOL] send_link: no 'to' phone number provided")
            return JSONResponse(content={
                "status": "ok",
                "result": "Registration link will be sent after the call.",
            })

        # Determine tenant from call context
        tenant_id = None
        call_control_id = request.headers.get("x-telnyx-call-control-id", "")
        if call_control_id:
            from app.persistence.models.call import Call
            stmt = select(Call).where(Call.call_sid == call_control_id)
            result = await db.execute(stmt)
            call_record = result.scalar_one_or_none()
            if call_record:
                tenant_id = call_record.tenant_id

        # Fallback: look up tenant by the caller's phone in sms configs
        if not tenant_id:
            tenant_id = await _get_tenant_from_telnyx_number(to_phone, db)

        if not tenant_id:
            logger.error("[TOOL] send_link: could not determine tenant")
            return JSONResponse(content={
                "status": "error",
                "message": "Could not determine tenant",
            })

        # Build Jackrabbit registration URL
        if class_id:
            reg_url = f"https://app.jackrabbitclass.com/regv2.asp?id={org_id}&classid={class_id}"
        else:
            reg_url = f"https://app.jackrabbitclass.com/regv2.asp?id={org_id}"

        # Send SMS via tenant's configured provider
        from app.infrastructure.telephony.factory import TelephonyProviderFactory

        factory = TelephonyProviderFactory(db)
        sms_provider = await factory.get_sms_provider(tenant_id)

        if not sms_provider:
            logger.error(f"[TOOL] send_link: no SMS provider for tenant {tenant_id}")
            return JSONResponse(content={
                "status": "error",
                "message": "SMS not configured for this tenant",
            })

        sms_config = await factory.get_config(tenant_id)
        from_number = factory.get_sms_phone_number(sms_config)

        if not from_number:
            logger.error(f"[TOOL] send_link: no from number for tenant {tenant_id}")
            return JSONResponse(content={
                "status": "error",
                "message": "No SMS phone number configured",
            })

        # Format phone to E.164
        formatted_to = _normalize_phone(to_phone)

        sms_result = await sms_provider.send_sms(
            to=formatted_to,
            from_=from_number,
            body=reg_url,
        )

        logger.info(
            f"[TOOL] send_link SMS sent - to={formatted_to}, from={from_number}, "
            f"message_id={sms_result.message_id}, url={reg_url}"
        )

        return JSONResponse(content={
            "status": "ok",
            "message_id": sms_result.message_id,
            "url_sent": reg_url,
        })

    except Exception as e:
        logger.error(f"[TOOL] Error in send_link: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )



def _map_location_to_code(location: str) -> str | None:
    """Map a location name from conversation to a location code.

    Args:
        location: Location name as mentioned in conversation

    Returns:
        Location code or None if not found
    """
    if not location:
        return None

    location_lower = location.lower().strip()

    # Direct mappings
    location_map = {
        # Cypress variations
        "cypress": "LAFCypress",
        "la fitness cypress": "LAFCypress",
        "lafcypress": "LAFCypress",
        # Langham Creek variations
        "langham creek": "LALANG",
        "langham": "LALANG",
        "la fitness langham creek": "LALANG",
        "lalang": "LALANG",
        # Spring variations
        "spring": "24Spring",
        "24 hour fitness spring": "24Spring",
        "24 hour spring": "24Spring",
        "24spring": "24Spring",
        "24hr spring": "24Spring",
    }

    return location_map.get(location_lower)


def _normalize_level_name(level: str) -> str | None:
    """Normalize a level name from conversation to standard format.

    Args:
        level: Level name as mentioned in conversation

    Returns:
        Normalized level name or None
    """
    if not level:
        return None

    level_lower = level.lower().strip()

    # Level name mappings (conversation -> standard name)
    level_map = {
        # Adult levels
        "adult level 1": "Adult Level 1",
        "adult level 2": "Adult Level 2",
        "adult level 3": "Adult Level 3",
        "adult 1": "Adult Level 1",
        "adult 2": "Adult Level 2",
        "adult 3": "Adult Level 3",
        # Young Adult levels
        "young adult 1": "Young Adult 1",
        "young adult 2": "Young Adult 2",
        "young adult 3": "Young Adult 3",
        "young adult level 1": "Young Adult 1",
        "young adult level 2": "Young Adult 2",
        "young adult level 3": "Young Adult 3",
        # Child levels
        "tadpole": "Tadpole",
        "swimboree": "Swimboree",
        "seahorse": "Seahorse",
        "starfish": "Starfish",
        "minnow": "Minnow",
        "turtle 1": "Turtle 1",
        "turtle 2": "Turtle 2",
        "shark 1": "Shark 1",
        "shark 2": "Shark 2",
        "dolphin": "Dolphin",
        "barracuda": "Barracuda",
    }

    return level_map.get(level_lower, level)  # Return original if no mapping found
