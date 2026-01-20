"""Telnyx webhooks for AI Assistant and SMS."""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.prompt_service import PromptService
from app.domain.services.sms_service import SmsService
from app.domain.services.voice_prompt_transformer import transform_chat_to_voice
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.redis import redis_client
from app.persistence.database import get_db
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
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
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Return dynamic variables for Telnyx AI Assistant.

    Telnyx calls this webhook to fetch variables like the system prompt (X).
    The tenant is identified by the Telnyx phone number being called.

    Args:
        request: FastAPI request (raw to handle various Telnyx formats)
        db: Database session

    Returns:
        Dictionary with dynamic variables, including X (the composed prompt)
    """
    import json

    # Parse raw body to handle different Telnyx formats
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Log raw request for debugging
    logger.info(f"Telnyx dynamic-variables raw body: {json.dumps(body)[:1500]}")

    # Try multiple possible locations for phone numbers
    # Telnyx may send: {to, from} or {data: {payload: {to, from}}} or {agent_target, end_user_target}
    to_number = (
        body.get("to")
        or body.get("agent_target")
        or body.get("telnyx_agent_target")
        or (body.get("data", {}).get("payload", {}) or {}).get("to")
        or (body.get("data", {}).get("payload", {}) or {}).get("agent_target")
        or (body.get("payload", {}) or {}).get("to")
        or ""
    )
    from_number = (
        body.get("from")
        or body.get("end_user_target")
        or body.get("telnyx_end_user_target")
        or (body.get("data", {}).get("payload", {}) or {}).get("from")
        or (body.get("data", {}).get("payload", {}) or {}).get("end_user_target")
        or (body.get("payload", {}) or {}).get("from")
        or ""
    )
    call_control_id = (
        body.get("call_control_id")
        or body.get("call_session_id")
        or body.get("conversation_id")
        or (body.get("data", {}) or {}).get("call_control_id")
        or ""
    )

    # Handle nested phone number objects
    if isinstance(to_number, dict):
        to_number = to_number.get("phone_number", "")
    if isinstance(from_number, dict):
        from_number = from_number.get("phone_number", "")

    logger.info(
        f"Telnyx dynamic variables request",
        extra={
            "to": to_number,
            "from": from_number,
            "call_control_id": call_control_id,
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

    # Get tenant's voice config for fallback prompt
    voice_config_stmt = select(TenantVoiceConfig).where(
        TenantVoiceConfig.tenant_id == tenant_id
    )
    voice_config_result = await db.execute(voice_config_stmt)
    voice_config = voice_config_result.scalar_one_or_none()

    # Compose the voice prompt for this tenant
    prompt_service = PromptService(db)

    # Check if tenant has a dedicated voice prompt bundle
    has_dedicated_voice = await prompt_service.has_dedicated_voice_prompt(tenant_id)

    voice_prompt = await prompt_service.compose_prompt_voice(tenant_id)

    if not voice_prompt:
        logger.warning(f"No prompt configured for tenant {tenant_id}")
        # Use tenant-specific fallback if available, otherwise generic
        if voice_config and voice_config.fallback_voice_prompt:
            return {"X": voice_config.fallback_voice_prompt}
        return {"X": _get_fallback_prompt()}

    # Only apply transform_chat_to_voice if using chat prompt fallback
    # Dedicated voice prompts are already voice-safe and shouldn't be wrapped
    if not has_dedicated_voice:
        voice_prompt = transform_chat_to_voice(voice_prompt)

    logger.info(
        f"Returning dynamic variables for tenant",
        extra={
            "tenant_id": tenant_id,
            "to": to_number,
            "prompt_length": len(voice_prompt),
            "has_dedicated_voice": has_dedicated_voice,
        },
    )

    return {"X": voice_prompt}


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
    """Return a fallback prompt when tenant cannot be identified or prompt fails."""
    return """You are a voice assistant for a local business. You communicate through spoken conversation only.

## CRITICAL VOICE RULES
- Keep responses SHORT (2-3 sentences max)
- Ask only ONE question per turn
- NEVER read URLs, email addresses, or special characters aloud
- For links/websites: "I can text that to you. What's the best number?"
- Sound warm and helpful, not robotic

## YOUR ROLE
- Greet callers warmly and ask how you can help
- Answer basic questions about services, hours, and location
- If you don't know something, say: "I don't have that specific information, but I can take your details and have someone call you back."
- Collect their name and best callback number if needed

## REMEMBER
You are on a PHONE CALL. Keep it conversational, brief, and helpful."""


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

        # Telnyx webhooks typically have: {data: {event_type: ..., payload: {...}}}
        # But Insights webhooks have: {event_type: ..., payload: {metadata: {to, from, ...}, results: [...]}}
        data = body.get("data", body)
        event_type = data.get("event_type") or body.get("event_type") or "unknown"
        payload = data.get("payload") or body.get("payload") or data

        logger.info(f"Telnyx event type: {event_type}")

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
        if not caller_name and not caller_email and call_id:
            from app.settings import settings
            if settings.telnyx_api_key:
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
            else:
                logger.info("No TELNYX_API_KEY configured, skipping transcript fetch")

        # FALLBACK: Try to get transcript from our own database
        # The voice_webhooks.py stores messages in the Conversation table during the call
        if not caller_name and not caller_email and from_number:
            try:
                # Get tenant_id first (we need it for the query)
                temp_tenant_id = await _get_tenant_from_telnyx_number(to_number, db) if to_number else None
                if temp_tenant_id:
                    from app.persistence.models.conversation import Conversation, Message
                    from datetime import timedelta

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
        # Voice assistant: assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d (ChatterCheetah Voice BSS)
        # Text assistant: assistant-d3d25f89-a4df-4ca0-8657-7fe2f53ce348 (ChatterCheetah text BSS)
        VOICE_ASSISTANT_ID = "assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d"
        TEXT_ASSISTANT_ID = "assistant-d3d25f89-a4df-4ca0-8657-7fe2f53ce348"
        is_text_assistant = assistant_id == TEXT_ASSISTANT_ID
        is_voice_assistant = assistant_id == VOICE_ASSISTANT_ID

        # Voice calls have: call.* event types, call_control_id, CallDuration, etc.
        # SMS/chat has: message.* event types, no call_control_id, no duration
        is_voice_call = (
            is_voice_assistant or  # Explicitly from voice assistant
            event_type.startswith("call.") or
            event_type in ("call.conversation.ended", "call.conversation_insights.generated") or
            bool(call_id and call_id.startswith("call_")) or  # Telnyx call IDs start with "call_"
            bool(duration and int(duration) > 0) or  # Voice calls have duration
            bool(recording_url)  # Voice calls may have recordings
        )

        # Also check for SMS-specific indicators
        is_sms_interaction = (
            is_text_assistant or  # Explicitly from text assistant
            event_type.startswith("message.") or
            event_type in ("message.received", "message.sent", "message.delivered")
        )

        if is_sms_interaction or (not is_voice_call and not call_id):
            logger.info(f"Skipping Call record creation for non-voice interaction: event_type={event_type}, call_id={call_id}, assistant_id={assistant_id}, is_text_assistant={is_text_assistant}")
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

                # Add user message (represents the SMS interaction)
                if transcript or summary:
                    # Get next sequence number
                    msg_result = await db.execute(
                        select(Message).where(
                            Message.conversation_id == sms_conversation.id
                        ).order_by(Message.sequence_number.desc()).limit(1)
                    )
                    last_msg = msg_result.scalar_one_or_none()
                    next_seq = (last_msg.sequence_number + 1) if last_msg else 1

                    # Add user message
                    user_msg = Message(
                        conversation_id=sms_conversation.id,
                        role="user",
                        content=transcript or summary or "SMS interaction",
                        sequence_number=next_seq,
                        message_metadata={"source": "telnyx_ai_assistant", "assistant_id": assistant_id},
                    )
                    db.add(user_msg)

                    # Add assistant response message
                    assistant_msg = Message(
                        conversation_id=sms_conversation.id,
                        role="assistant",
                        content=summary or "Response provided",
                        sequence_number=next_seq + 1,
                        message_metadata={"source": "telnyx_ai_assistant", "assistant_id": assistant_id},
                    )
                    db.add(assistant_msg)
                    logger.info(f"Added SMS messages for usage tracking: conversation_id={sms_conversation.id}")

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
                    )
                    db.add(lead)
                    logger.info(f"Created Lead from SMS AI interaction: phone={normalized_from}")
                else:
                    if caller_name and not lead.name:
                        lead.name = caller_name
                    if caller_email and not lead.email:
                        lead.email = caller_email
                    logger.info(f"Updated existing Lead from SMS AI interaction: id={lead.id}")

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
            from datetime import timedelta
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
        else:
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
            )
            db.add(call)
            await db.flush()  # Get the call ID
            logger.info(f"Created new Call record: id={call.id}")

        # Store transcript and summary in call metadata or separate table
        # For now, we'll create a lead with the information

        # Create or update Lead from caller
        lead = None
        if from_number:
            normalized_from = _normalize_phone(from_number)

            # Check if contact/lead already exists (get most recent if multiple)
            existing_lead = await db.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == normalized_from,
                ).order_by(Lead.created_at.desc()).limit(1)
            )
            lead = existing_lead.scalar_one_or_none()

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

            if not lead:
                # Create new lead with extracted info
                # Use phone number as fallback name if no name extracted
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
                logger.info(f"Created new Lead from AI call: phone={normalized_from}, name={caller_name}, email={caller_email}")
            else:
                # Update existing lead with call info
                # Use copy to ensure SQLAlchemy detects the change
                from sqlalchemy.orm.attributes import flag_modified
                logger.info(f"Existing lead extra_data BEFORE: {lead.extra_data}")
                existing_data = dict(lead.extra_data) if lead.extra_data else {}
                voice_calls = list(existing_data.get("voice_calls", []))

                # DEDUP: Check if this call.id already exists in voice_calls
                existing_call_ids = {vc.get("call_id") for vc in voice_calls if isinstance(vc, dict)}
                if call.id not in existing_call_ids:
                    voice_calls.append(call_data)
                    existing_data["voice_calls"] = voice_calls
                    lead.extra_data = existing_data
                    flag_modified(lead, "extra_data")
                    logger.info(f"Added call_id={call.id} to voice_calls for lead {lead.id}")
                else:
                    logger.info(f"Skipping duplicate voice_call entry for call_id={call.id}, lead_id={lead.id}")
                # Stack names/emails if we got new info that's different
                if caller_name:
                    if not lead.name:
                        lead.name = caller_name
                    elif caller_name.lower() not in lead.name.lower():
                        # Append new name if different from existing
                        lead.name = f"{lead.name}, {caller_name}"
                if caller_email:
                    if not lead.email:
                        lead.email = caller_email
                    elif caller_email.lower() not in lead.email.lower():
                        # Append new email if different from existing
                        lead.email = f"{lead.email}, {caller_email}"
                # Update created_at to now so lead appears at top of dashboard
                lead.created_at = now
                logger.info(f"Updated existing Lead id={lead.id} with AI call: phone={normalized_from}, name={caller_name}")

            # Flush to get lead ID
            await db.flush()
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
        link_already_sent = any(indicator in combined_text for indicator in already_sent_indicators)

        is_registration_request = any(kw in combined_text for kw in registration_keywords)

        # [SMS-DEBUG] Log which keywords matched for debugging
        matched_reg_keywords = [kw for kw in registration_keywords if kw in combined_text]
        matched_sent_indicators = [ind for ind in already_sent_indicators if ind in combined_text]
        logger.info(
            f"[SMS-DEBUG] Keyword matching - "
            f"matched_registration_keywords={matched_reg_keywords}, "
            f"matched_sent_indicators={matched_sent_indicators}"
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
        sms_already_sent_for_call = False
        normalized_from_for_dedup = _normalize_phone(from_number) if from_number else None
        redis_dedup_key = (
            f"registration_sms:{tenant_id}:{normalized_from_for_dedup}"
            if normalized_from_for_dedup
            else None
        )

        # Fast-path dedup via Redis (works even if lead is missing)
        if is_registration_request and redis_dedup_key:
            try:
                await redis_client.connect()
                if await redis_client.exists(redis_dedup_key):
                    sms_already_sent_for_call = True
                    logger.info(
                        f"Skipping registration SMS - redis dedup hit: {redis_dedup_key}"
                    )
            except Exception as e:
                logger.warning(f"Redis dedup check failed for {redis_dedup_key}: {e}")

        if lead and call and is_registration_request and from_number and not sms_already_sent_for_call:
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
            f"link_already_sent={link_already_sent}, sms_already_sent_for_call={sms_already_sent_for_call}, "
            f"is_registration_request={is_registration_request}, has_phone={bool(from_number)}, "
            f"will_send={is_registration_request and from_number and not link_already_sent and not sms_already_sent_for_call}"
        )

        if link_already_sent:
            logger.info(
                f"Skipping registration SMS - link already sent during call: "
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
                # Pass summary and transcript so dynamic URL can be built from context
                fulfillment_service = PromiseFulfillmentService(db)
                result = await fulfillment_service.fulfill_promise(
                    tenant_id=tenant_id,
                    conversation_id=int(conversation_id) if str(conversation_id).isdigit() else call.id,
                    promise=promise,
                    phone=from_number,
                    name=caller_name,
                    ai_response=f"{summary or ''}\n{transcript or ''}",  # Include both for URL extraction
                )

                logger.info(
                    f"Registration SMS fulfillment result - tenant_id={tenant_id}, "
                    f"status={result.get('status')}, phone={from_number}, call_id={call.id if call else 'none'}"
                )
                # Set Redis dedup on success to catch retries when lead is missing
                if result.get("status") == "sent" and redis_dedup_key:
                    try:
                        await redis_client.set(redis_dedup_key, "1", ttl=7200)
                        logger.info(f"Set Redis registration dedup key: {redis_dedup_key}")
                    except Exception as e:
                        logger.warning(f"Failed to set Redis registration dedup key {redis_dedup_key}: {e}")
                elif result.get("status") != "sent" and lead and call:
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
                # ROLLBACK: On exception, also try to remove claim
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

        # Handle call.hangup event - update duration
        if event_type == "call.hangup":
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
                    if duration_secs:
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
    from sqlalchemy.orm.attributes import flag_modified

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
