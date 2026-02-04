"""Tenant-facing SMS endpoints (no Twilio credentials exposed)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant, is_global_admin
from app.domain.services.dnc_service import DncService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.settings import settings

router = APIRouter()


# Request/Response Models

class SubjectTemplate(BaseModel):
    """Template for a specific email subject prefix."""
    message: str
    delay_minutes: int = 5


def normalize_subject_templates(raw_templates: dict | None) -> dict[str, SubjectTemplate] | None:
    """Normalize subject templates to ensure they match the expected schema.

    Handles both old format (string values) and new format (object with message/delay_minutes).
    """
    if not raw_templates:
        return None

    normalized = {}
    for subject, template_data in raw_templates.items():
        try:
            if isinstance(template_data, str):
                # Old format: just the message string
                normalized[subject] = SubjectTemplate(message=template_data, delay_minutes=5)
            elif isinstance(template_data, dict):
                # New format: {message, delay_minutes}
                message = template_data.get("message", "")
                delay = template_data.get("delay_minutes", 5)
                # Ensure delay is an int
                if isinstance(delay, str):
                    delay = int(delay)
                normalized[subject] = SubjectTemplate(message=message, delay_minutes=delay)
            else:
                # Skip invalid entries
                continue
        except (ValueError, TypeError):
            # Skip entries that can't be parsed
            continue

    return normalized if normalized else None


class SmsSettingsResponse(BaseModel):
    """SMS settings visible to tenant."""
    is_enabled: bool
    phone_number: str | None  # Assigned Twilio number (read-only)
    auto_reply_enabled: bool
    auto_reply_message: str | None
    initial_outreach_message: str | None
    business_hours_enabled: bool
    timezone: str
    business_hours: dict | None
    # Follow-up settings
    followup_enabled: bool
    followup_delay_minutes: int  # Default delay (used when no subject-specific template matches)
    followup_sources: list[str]
    followup_initial_message: str | None
    # Subject-specific templates for email follow-ups
    # Maps subject prefix to {message, delay_minutes}
    followup_subject_templates: dict[str, SubjectTemplate] | None
    # Lead notification settings
    lead_notification_enabled: bool = False
    lead_notification_phone: str | None = None  # Override phone (defaults to business phone)
    lead_notification_channels: list[str] = ["sms", "chat", "voice", "email"]
    lead_notification_quiet_hours_enabled: bool = True


class UpdateSmsSettingsRequest(BaseModel):
    """Tenant-editable SMS settings."""
    is_enabled: bool = True
    auto_reply_enabled: bool = False
    auto_reply_message: str | None = None
    initial_outreach_message: str | None = "Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?"
    business_hours_enabled: bool = False
    timezone: str = "America/Chicago"
    business_hours: dict | None = None
    # Follow-up settings
    followup_enabled: bool = False
    followup_delay_minutes: int = 5  # Default delay (used when no subject-specific template matches)
    followup_sources: list[str] = ["email", "voice_call", "sms"]
    followup_initial_message: str | None = None
    # Subject-specific templates for email follow-ups
    # Maps email subject prefix to {message, delay_minutes}
    followup_subject_templates: dict[str, SubjectTemplate] | None = None
    # Lead notification settings
    lead_notification_enabled: bool = False
    lead_notification_phone: str | None = None  # Override phone (defaults to business phone)
    lead_notification_channels: list[str] = ["sms", "chat", "voice", "email"]
    lead_notification_quiet_hours_enabled: bool = True
    # Admin-only: update assigned phone number
    phone_number: str | None = None


class InitiateOutreachRequest(BaseModel):
    """Request to send initial AI outreach SMS."""
    phone_number: str  # Customer's phone number
    custom_message: str | None = None  # Optional override of default message


class InitiateOutreachResponse(BaseModel):
    """Response from outreach initiation."""
    success: bool
    message_sid: str | None = None
    error: str | None = None
    conversation_id: int | None = None


class SmsConversationSummary(BaseModel):
    """Summary of an SMS conversation."""
    id: int
    phone_number: str
    message_count: int
    last_message_at: str
    last_message_preview: str | None


# Endpoints

@router.get("/settings", response_model=SmsSettingsResponse)
async def get_sms_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SmsSettingsResponse:
    """Get SMS settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        # Return defaults if no config exists
        return SmsSettingsResponse(
            is_enabled=False,
            phone_number=None,
            auto_reply_enabled=False,
            auto_reply_message=None,
            initial_outreach_message=None,
            business_hours_enabled=False,
            timezone="America/Chicago",
            business_hours=None,
            followup_enabled=False,
            followup_delay_minutes=5,
            followup_sources=["email", "voice_call", "sms"],
            followup_initial_message=None,
            followup_subject_templates=None,
            lead_notification_enabled=False,
            lead_notification_phone=None,
            lead_notification_channels=["sms", "chat", "voice", "email"],
            lead_notification_quiet_hours_enabled=True,
        )

    # Extract follow-up settings from config.settings JSON
    settings_json = config.settings or {}

    return SmsSettingsResponse(
        is_enabled=config.is_enabled,
        phone_number=config.twilio_phone_number or config.telnyx_phone_number,  # Read-only, assigned by admin
        auto_reply_enabled=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        initial_outreach_message=settings_json.get("initial_outreach_message"),
        business_hours_enabled=config.business_hours_enabled,
        timezone=config.timezone,
        business_hours=config.business_hours,
        followup_enabled=settings_json.get("followup_enabled", False),
        followup_delay_minutes=settings_json.get("followup_delay_minutes", 5),
        followup_sources=settings_json.get("followup_sources", ["email", "voice_call", "sms"]),
        followup_initial_message=settings_json.get("followup_initial_message"),
        followup_subject_templates=normalize_subject_templates(settings_json.get("followup_subject_templates")),
        lead_notification_enabled=settings_json.get("lead_notification_enabled", False),
        lead_notification_phone=settings_json.get("lead_notification_phone"),
        lead_notification_channels=settings_json.get("lead_notification_channels", ["sms", "chat", "voice", "email"]),
        lead_notification_quiet_hours_enabled=settings_json.get("lead_notification_quiet_hours_enabled", True),
    )


@router.put("/settings", response_model=SmsSettingsResponse)
async def update_sms_settings(
    settings_data: UpdateSmsSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SmsSettingsResponse:
    """Update SMS settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    # Handle phone number update (admin-only)
    phone_number_to_update = None
    if settings_data.phone_number is not None:
        if not is_global_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can update the phone number",
            )
        normalized = _normalize_phone_number(settings_data.phone_number)
        if settings_data.phone_number and not normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid phone number format. Use format: +1XXXXXXXXXX or (XXX) XXX-XXXX",
            )
        phone_number_to_update = normalized  # May be None if clearing

    # Build settings JSON with follow-up config
    # Convert SubjectTemplate Pydantic objects to dicts for JSON storage
    templates_dict = None
    if settings_data.followup_subject_templates:
        templates_dict = {
            subject: template.model_dump()
            for subject, template in settings_data.followup_subject_templates.items()
        }

    new_settings = {
        "initial_outreach_message": settings_data.initial_outreach_message,
        "followup_enabled": settings_data.followup_enabled,
        "followup_delay_minutes": settings_data.followup_delay_minutes,
        "followup_sources": settings_data.followup_sources,
        "followup_initial_message": settings_data.followup_initial_message,
        "followup_subject_templates": templates_dict,
        "lead_notification_enabled": settings_data.lead_notification_enabled,
        "lead_notification_phone": settings_data.lead_notification_phone,
        "lead_notification_channels": settings_data.lead_notification_channels,
        "lead_notification_quiet_hours_enabled": settings_data.lead_notification_quiet_hours_enabled,
    }

    if not config:
        # Create new config
        config = TenantSmsConfig(
            tenant_id=tenant_id,
            is_enabled=False,  # Can't enable without phone number
            auto_reply_outside_hours=settings_data.auto_reply_enabled,
            auto_reply_message=settings_data.auto_reply_message,
            business_hours_enabled=settings_data.business_hours_enabled,
            timezone=settings_data.timezone,
            business_hours=settings_data.business_hours,
            settings=new_settings,
            twilio_phone_number=phone_number_to_update,  # Admin can set phone on creation
        )
        db.add(config)
    else:
        # Update phone number if admin provided one
        if phone_number_to_update is not None:
            config.twilio_phone_number = phone_number_to_update

        # Only allow enabling if phone number is assigned (or being assigned now)
        has_phone = config.twilio_phone_number or config.telnyx_phone_number or phone_number_to_update
        if settings_data.is_enabled and not has_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot enable SMS without an assigned phone number. Contact support.",
            )

        config.is_enabled = settings_data.is_enabled
        config.auto_reply_outside_hours = settings_data.auto_reply_enabled
        config.auto_reply_message = settings_data.auto_reply_message
        config.business_hours_enabled = settings_data.business_hours_enabled
        config.timezone = settings_data.timezone
        config.business_hours = settings_data.business_hours

        # Merge new settings with existing (preserve any other keys)
        existing_settings = config.settings or {}
        config.settings = {**existing_settings, **new_settings}

    await db.commit()
    await db.refresh(config)

    # Extract settings for response
    settings_json = config.settings or {}

    return SmsSettingsResponse(
        is_enabled=config.is_enabled,
        phone_number=config.twilio_phone_number or config.telnyx_phone_number,
        auto_reply_enabled=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        initial_outreach_message=settings_json.get("initial_outreach_message"),
        business_hours_enabled=config.business_hours_enabled,
        timezone=config.timezone,
        business_hours=config.business_hours,
        followup_enabled=settings_json.get("followup_enabled", False),
        followup_delay_minutes=settings_json.get("followup_delay_minutes", 5),
        followup_sources=settings_json.get("followup_sources", ["email", "voice_call", "sms"]),
        followup_initial_message=settings_json.get("followup_initial_message"),
        followup_subject_templates=normalize_subject_templates(settings_json.get("followup_subject_templates")),
        lead_notification_enabled=settings_json.get("lead_notification_enabled", False),
        lead_notification_phone=settings_json.get("lead_notification_phone"),
        lead_notification_channels=settings_json.get("lead_notification_channels", ["sms", "chat", "voice", "email"]),
        lead_notification_quiet_hours_enabled=settings_json.get("lead_notification_quiet_hours_enabled", True),
    )


@router.post("/outreach", response_model=InitiateOutreachResponse)
async def initiate_outreach(
    request: InitiateOutreachRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InitiateOutreachResponse:
    """Send initial AI outreach SMS to a customer.
    
    This creates a new conversation and sends the first message.
    When the customer replies, the LLM will handle the conversation.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    # Get SMS config
    stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config or not config.is_enabled:
        return InitiateOutreachResponse(
            success=False,
            error="SMS is not enabled. Please enable SMS in settings.",
        )
    
    if not config.twilio_phone_number:
        return InitiateOutreachResponse(
            success=False,
            error="No phone number assigned. Contact support to get a number assigned.",
        )
    
    # Normalize phone number
    phone = _normalize_phone_number(request.phone_number)
    if not phone:
        return InitiateOutreachResponse(
            success=False,
            error="Invalid phone number format. Please use format: +1XXXXXXXXXX",
        )

    # Check Do Not Contact list
    dnc_service = DncService(db)
    if await dnc_service.is_blocked(tenant_id, phone=phone):
        return InitiateOutreachResponse(
            success=False,
            error="Cannot contact: This phone number is on the Do Not Contact list.",
        )

    # Get or create conversation
    from app.persistence.repositories.conversation_repository import ConversationRepository
    from app.persistence.models.conversation import Conversation, Message
    
    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_by_phone_number(tenant_id, phone, channel="sms")
    
    if not conversation:
        # Create new conversation
        conversation = Conversation(
            tenant_id=tenant_id,
            channel="sms",
            phone_number=phone,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
    
    # Determine message to send
    message_text = request.custom_message
    if not message_text:
        message_text = (
            config.settings.get("initial_outreach_message") 
            if config.settings 
            else "Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?"
        )
    
    # Send via Twilio
    try:
        from app.infrastructure.twilio_client import TwilioSmsClient
        
        # Use global Twilio credentials (operator's account)
        twilio_client = TwilioSmsClient(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
        )
        
        send_result = twilio_client.send_sms(
            to=phone,
            from_=config.twilio_phone_number,
            body=message_text,
        )
        
        # Store the outgoing message in conversation
        outgoing_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=message_text,
            message_metadata={
                "twilio_message_sid": send_result.get("sid"),
                "outreach_initiated_by": current_user.email,
            },
        )
        db.add(outgoing_message)
        await db.commit()
        
        return InitiateOutreachResponse(
            success=True,
            message_sid=send_result.get("sid"),
            conversation_id=conversation.id,
        )
        
    except Exception as e:
        return InitiateOutreachResponse(
            success=False,
            error=f"Failed to send SMS: {str(e)}",
        )


@router.get("/conversations", response_model=list[SmsConversationSummary])
async def list_sms_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> list[SmsConversationSummary]:
    """List SMS conversations for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    from sqlalchemy import func, desc
    from app.persistence.models.conversation import Conversation, Message
    
    # Get conversations with message counts
    stmt = (
        select(
            Conversation,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .outerjoin(Message, Conversation.id == Message.conversation_id)
        .where(Conversation.tenant_id == tenant_id)
        .where(Conversation.channel == "sms")
        .group_by(Conversation.id)
        .order_by(desc("last_message_at"))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    summaries = []
    for row in rows:
        conv = row[0]
        message_count = row[1] or 0
        last_message_at = row[2]
        
        # Get last message preview
        last_msg_stmt = (
            select(Message.content)
            .where(Message.conversation_id == conv.id)
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        last_msg_result = await db.execute(last_msg_stmt)
        last_msg = last_msg_result.scalar_one_or_none()
        
        preview = None
        if last_msg:
            preview = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg
        
        summaries.append(SmsConversationSummary(
            id=conv.id,
            phone_number=conv.phone_number or "Unknown",
            message_count=message_count,
            last_message_at=last_message_at.isoformat() if last_message_at else "",
            last_message_preview=preview,
        ))
    
    return summaries


def _normalize_phone_number(phone: str) -> str | None:
    """Normalize phone number to E.164 format."""
    import re
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    # Handle US numbers
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 10 and phone.startswith("+"):
        return f"+{digits}"
    
    return None
