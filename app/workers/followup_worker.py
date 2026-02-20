"""Follow-up worker for processing scheduled SMS follow-up tasks."""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.conversation_service import ConversationService
from app.domain.services.dnc_service import DncService
from app.domain.services.followup_message_service import FollowUpMessageService
from app.domain.services.opt_in_service import OptInService
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.database import get_db
from app.persistence.models.lead import Lead
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.lead_repository import LeadRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Fixed quiet hours: no outbound SMS between 9 PM and 8 AM in tenant timezone
QUIET_HOURS_START = time(21, 0)  # 9:00 PM
QUIET_HOURS_END = time(8, 0)    # 8:00 AM


class FollowUpTaskPayload(BaseModel):
    """Payload for follow-up processing task."""

    tenant_id: int
    lead_id: int
    phone_number: str


@router.post("/followup")
async def process_followup_task(
    request: Request,
    payload: FollowUpTaskPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process scheduled follow-up SMS task.

    This endpoint is called by Cloud Tasks after the configured delay.
    It initiates the outbound SMS conversation for lead qualification.
    """
    try:
        lead_repo = LeadRepository(db)
        lead = await lead_repo.get_by_id(payload.tenant_id, payload.lead_id)

        if not lead:
            logger.warning(f"Lead {payload.lead_id} not found for follow-up")
            return {"status": "skipped", "reason": "lead_not_found"}

        # Check if follow-up was already sent (prevent duplicate sends)
        if lead.extra_data and lead.extra_data.get("followup_sent_at"):
            logger.info(f"Follow-up already sent for lead {payload.lead_id}")
            return {"status": "skipped", "reason": "already_sent"}

        # Get SMS provider using factory (supports Twilio and Telnyx)
        factory = TelephonyProviderFactory(db)
        sms_config = await factory.get_config(payload.tenant_id)

        if not sms_config or not sms_config.is_enabled:
            logger.warning(f"SMS not enabled for tenant {payload.tenant_id}")
            return {"status": "skipped", "reason": "sms_not_enabled"}

        # Get the correct phone number based on provider
        from_phone = factory.get_sms_phone_number(sms_config)
        if not from_phone:
            logger.warning(f"No phone number configured for tenant {payload.tenant_id} (provider: {sms_config.provider})")
            return {"status": "skipped", "reason": "no_phone_number"}

        sms_provider = await factory.get_sms_provider(payload.tenant_id)
        if not sms_provider:
            logger.warning(f"Could not get SMS provider for tenant {payload.tenant_id}")
            return {"status": "skipped", "reason": "provider_not_configured"}

        # Check quiet hours - defer if outside allowed sending window
        defer_result = await _check_quiet_hours_and_defer(sms_config, payload)
        if defer_result is not None:
            return defer_result

        # Check Do Not Contact list - skip if blocked
        dnc_service = DncService(db)
        if await dnc_service.is_blocked(payload.tenant_id, phone=payload.phone_number):
            logger.info(f"DNC block - skipping follow-up for {payload.phone_number}")
            return {"status": "skipped", "reason": "do_not_contact"}

        # Check opt-in status
        opt_in_service = OptInService(db)
        is_opted_in = await opt_in_service.is_opted_in(payload.tenant_id, payload.phone_number)

        if not is_opted_in:
            # For leads from voice calls or email inquiries, consider implied consent
            # (they provided their phone number expecting to be contacted)
            source = lead.extra_data.get("source") if lead.extra_data else None
            if source in ("voice_call", "email"):
                # Auto opt-in with consent type based on source
                consent_method = f"implied_{source}_followup"
                await opt_in_service.opt_in(
                    payload.tenant_id,
                    payload.phone_number,
                    method=consent_method
                )
                logger.info(f"Auto opted-in {payload.phone_number} for {source} follow-up")
            else:
                logger.info(f"Phone {payload.phone_number} not opted in, skipping follow-up")
                return {"status": "skipped", "reason": "not_opted_in"}

        # Create new conversation for follow-up
        conversation_service = ConversationService(db)
        conversation = await conversation_service.create_conversation(
            tenant_id=payload.tenant_id,
            channel="sms",
            external_id=f"followup-{payload.lead_id}",
        )

        # Update conversation with phone number
        from app.persistence.repositories.conversation_repository import ConversationRepository
        conv_repo = ConversationRepository(db)
        conv = await conv_repo.get_by_id(payload.tenant_id, conversation.id)
        if conv:
            conv.phone_number = payload.phone_number
            await db.commit()

        # Update lead with follow-up info (create new dict to trigger SQLAlchemy change detection)
        extra_data = dict(lead.extra_data or {})
        extra_data["followup_conversation_id"] = conversation.id
        extra_data["followup_sent_at"] = datetime.now(timezone.utc).isoformat()
        lead.extra_data = extra_data
        lead.conversation_id = conversation.id  # Update primary conversation link
        await db.commit()

        # Generate initial follow-up message using LLM
        followup_msg_service = FollowUpMessageService(db)
        try:
            initial_message = await followup_msg_service.compose_followup_message(
                tenant_id=payload.tenant_id,
                lead=lead,
            )
            logger.info(f"LLM-generated follow-up message for lead {payload.lead_id}")
        except Exception as e:
            logger.warning(f"LLM follow-up failed for lead {payload.lead_id}, using fallback: {e}")
            initial_message = _generate_initial_message(lead, sms_config)

        # Build status callback URL based on provider
        status_callback_url = None
        if settings.twilio_webhook_url_base:
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.twilio_webhook_url_base}/api/v1/sms{webhook_prefix}/status"

        # Send SMS via the configured provider (Twilio or Telnyx)
        send_result = await sms_provider.send_sms(
            to=payload.phone_number,
            from_=from_phone,
            body=initial_message,
            status_callback=status_callback_url,
        )

        # Store initial message in conversation
        await conversation_service.add_message(
            payload.tenant_id,
            conversation.id,
            "assistant",
            initial_message,
        )

        logger.info(
            f"Follow-up SMS sent: lead_id={payload.lead_id}, "
            f"conversation_id={conversation.id}, message_id={send_result.message_id}, "
            f"provider={send_result.provider}"
        )

        return {
            "status": "success",
            "conversation_id": conversation.id,
            "message_id": send_result.message_id,
            "provider": send_result.provider,
        }

    except Exception as e:
        logger.error(f"Error processing follow-up task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Follow-up processing failed: {str(e)}",
        )


def _generate_initial_message(lead: Lead, sms_config: TenantSmsConfig) -> str:
    """Generate the initial follow-up message.

    Uses subject-specific template if available, then custom template, otherwise contextual message.
    """
    lead_name = lead.name or ""
    first_name = lead_name.split()[0] if lead_name else ""

    # Check for subject-specific template first (for email leads)
    email_subject = lead.extra_data.get("email_subject", "") if lead.extra_data else ""
    if email_subject and sms_config.settings:
        subject_templates = sms_config.settings.get("followup_subject_templates", {})
        for prefix, template_data in subject_templates.items():
            if email_subject.lower().startswith(prefix.lower()):
                # Support both old format (string) and new format (dict with message/delay)
                if isinstance(template_data, dict):
                    template = template_data.get("message", "")
                else:
                    template = template_data  # Legacy string format
                if template:
                    message = template.replace("{name}", lead_name or "there")
                    message = message.replace("{first_name}", first_name or "there")
                    logger.info(f"Using subject-specific template for prefix: {prefix}")
                    return message

    # Check for source-specific template (e.g., __voice_call_default, __chatbot_default)
    source = lead.extra_data.get("source") if lead.extra_data else None
    if source and sms_config.settings:
        subject_templates = sms_config.settings.get("followup_subject_templates", {})
        source_key = f"__{source}_default"
        template_data = subject_templates.get(source_key)
        if template_data:
            if isinstance(template_data, dict):
                template = template_data.get("message", "")
            else:
                template = template_data
            if template:
                message = template.replace("{name}", lead_name or "there")
                message = message.replace("{first_name}", first_name or "there")
                logger.info(f"Using source-specific template for source: {source}")
                return message

    # Check for global custom template in settings
    custom_template = None
    if sms_config.settings:
        custom_template = sms_config.settings.get("followup_initial_message")

    if custom_template:
        # Template variable substitution
        message = custom_template.replace("{name}", lead_name or "there")
        message = message.replace("{first_name}", first_name or "there")
        return message

    # Default contextual message based on source

    if source == "voice_call":
        if first_name:
            return f"Hi {first_name}! Thanks for calling earlier. I wanted to follow up and see if I can help with any other questions. What brings you to us today?"
        return "Hi! Thanks for calling earlier. I wanted to follow up and see if I can help with any other questions. What brings you to us today?"
    elif source == "email":
        if first_name:
            return f"Hi {first_name}! We saw your 'get in touch' form. Can I help answer any questions?"
        return "Hi! We saw your 'get in touch' form. Can I help answer any questions?"
    else:
        if first_name:
            return f"Hi {first_name}! Thanks for reaching out. I wanted to follow up and see how I can help you today."
        return "Hi! Thanks for reaching out. I wanted to follow up and see how I can help you today."


def _is_quiet_hours(tz_name: str) -> bool:
    """Check if current time is within quiet hours (9 PM - 8 AM) in the given timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ValueError):
        tz = ZoneInfo("UTC")
    now_local = datetime.now(timezone.utc).astimezone(tz).time()
    # Quiet hours span midnight: 21:00 -> 08:00
    return now_local >= QUIET_HOURS_START or now_local < QUIET_HOURS_END


def _seconds_until_quiet_hours_end(tz_name: str) -> int:
    """Calculate seconds from now until quiet hours end (8 AM) in the given timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ValueError):
        tz = ZoneInfo("UTC")
    now = datetime.now(timezone.utc).astimezone(tz)
    # Target is 8 AM today or tomorrow
    target = now.replace(hour=QUIET_HOURS_END.hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


async def _check_quiet_hours_and_defer(
    sms_config: TenantSmsConfig,
    payload: FollowUpTaskPayload,
) -> dict[str, Any] | None:
    """If it's quiet hours, reschedule the follow-up and return a response dict.

    Returns None if not in quiet hours (caller should proceed normally).
    """
    tz_name = sms_config.timezone or "UTC"
    if not _is_quiet_hours(tz_name):
        return None

    delay_seconds = _seconds_until_quiet_hours_end(tz_name)
    logger.info(
        f"Quiet hours active for tenant {payload.tenant_id} (tz={tz_name}). "
        f"Deferring follow-up for lead {payload.lead_id} by {delay_seconds}s"
    )

    # Reschedule via Cloud Tasks
    from app.infrastructure.cloud_tasks import CloudTasksClient

    worker_base_url = settings.cloud_tasks_worker_url
    if worker_base_url and worker_base_url.endswith("/process-sms"):
        worker_base_url = worker_base_url[:-12]
    task_url = f"{worker_base_url.rstrip('/')}/followup" if worker_base_url else None

    if not task_url:
        logger.error("Cannot defer follow-up: cloud_tasks_worker_url not configured")
        return {"status": "skipped", "reason": "cannot_defer_no_worker_url"}

    cloud_tasks = CloudTasksClient()
    await cloud_tasks.create_task_async(
        payload={
            "tenant_id": payload.tenant_id,
            "lead_id": payload.lead_id,
            "phone_number": payload.phone_number,
        },
        url=task_url,
        delay_seconds=delay_seconds,
    )

    return {
        "status": "deferred",
        "reason": "quiet_hours",
        "deferred_seconds": delay_seconds,
    }
