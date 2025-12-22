"""Voice webhook endpoints for Twilio."""

import logging
from datetime import datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.business_hours_service import is_within_business_hours
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.call_repository import CallRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum number of conversation turns before ending the call
MAX_VOICE_TURNS = 10


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
    - Starts AI conversation or routes to voicemail
    
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
            tenant_id,
            call_sid=CallSid,
            from_number=From,
            to_number=To,
            status=CallStatus,
            direction="inbound",
            started_at=datetime.utcnow(),
        )
        logger.info(f"Created call record: call_sid={CallSid}, tenant_id={tenant_id}, status={CallStatus}")
        
        # Create a voice conversation for this call
        conversation = Conversation(
            tenant_id=tenant_id,
            channel="voice",
            external_id=CallSid,  # Use call SID as external ID
            phone_number=From,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        logger.info(f"Created voice conversation: id={conversation.id}, call_sid={CallSid}")
        
        # Generate TwiML based on business hours
        if is_open:
            # Start AI conversation
            twiml = _generate_greeting_twiml(CallSid, tenant_id, conversation.id)
        else:
            # After hours - voicemail
            twiml = _generate_voicemail_twiml()
        
        return Response(
            content=twiml,
            media_type="application/xml",
        )
        
    except Exception as e:
        logger.error(f"Error processing inbound call webhook: {e}", exc_info=True)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>We apologize, but we encountered an error processing your call. Please try again later.</Say><Hangup/></Response>',
            media_type="application/xml",
        )


@router.post("/gather")
async def gather_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    CallSid: Annotated[str, Form()],
    SpeechResult: Annotated[str | None, Form()] = None,
    Confidence: Annotated[str | None, Form()] = None,
    tenant_id: Annotated[str | None, Form()] = None,
    conversation_id: Annotated[str | None, Form()] = None,
    turn: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle speech input from Twilio Gather.
    
    This endpoint receives transcribed speech from Twilio and:
    - Processes it through the AI
    - Returns TwiML with the AI response and next Gather
    
    Args:
        request: FastAPI request
        db: Database session
        CallSid: Twilio call SID
        SpeechResult: Transcribed speech from caller (optional if no speech detected)
        Confidence: Confidence score for speech recognition
        tenant_id: Tenant ID (passed in action URL)
        conversation_id: Conversation ID (passed in action URL)
        turn: Current turn number
        
    Returns:
        TwiML XML response
    """
    try:
        # Parse turn number
        current_turn = int(turn) if turn else 0
        parsed_tenant_id = int(tenant_id) if tenant_id else None
        parsed_conversation_id = int(conversation_id) if conversation_id else None
        
        # Handle no speech detected
        if not SpeechResult:
            logger.info(f"No speech detected for call: {CallSid}, turn: {current_turn}")
            
            # After 2 no-speech attempts, end the call
            if current_turn >= 2:
                return Response(
                    content=_generate_goodbye_twiml("I didn't catch that. Thank you for calling. Goodbye!"),
                    media_type="application/xml",
                )
            
            # Prompt again
            twiml = _generate_gather_twiml(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn + 1,
                "I'm sorry, I didn't catch that. How can I help you today?",
            )
            return Response(content=twiml, media_type="application/xml")
        
        logger.info(f"Speech received for call {CallSid}: '{SpeechResult}' (confidence: {Confidence})")
        
        # Store user message in conversation
        if parsed_conversation_id:
            # Get next sequence number
            stmt = select(Message).where(
                Message.conversation_id == parsed_conversation_id
            ).order_by(Message.sequence_number.desc())
            result = await db.execute(stmt)
            last_message = result.scalar_one_or_none()
            next_seq = (last_message.sequence_number + 1) if last_message else 1
            
            user_message = Message(
                conversation_id=parsed_conversation_id,
                role="user",
                content=SpeechResult,
                sequence_number=next_seq,
                message_metadata={
                    "call_sid": CallSid,
                    "confidence": Confidence,
                    "source": "voice_transcription",
                },
            )
            db.add(user_message)
            await db.commit()
        
        # Check for end-of-conversation signals
        lower_speech = SpeechResult.lower().strip()
        if any(phrase in lower_speech for phrase in ["goodbye", "bye", "thank you bye", "that's all", "no more questions"]):
            # Generate summary and end call
            ai_response = "Thank you for calling! Have a great day. Goodbye!"
            
            # Store assistant message
            if parsed_conversation_id:
                assistant_message = Message(
                    conversation_id=parsed_conversation_id,
                    role="assistant",
                    content=ai_response,
                    sequence_number=next_seq + 1,
                    message_metadata={"call_sid": CallSid},
                )
                db.add(assistant_message)
                await db.commit()
            
            return Response(
                content=_generate_goodbye_twiml(ai_response),
                media_type="application/xml",
            )
        
        # Check max turns
        if current_turn >= MAX_VOICE_TURNS:
            ai_response = "I appreciate you taking the time to speak with me. To continue helping you, one of our team members will follow up soon. Thank you for calling!"
            return Response(
                content=_generate_goodbye_twiml(ai_response),
                media_type="application/xml",
            )
        
        # Process with AI (will be implemented in voice_service)
        # For now, use a placeholder that will be replaced when voice_service is ready
        from app.domain.services.voice_service import VoiceService
        
        voice_service = VoiceService(db)
        voice_result = await voice_service.process_voice_turn(
            tenant_id=parsed_tenant_id,
            call_sid=CallSid,
            conversation_id=parsed_conversation_id,
            transcribed_text=SpeechResult,
        )
        
        ai_response = voice_result.response_text
        
        # Store assistant message
        if parsed_conversation_id:
            assistant_message = Message(
                conversation_id=parsed_conversation_id,
                role="assistant",
                content=ai_response,
                sequence_number=next_seq + 1,
                message_metadata={"call_sid": CallSid, "intent": voice_result.intent},
            )
            db.add(assistant_message)
            await db.commit()
        
        # Generate next gather TwiML
        twiml = _generate_gather_twiml(
            CallSid,
            parsed_tenant_id,
            parsed_conversation_id,
            current_turn + 1,
            ai_response,
        )
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error processing gather webhook: {e}", exc_info=True)
        return Response(
            content=_generate_goodbye_twiml("I apologize, but I encountered an issue. Please call back or one of our team members will reach out to you. Goodbye!"),
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
    
    When a call is completed, this triggers summary generation.
    
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
            
            # Trigger summary generation for completed calls
            if CallStatus == "completed" and call.duration and call.duration > 5:
                try:
                    from app.domain.services.voice_service import VoiceService
                    voice_service = VoiceService(db)
                    await voice_service.generate_call_summary(call.id)
                    logger.info(f"Generated summary for call: {CallSid}")
                except Exception as summary_error:
                    logger.error(f"Failed to generate call summary: {summary_error}", exc_info=True)
        
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


def _get_webhook_base_url() -> str:
    """Get the base URL for webhooks."""
    return settings.twilio_webhook_url_base or "https://example.com"


def _generate_greeting_twiml(call_sid: str, tenant_id: int, conversation_id: int) -> str:
    """Generate TwiML for greeting and first gather.
    
    Args:
        call_sid: Twilio call SID
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        
    Returns:
        TwiML XML string with greeting and gather
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "turn": 0,
    })
    action_url = f"{base_url}/api/v1/voice/gather?{params}"
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Hello! Thank you for calling. I'm an AI assistant and I'm here to help you. How can I assist you today?</Say>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="3" language="en-US" enhanced="true">
        <Say voice="Polly.Joanna"></Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't catch that. Please call back if you need assistance. Goodbye!</Say>
    <Hangup/>
</Response>'''


def _generate_gather_twiml(
    call_sid: str,
    tenant_id: int | None,
    conversation_id: int | None,
    turn: int,
    message: str,
) -> str:
    """Generate TwiML with a message and next gather.
    
    Args:
        call_sid: Twilio call SID
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        turn: Current turn number
        message: Message to speak
        
    Returns:
        TwiML XML string
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "tenant_id": tenant_id or "",
        "conversation_id": conversation_id or "",
        "turn": turn,
    })
    action_url = f"{base_url}/api/v1/voice/gather?{params}"
    
    # Escape XML special characters in message
    escaped_message = (
        message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escaped_message}</Say>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="3" language="en-US" enhanced="true">
        <Say voice="Polly.Joanna"></Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't hear a response. Thank you for calling. Goodbye!</Say>
    <Hangup/>
</Response>'''


def _generate_goodbye_twiml(message: str) -> str:
    """Generate TwiML for ending the call.
    
    Args:
        message: Goodbye message to speak
        
    Returns:
        TwiML XML string
    """
    # Escape XML special characters
    escaped_message = (
        message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escaped_message}</Say>
    <Hangup/>
</Response>'''


def _generate_voicemail_twiml() -> str:
    """Generate TwiML for closed business hours (voicemail).
    
    Returns:
        TwiML XML string with voicemail prompt
    """
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Thank you for calling. We're currently outside our business hours. Please leave a message after the tone, and we'll get back to you as soon as possible.</Say>
    <Record maxLength="300" finishOnKey="#"/>
    <Say voice="Polly.Joanna">Thank you for your message. We'll contact you soon. Goodbye.</Say>
    <Hangup/>
</Response>'''
