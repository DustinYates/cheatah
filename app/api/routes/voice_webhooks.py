"""Voice webhook endpoints for Twilio."""

import logging
from datetime import datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.business_hours_service import is_within_business_hours
from app.infrastructure.redis import redis_client
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.call_repository import CallRepository
from app.settings import settings

logger = logging.getLogger(__name__)

# Idempotency TTL for webhook deduplication (5 minutes)
WEBHOOK_IDEMPOTENCY_TTL = 300

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
        # Check for duplicate webhook (idempotency)
        idempotency_key = f"voice:inbound:{CallSid}"
        await redis_client.connect()
        
        if await redis_client.exists(idempotency_key):
            logger.info(f"Duplicate inbound call webhook for CallSid: {CallSid}, returning cached response")
            # Check if call already exists and return appropriate TwiML
            existing_call = await _get_call_by_sid(CallSid, db)
            if existing_call:
                # Return a gather TwiML to continue the conversation
                stmt = select(Conversation).where(Conversation.external_id == CallSid)
                result = await db.execute(stmt)
                conversation = result.scalar_one_or_none()
                if conversation:
                    twiml = _generate_gather_twiml(
                        CallSid,
                        existing_call.tenant_id,
                        conversation.id,
                        0,
                        "I'm here to help. What can I do for you?",
                    )
                    return Response(content=twiml, media_type="application/xml")
            
            # Fallback - just acknowledge
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>Thank you for calling. How can I help you?</Say></Response>',
                media_type="application/xml",
            )
        
        # Mark this webhook as processed
        await redis_client.set(idempotency_key, "processing", ttl=WEBHOOK_IDEMPOTENCY_TTL)
        
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
        
        # Create call record (check if already exists for idempotency)
        call_repo = CallRepository(db)
        existing_call = await call_repo.get_by_call_sid(CallSid)
        
        if existing_call:
            # Call already exists - this is a duplicate webhook
            logger.info(f"Call record already exists for CallSid: {CallSid}, using existing")
            call = existing_call
        else:
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
        
        # Create or get voice conversation for this call
        stmt = select(Conversation).where(Conversation.external_id == CallSid)
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
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
        else:
            logger.info(f"Using existing voice conversation: id={conversation.id}, call_sid={CallSid}")
        
        # Get tenant-specific greeting and disclosure
        from app.domain.services.voice_config_service import VoiceConfigService
        voice_config_service = VoiceConfigService(db)
        greeting_config = await voice_config_service.get_greeting_and_disclosure(tenant_id)
        
        # Generate TwiML based on business hours
        if is_open:
            # Start AI conversation with tenant-specific greeting
            twiml = _generate_greeting_twiml(
                CallSid,
                tenant_id,
                conversation.id,
                greeting=greeting_config.get("greeting"),
                disclosure=greeting_config.get("disclosure"),
            )
        else:
            # After hours - voicemail with tenant-specific message
            twiml = _generate_voicemail_twiml(
                message=greeting_config.get("after_hours_message")
            )
        
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
    tenant_id: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
    turn: Annotated[str | None, Query()] = None,
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
            # Get next sequence number - use limit(1) to get only the latest message
            stmt = select(Message).where(
                Message.conversation_id == parsed_conversation_id
            ).order_by(Message.sequence_number.desc()).limit(1)
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
        
        # Process with AI
        from app.domain.services.voice_service import VoiceService
        from app.domain.services.handoff_service import HandoffService, CallContext
        from app.infrastructure.notifications import NotificationService
        
        voice_service = VoiceService(db)
        voice_result = await voice_service.process_voice_turn(
            tenant_id=parsed_tenant_id,
            call_sid=CallSid,
            conversation_id=parsed_conversation_id,
            transcribed_text=SpeechResult,
        )
        
        ai_response = voice_result.response_text
        
        # Check for handoff/escalation
        if parsed_tenant_id and voice_result.requires_escalation:
            handoff_service = HandoffService(db)
            
            # Build call context for handoff decision
            confidence_float = float(Confidence) if Confidence else None
            call_context = CallContext(
                call_sid=CallSid,
                tenant_id=parsed_tenant_id,
                conversation_id=parsed_conversation_id,
                current_turn=current_turn,
                transcribed_text=SpeechResult,
                intent=voice_result.intent,
                confidence=confidence_float,
            )
            
            # Evaluate if we should handoff
            handoff_decision = await handoff_service.evaluate_handoff(call_context)
            
            if handoff_decision.should_handoff:
                # Execute handoff and return appropriate TwiML
                twiml = await handoff_service.execute_handoff(
                    call_sid=CallSid,
                    decision=handoff_decision,
                    tenant_id=parsed_tenant_id,
                )
                
                # Send handoff notification
                notification_service = NotificationService(db)
                call = await _get_call_by_sid(CallSid, db)
                if call:
                    await notification_service.notify_handoff(
                        tenant_id=parsed_tenant_id,
                        call_id=call.id,
                        reason=handoff_decision.reason or "escalation_requested",
                        caller_phone=call.from_number,
                        handoff_mode=handoff_decision.handoff_mode or "take_message",
                        transfer_number=handoff_decision.transfer_number,
                    )
                
                return Response(content=twiml, media_type="application/xml")
        
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
    # Normalize phone number - Twilio may send with or without + prefix
    # Try multiple formats to handle inconsistencies
    phone_variants = [phone_number]
    if phone_number.startswith("+"):
        # Also try without the + prefix
        phone_variants.append(phone_number[1:])
    else:
        # Also try with the + prefix
        phone_variants.append(f"+{phone_number}")
    
    # Also handle spaces that might appear in logs (e.g., " 18333615689")
    phone_variants = [p.strip() for p in phone_variants]
    
    logger.info(f"Looking up tenant for phone variants: {phone_variants}")
    
    # Try to find tenant by voice phone number in TenantBusinessProfile
    for phone in phone_variants:
        stmt = select(TenantBusinessProfile).where(
            TenantBusinessProfile.twilio_voice_phone == phone
        )
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if profile:
            logger.info(f"Found tenant {profile.tenant_id} via TenantBusinessProfile for phone {phone}")
            return profile.tenant_id
    
    # Fallback: Try SMS config phone number (some tenants might use same number)
    for phone in phone_variants:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.twilio_phone_number == phone
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if config:
            logger.info(f"Found tenant {config.tenant_id} via TenantSmsConfig for phone {phone}")
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


async def _get_call_by_sid(
    call_sid: str,
    db: AsyncSession,
) -> Call | None:
    """Get call by Twilio call SID.
    
    Args:
        call_sid: Twilio call SID
        db: Database session
        
    Returns:
        Call or None if not found
    """
    stmt = select(Call).where(Call.call_sid == call_sid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _get_webhook_base_url() -> str:
    """Get the base URL for webhooks."""
    return settings.twilio_webhook_url_base or "https://example.com"


def _generate_greeting_twiml(
    call_sid: str,
    tenant_id: int,
    conversation_id: int,
    greeting: str | None = None,
    disclosure: str | None = None,
) -> str:
    """Generate TwiML for greeting and first gather.
    
    Args:
        call_sid: Twilio call SID
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        greeting: Custom greeting text
        disclosure: Recording disclosure text
        
    Returns:
        TwiML XML string with greeting and gather
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "turn": 0,
    })
    # Escape & to &amp; for valid XML
    action_url = f"{base_url}/api/v1/voice/gather?{params}".replace("&", "&amp;")
    
    # Use default greeting if not provided
    greeting_text = greeting or (
        "Hello! Thank you for calling. I'm an AI assistant and I'm here to help you. "
        "How can I assist you today?"
    )
    
    # Add disclosure if provided
    full_greeting = greeting_text
    if disclosure:
        full_greeting = f"{disclosure} {greeting_text}"
    
    # Escape XML special characters
    escaped_greeting = (
        full_greeting
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{escaped_greeting}</Say>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="3" language="en-US">
        <Say></Say>
    </Gather>
    <Say>I didn't catch that. Please call back if you need assistance. Goodbye!</Say>
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
    # Escape & to &amp; for valid XML
    action_url = f"{base_url}/api/v1/voice/gather?{params}".replace("&", "&amp;")
    
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
    <Say>{escaped_message}</Say>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="3" language="en-US">
        <Say></Say>
    </Gather>
    <Say>I didn't hear a response. Thank you for calling. Goodbye!</Say>
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
    <Say>{escaped_message}</Say>
    <Hangup/>
</Response>'''


def _generate_voicemail_twiml(message: str | None = None) -> str:
    """Generate TwiML for closed business hours (voicemail).
    
    Args:
        message: Custom voicemail message (optional)
    
    Returns:
        TwiML XML string with voicemail prompt
    """
    voicemail_message = message or (
        "Thank you for calling. We're currently outside our business hours. "
        "Please leave a message after the tone, and we'll get back to you as soon as possible."
    )
    
    # Escape XML special characters
    escaped_message = (
        voicemail_message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{escaped_message}</Say>
    <Record maxLength="300" finishOnKey="#"/>
    <Say>Thank you for your message. We'll contact you soon. Goodbye.</Say>
    <Hangup/>
</Response>'''
