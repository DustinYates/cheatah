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
    from app.persistence.models.lead import Lead
    import json

    try:
        body = await request.json()

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
        call_id = (
            metadata.get("call_control_id")
            or metadata.get("call_session_id")
            or payload.get("conversation_id")
            or payload.get("call_control_id")
            or payload.get("call_id")
            or data.get("call_control_id")
            or data.get("conversation_id")
            or body.get("conversation_id")
            or conversation.get("id")
            or data.get("id")
            or ""
        )

        # Phone numbers - for Insights webhook they're in metadata
        from_number = (
            metadata.get("from")
            or metadata.get("telnyx_end_user_target")
            or payload.get("from")
            or payload.get("caller_id")
            or payload.get("end_user_target")
            or data.get("from")
            or data.get("end_user_target")
            or body.get("end_user_target")
            or conversation.get("end_user_target")
            or conversation.get("from")
            or ""
        )
        to_number = (
            metadata.get("to")
            or metadata.get("telnyx_agent_target")
            or payload.get("to")
            or payload.get("called_number")
            or payload.get("agent_target")
            or data.get("to")
            or data.get("agent_target")
            or body.get("agent_target")
            or conversation.get("agent_target")
            or conversation.get("to")
            or ""
        )

        # Duration
        duration = payload.get("duration") or payload.get("call_duration") or data.get("duration") or 0

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

        if isinstance(results, list) and results:
            for result_item in results:
                if isinstance(result_item, dict):
                    result_text = result_item.get("result", "") or result_item.get("value", "")
                elif isinstance(result_item, str):
                    result_text = result_item
                else:
                    continue

                if not result_text:
                    continue

                result_lower = result_text.lower().strip()

                # Identify result type by content
                # Email detection (contains @ and looks like email)
                if "@" in result_text and not caller_email:
                    # Extract email from text
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

        # Create Call record (use naive datetime for DB compatibility)
        now = datetime.utcnow()
        call = Call(
            tenant_id=tenant_id,
            call_sid=call_id or f"telnyx_ai_{now.timestamp()}",
            from_number=from_number,
            to_number=to_number,
            direction="inbound",
            status="completed",
            duration=int(duration) if duration else 0,
            recording_url=recording_url or None,
            started_at=now,
            ended_at=now,
        )
        db.add(call)
        await db.flush()  # Get the call ID

        logger.info(f"Created Call record: id={call.id}")

        # Store transcript and summary in call metadata or separate table
        # For now, we'll create a lead with the information

        # Create or update Lead from caller
        if from_number:
            normalized_from = _normalize_phone(from_number)

            # Check if contact/lead already exists
            existing_lead = await db.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == normalized_from,
                )
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
                lead = Lead(
                    tenant_id=tenant_id,
                    phone=normalized_from,
                    name=caller_name or None,  # Set name on lead if extracted
                    email=caller_email or None,  # Set email on lead if extracted
                    status="new",
                    extra_data={"voice_calls": [call_data]},
                )
                db.add(lead)
                logger.info(f"Created new Lead from AI call: phone={normalized_from}, name={caller_name}, email={caller_email}")
            else:
                # Update existing lead with call info
                existing_data = lead.extra_data or {}
                voice_calls = existing_data.get("voice_calls", [])
                voice_calls.append(call_data)
                existing_data["voice_calls"] = voice_calls
                lead.extra_data = existing_data
                # Update name/email if we got new info and lead doesn't have it
                if caller_name and not lead.name:
                    lead.name = caller_name
                if caller_email and not lead.email:
                    lead.email = caller_email
                logger.info(f"Updated existing Lead with AI call: phone={normalized_from}, name={caller_name}")

        await db.commit()

        return JSONResponse(content={
            "status": "ok",
            "call_id": call.id,
            "tenant_id": tenant_id,
            "lead_created": bool(from_number),
        })

    except Exception as e:
        logger.error(f"Error processing Telnyx AI call webhook: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)})
