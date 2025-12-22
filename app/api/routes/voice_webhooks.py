"""Voice webhook endpoints for Twilio."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.business_hours_service import is_within_business_hours
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.tenant import TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.call_repository import CallRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/inbound")
async def inbound_call_webhook(
    request: Request,
    CallSid: Annotated[str, Form()],
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    CallStatus: Annotated[str, Form()],
    AccountSid: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Handle inbound call webhook from Twilio.
    
    This endpoint:
    - Receives webhook from Twilio when a call comes in
    - Looks up tenant by phone number
    - Checks business hours
    - Creates call record in database
    - Returns TwiML response (placeholder message or voicemail)
    
    Args:
        request: FastAPI request
        CallSid: Twilio call SID
        From: Caller phone number
        To: Called Twilio number
        CallStatus: Call status (ringing, in-progress, etc.)
        AccountSid: Twilio account SID
        db: Database session
        
    Returns:
        TwiML XML response
    """
    try:
        # Lookup tenant from phone number
        tenant_id = await _get_tenant_from_voice_number(To, AccountSid, db)
        
        if not tenant_id:
            logger.warning(f"Could not determine tenant for voice phone number: {To}")
            # Return simple response to hang up gracefully
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>We apologize, but we could not process your call. Please try again later.</Say><Hangup/></Response>',
                media_type="application/xml",
            )
        
        # Get business hours configuration (reuse SMS config)
        sms_config = await _get_sms_config_for_tenant(tenant_id, db)
        
        # Check business hours
        is_open = True
        if sms_config and sms_config.business_hours_enabled:
            is_open = is_within_business_hours(
                business_hours=sms_config.business_hours,
                timezone_str=sms_config.timezone or "UTC",
                business_hours_enabled=sms_config.business_hours_enabled,
            )
        
        # Create call record
        call_repo = CallRepository(db)
        call = await call_repo.create(
            tenant_id,  # First positional argument
            call_sid=CallSid,
            from_number=From,
            to_number=To,
            status=CallStatus,
            direction="inbound",
            started_at=datetime.utcnow(),
        )
        logger.info(f"Created call record: call_sid={CallSid}, tenant_id={tenant_id}, status={CallStatus}")
        
        # Generate TwiML based on business hours
        if is_open:
            twiml = _generate_open_hours_twiml()
        else:
            twiml = _generate_voicemail_twiml()
        
        return Response(
            content=twiml,
            media_type="application/xml",
        )
        
    except Exception as e:
        logger.error(f"Error processing inbound call webhook: {e}", exc_info=True)
        # Return error response but don't hang up immediately
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>We apologize, but we encountered an error processing your call. Please try again later.</Say><Hangup/></Response>',
            media_type="application/xml",
        )


@router.post("/status")
async def call_status_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    CallSid: Annotated[str, Form()],
    CallStatus: Annotated[str, Form()],
    CallDuration: Annotated[str | None, Form()] = None,
    RecordingSid: Annotated[str | None, Form()] = None,
    RecordingUrl: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle call status callback from Twilio.
    
    This endpoint receives status updates when:
    - Call status changes (completed, failed, etc.)
    - Recording is completed
    
    Args:
        request: FastAPI request
        CallSid: Twilio call SID
        CallStatus: Call status (completed, failed, busy, no-answer, etc.)
        CallDuration: Call duration in seconds (optional)
        RecordingSid: Recording SID if recording completed (optional)
        RecordingUrl: Recording URL if recording completed (optional)
        db: Database session
        
    Returns:
        Empty response (200 OK)
    """
    try:
        call_repo = CallRepository(db)
        call = await call_repo.get_by_call_sid(CallSid)
        
        if not call:
            logger.warning(f"Call not found for status update: CallSid={CallSid}")
            return Response(status_code=200)
        
        # Update call status
        call.status = CallStatus
        
        # Update duration if provided
        if CallDuration:
            try:
                call.duration = int(CallDuration)
            except (ValueError, TypeError):
                logger.warning(f"Invalid CallDuration: {CallDuration}")
        
        # Update recording info if provided
        if RecordingSid:
            call.recording_sid = RecordingSid
        if RecordingUrl:
            call.recording_url = RecordingUrl
        
        # Update ended_at if call is completed
        if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
            call.ended_at = datetime.utcnow()
        
        call.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"Call status update: CallSid={CallSid}, Status={CallStatus}, Duration={CallDuration}")
        
    except Exception as e:
        logger.error(f"Error processing call status callback: {e}", exc_info=True)
    
    # Always return 200
    return Response(status_code=200)


async def _get_tenant_from_voice_number(
    phone_number: str,
    account_sid: str,
    db: AsyncSession,
) -> int | None:
    """Get tenant ID from voice phone number.
    
    Args:
        phone_number: Twilio voice phone number
        account_sid: Twilio account SID
        db: Database session
        
    Returns:
        Tenant ID or None if not found
    """
    # Try to find tenant by voice phone number in TenantBusinessProfile
    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.twilio_voice_phone == phone_number
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    
    if profile:
        return profile.tenant_id
    
    # Fallback: Try SMS config phone number (some tenants might use same number)
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.twilio_phone_number == phone_number
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if config:
        return config.tenant_id
    
    return None


async def _get_sms_config_for_tenant(
    tenant_id: int,
    db: AsyncSession,
) -> TenantSmsConfig | None:
    """Get SMS config for tenant (used for business hours).
    
    Args:
        tenant_id: Tenant ID
        db: Database session
        
    Returns:
        TenantSmsConfig or None if not found
    """
    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _generate_open_hours_twiml() -> str:
    """Generate TwiML for open business hours.
    
    Returns:
        TwiML XML string with placeholder message
    """
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Thank you for calling. We'll connect you shortly.</Say>
    <Record maxLength="300"/>
    <Say voice="alice">Your message has been recorded. Thank you for calling.</Say>
    <Hangup/>
</Response>'''


def _generate_voicemail_twiml() -> str:
    """Generate TwiML for closed business hours (voicemail).
    
    Returns:
        TwiML XML string with voicemail prompt
    """
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Thank you for calling. We're currently outside our business hours. Please leave a message after the tone, and we'll get back to you as soon as possible.</Say>
    <Record maxLength="300" finishOnKey="#"/>
    <Say voice="alice">Thank you for your message. We'll contact you soon. Goodbye.</Say>
    <Hangup/>
</Response>'''

