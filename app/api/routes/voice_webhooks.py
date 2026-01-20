"""Voice webhook endpoints for Twilio."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.business_hours_service import is_within_business_hours
from app.domain.services.escalation_service import EscalationService
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

# TTL for streaming chunks in Redis (2 minutes)
STREAMING_CHUNKS_TTL = 120

# Enable streaming mode (can be disabled via environment variable)
STREAMING_ENABLED = True

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
    
    Includes comprehensive latency tracking for monitoring.
    
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
    # Start overall endpoint timing
    endpoint_start = time.time()
    
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

        # Check for user request to send information (registration link, schedule, etc.)
        # Run in background to avoid blocking voice response
        asyncio.create_task(_check_and_fulfill_user_request(
            db=db,
            tenant_id=parsed_tenant_id,
            conversation_id=parsed_conversation_id,
            call_sid=CallSid,
            user_message=SpeechResult,
        ))

        # Check for AI promises to send information (registration link, schedule, etc.)
        # Run in background to avoid blocking voice response
        asyncio.create_task(_check_and_fulfill_promise(
            db=db,
            tenant_id=parsed_tenant_id,
            conversation_id=parsed_conversation_id,
            call_sid=CallSid,
            ai_response=ai_response,
        ))

        # Check for handoff/escalation
        if parsed_tenant_id and voice_result.requires_escalation:
            # First, create escalation record via EscalationService
            # This ensures consistent notification handling across all channels
            escalation_service = EscalationService(db)

            # Get call to extract caller info
            call = await _get_call_by_sid(CallSid, db)
            caller_name = await _extract_caller_name_from_conversation(db, parsed_conversation_id)

            confidence_float = float(Confidence) if Confidence else None

            escalation = await escalation_service.check_and_escalate(
                tenant_id=parsed_tenant_id,
                conversation_id=parsed_conversation_id,
                user_message=SpeechResult,
                llm_response=ai_response,
                confidence_score=confidence_float,
                channel="voice",
                customer_phone=call.from_number if call else None,
                customer_email=None,  # Not available in voice
                customer_name=caller_name,
            )

            # Then, execute handoff via HandoffService
            handoff_service = HandoffService(db)

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

                # Note: We no longer call notify_handoff here because
                # EscalationService.check_and_escalate already sent notifications

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
        
        # Log endpoint-level latency metrics
        endpoint_latency = (time.time() - endpoint_start) * 1000
        voice_latency = voice_result.latency_metrics
        logger.info(
            f"Gather webhook latency for {CallSid}: "
            f"endpoint_total={endpoint_latency:.1f}ms, "
            f"voice_processing={voice_latency.total_ms if voice_latency else 'n/a'}ms, "
            f"turn={current_turn}"
        )
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error processing gather webhook: {e}", exc_info=True)
        return Response(
            content=_generate_goodbye_twiml("I apologize, but I encountered an issue. Please call back or one of our team members will reach out to you. Goodbye!"),
            media_type="application/xml",
        )


@router.post("/gather-streaming")
async def gather_streaming_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    CallSid: Annotated[str, Form()],
    SpeechResult: Annotated[str | None, Form()] = None,
    Confidence: Annotated[str | None, Form()] = None,
    tenant_id: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
    turn: Annotated[str | None, Query()] = None,
) -> Response:
    """Handle speech input from Twilio Gather with TRUE streaming LLM response.
    
    This endpoint uses streaming LLM generation for lower perceived latency (TTFA).
    It returns the FIRST chunk immediately as soon as it's available, then uses
    <Redirect> to continue playing remaining chunks via /continue-chunk.
    
    TTFA-optimized flow:
    1. Start LLM streaming immediately (minimal pre-processing)
    2. Return first chunk with TwiML as soon as available
    3. Store remaining chunks in Redis for /continue-chunk
    4. DB writes are deferred to avoid blocking first audio
    
    Args:
        request: FastAPI request
        db: Database session
        CallSid: Twilio call SID
        SpeechResult: Transcribed speech from caller
        Confidence: Confidence score for speech recognition
        tenant_id: Tenant ID (passed in action URL)
        conversation_id: Conversation ID (passed in action URL)
        turn: Current turn number
        
    Returns:
        TwiML XML response with first chunk and optional redirect
    """
    start_time = time.time()
    
    try:
        # Parse parameters (fast, non-blocking)
        current_turn = int(turn) if turn else 0
        parsed_tenant_id = int(tenant_id) if tenant_id else None
        parsed_conversation_id = int(conversation_id) if conversation_id else None
        
        # Handle no speech detected - same as non-streaming
        if not SpeechResult:
            logger.info(f"No speech detected for streaming call: {CallSid}, turn: {current_turn}")
            
            if current_turn >= 2:
                return Response(
                    content=_generate_goodbye_twiml("I didn't catch that. Thank you for calling. Goodbye!"),
                    media_type="application/xml",
                )
            
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn + 1,
                "I'm sorry, I didn't catch that. How can I help you today?",
            )
            return Response(content=twiml, media_type="application/xml")
        
        logger.info(f"TTFA streaming: {CallSid}: '{SpeechResult}' (confidence: {Confidence})")
        
        # Check for end-of-conversation signals (fast path, no LLM needed)
        lower_speech = SpeechResult.lower().strip()
        if any(phrase in lower_speech for phrase in ["goodbye", "bye", "thank you bye", "that's all", "no more questions"]):
            ai_response = "Thank you for calling! Have a great day. Goodbye!"
            
            # Defer DB writes to background
            asyncio.create_task(_store_messages_background(
                db=db,
                conversation_id=parsed_conversation_id,
                call_sid=CallSid,
                user_content=SpeechResult,
                assistant_content=ai_response,
                confidence=Confidence,
                intent=None,
                chunk_count=1,
            ))
            
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
        
        # === TTFA-OPTIMIZED STREAMING ===
        # Import voice service
        from app.domain.services.voice_service import VoiceService
        
        voice_service = VoiceService(db)
        
        # Stream and capture first chunk ASAP
        first_chunk = None
        remaining_chunks = []
        final_intent = None
        requires_escalation = False
        ttfa_ms = None
        
        async for chunk in voice_service.process_voice_turn_streaming(
            tenant_id=parsed_tenant_id,
            call_sid=CallSid,
            conversation_id=parsed_conversation_id,
            transcribed_text=SpeechResult,
        ):
            if first_chunk is None:
                # Capture first chunk and TTFA
                first_chunk = chunk.text
                ttfa_ms = (time.time() - start_time) * 1000
                logger.info(f"TTFA for {CallSid}: {ttfa_ms:.1f}ms")
            else:
                remaining_chunks.append(chunk.text)
            
            if chunk.intent:
                final_intent = chunk.intent
            if chunk.requires_escalation:
                requires_escalation = True
        
        # Handle case where no chunks were generated
        if first_chunk is None:
            first_chunk = "I apologize, but I couldn't generate a response. Could you please repeat that?"
            ttfa_ms = (time.time() - start_time) * 1000
        
        # Handle escalation (this takes priority and bypasses TTFA optimization)
        if parsed_tenant_id and requires_escalation:
            # Create escalation record for consistent notification handling
            escalation_service = EscalationService(db)

            call = await _get_call_by_sid(CallSid, db)
            caller_name = await _extract_caller_name_from_conversation(db, parsed_conversation_id)

            confidence_float = float(Confidence) if Confidence else None

            escalation = await escalation_service.check_and_escalate(
                tenant_id=parsed_tenant_id,
                conversation_id=parsed_conversation_id,
                user_message=SpeechResult,
                llm_response=first_chunk,  # Use first chunk as response
                confidence_score=confidence_float,
                channel="voice",
                customer_phone=call.from_number if call else None,
                customer_email=None,
                customer_name=caller_name,
            )

            # Execute handoff
            from app.domain.services.handoff_service import HandoffService, CallContext

            handoff_service = HandoffService(db)

            call_context = CallContext(
                call_sid=CallSid,
                tenant_id=parsed_tenant_id,
                conversation_id=parsed_conversation_id,
                current_turn=current_turn,
                transcribed_text=SpeechResult,
                intent=final_intent,
                confidence=confidence_float,
            )

            handoff_decision = await handoff_service.evaluate_handoff(call_context)

            if handoff_decision.should_handoff:
                twiml = await handoff_service.execute_handoff(
                    call_sid=CallSid,
                    decision=handoff_decision,
                    tenant_id=parsed_tenant_id,
                )

                # Notifications already sent via EscalationService
                return Response(content=twiml, media_type="application/xml")

        # Generate unique chunk_id for this response
        chunk_id = str(uuid.uuid4())[:8]

        # Full response for logging/storage
        full_response = first_chunk + (" " + " ".join(remaining_chunks) if remaining_chunks else "")

        # Check for AI promises to send information (background, don't block TTFA)
        asyncio.create_task(_check_and_fulfill_promise(
            db=db,
            tenant_id=parsed_tenant_id,
            conversation_id=parsed_conversation_id,
            call_sid=CallSid,
            ai_response=full_response,
        ))

        # Defer DB writes to background task (don't block TTFA)
        asyncio.create_task(_store_messages_background(
            db=db,
            conversation_id=parsed_conversation_id,
            call_sid=CallSid,
            user_content=SpeechResult,
            assistant_content=full_response,
            confidence=Confidence,
            intent=final_intent,
            chunk_count=1 + len(remaining_chunks),
        ))
        
        # Log TTFA metrics
        total_latency = (time.time() - start_time) * 1000
        logger.info(
            f"TTFA streaming for {CallSid}: "
            f"ttfa={ttfa_ms:.1f}ms, total={total_latency:.1f}ms, "
            f"chunks={1 + len(remaining_chunks)}"
        )
        
        # If there are remaining chunks, store in Redis and use redirect
        if remaining_chunks:
            await redis_client.connect()
            chunks_key = f"voice:chunks:{CallSid}:{chunk_id}"
            await redis_client.set(
                chunks_key,
                json.dumps(remaining_chunks),
                ttl=STREAMING_CHUNKS_TTL,
            )
            
            # Return first chunk with redirect to continue-chunk
            twiml = _generate_first_chunk_with_redirect_twiml(
                first_chunk,
                CallSid,
                chunk_id,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn + 1,
            )
        else:
            # Only one chunk, return with gather for next input
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn + 1,
                first_chunk,
            )
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error processing streaming gather webhook: {e}", exc_info=True)
        return Response(
            content=_generate_goodbye_twiml("I apologize, but I encountered an issue. Please call back or one of our team members will reach out to you. Goodbye!"),
            media_type="application/xml",
        )


async def _store_messages_background(
    db: AsyncSession,
    conversation_id: int | None,
    call_sid: str,
    user_content: str,
    assistant_content: str,
    confidence: str | None,
    intent: str | None,
    chunk_count: int,
) -> None:
    """Store user and assistant messages in background to avoid blocking TTFA.
    
    This function is meant to be called via asyncio.create_task() so it runs
    after the HTTP response has been sent to Twilio.
    """
    if not conversation_id:
        return
    
    try:
        # Get next sequence number
        stmt = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.sequence_number.desc()).limit(1)
        result = await db.execute(stmt)
        last_message = result.scalar_one_or_none()
        next_seq = (last_message.sequence_number + 1) if last_message else 1
        
        # Store user message
        user_message = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_content,
            sequence_number=next_seq,
            message_metadata={
                "call_sid": call_sid,
                "confidence": confidence,
                "source": "voice_transcription_streaming_ttfa",
            },
        )
        db.add(user_message)
        
        # Store assistant message
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            sequence_number=next_seq + 1,
            message_metadata={
                "call_sid": call_sid,
                "intent": intent,
                "streaming": True,
                "chunk_count": chunk_count,
                "ttfa_optimized": True,
            },
        )
        db.add(assistant_message)
        
        await db.commit()
        logger.debug(f"Background stored messages for call {call_sid}")
        
    except Exception as e:
        logger.error(f"Background message storage failed for {call_sid}: {e}", exc_info=True)


@router.post("/continue-chunk")
async def continue_chunk_webhook(
    request: Request,
    CallSid: Annotated[str, Form()],
    chunk_id: Annotated[str | None, Query()] = None,
    tenant_id: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
    turn: Annotated[str | None, Query()] = None,
) -> Response:
    """Continue playing remaining chunks from a streaming response.
    
    This endpoint is called via <Redirect> when there are remaining
    chunks to play after the first chunk has been spoken.
    
    Args:
        request: FastAPI request
        CallSid: Twilio call SID
        chunk_id: ID for retrieving remaining chunks from Redis
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        turn: Current turn number
        
    Returns:
        TwiML XML response with next chunk or gather
    """
    try:
        parsed_tenant_id = int(tenant_id) if tenant_id else None
        parsed_conversation_id = int(conversation_id) if conversation_id else None
        current_turn = int(turn) if turn else 0
        
        if not chunk_id:
            # No more chunks, return gather for next input
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn,
                "",  # No message, just gather
            )
            return Response(content=twiml, media_type="application/xml")
        
        # Retrieve remaining chunks from Redis
        await redis_client.connect()
        chunks_key = f"voice:chunks:{CallSid}:{chunk_id}"
        chunks_data = await redis_client.get(chunks_key)
        
        if not chunks_data:
            # Chunks expired or not found, return gather
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn,
                "",
            )
            return Response(content=twiml, media_type="application/xml")
        
        chunks = json.loads(chunks_data)
        
        if not chunks:
            # No more chunks, return gather
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn,
                "",
            )
            return Response(content=twiml, media_type="application/xml")
        
        # Get next chunk
        next_chunk = chunks.pop(0)
        
        if chunks:
            # Store remaining chunks for next continuation
            await redis_client.set(chunks_key, json.dumps(chunks), ttl=STREAMING_CHUNKS_TTL)
            
            # Return TwiML with this chunk and redirect to continue
            twiml = _generate_chunk_continuation_twiml(
                next_chunk,
                CallSid,
                chunk_id,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn,
            )
        else:
            # Last chunk, delete from Redis and return gather
            await redis_client.delete(chunks_key)
            
            twiml = _generate_gather_twiml_streaming(
                CallSid,
                parsed_tenant_id,
                parsed_conversation_id,
                current_turn,
                next_chunk,
            )
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error processing continue chunk webhook: {e}", exc_info=True)
        return Response(
            content=_generate_goodbye_twiml("I apologize, but I encountered an issue. Goodbye!"),
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


import re


async def _extract_caller_name_from_conversation(
    db: AsyncSession,
    conversation_id: int | None,
) -> str | None:
    """Extract caller name from conversation history.

    Args:
        db: Database session
        conversation_id: Conversation ID

    Returns:
        Caller name if found, None otherwise
    """
    if not conversation_id:
        return None

    try:
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "user"
        ).order_by(Message.created_at)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        # Combine all user messages
        user_text = " ".join([m.content for m in messages])

        # Try to extract name using patterns
        # Note: Use [a-zA-Z] instead of [A-Z][a-z] because speech-to-text often outputs lowercase
        name_patterns = [
            r"(?:I'?m|I am|my name is|this is|im|name's|it's)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
            r"(?:call me|you can call me)\s+([a-zA-Z]+)",
        ]

        for pattern in name_patterns:
            matches = re.findall(pattern, user_text, re.IGNORECASE)
            if matches:
                # Return the first match, title-cased
                return matches[0].strip().title()

        return None
    except Exception as e:
        logger.warning(f"Failed to extract caller name: {e}")
        return None


async def _extract_caller_email_from_conversation(
    db: AsyncSession,
    conversation_id: int | None,
) -> str | None:
    """Extract caller email from conversation history.

    Args:
        db: Database session
        conversation_id: Conversation ID

    Returns:
        Caller email if found, None otherwise
    """
    if not conversation_id:
        return None

    try:
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "user"
        ).order_by(Message.created_at)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        # Combine all user messages
        user_text = " ".join([m.content for m in messages])

        # Try to extract email using pattern
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        matches = re.findall(email_pattern, user_text, re.IGNORECASE)
        if matches:
            return matches[0].lower()

        return None
    except Exception as e:
        logger.warning(f"Failed to extract caller email: {e}")
        return None


async def _check_and_fulfill_promise(
    db: AsyncSession,
    tenant_id: int,
    conversation_id: int | None,
    call_sid: str,
    ai_response: str,
) -> None:
    """Check if AI response contains a promise to send info and fulfill it.

    This runs in the background to avoid blocking voice response.

    Args:
        db: Database session
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        call_sid: Twilio call SID
        ai_response: The AI's response text
    """
    try:
        from app.domain.services.promise_detector import PromiseDetector
        from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService

        # [SMS-DEBUG] Log initial parameters for debugging transfer issues
        logger.info(
            f"[SMS-DEBUG] Starting promise check - call_sid={call_sid}, "
            f"tenant_id={tenant_id}, conversation_id={conversation_id}, "
            f"ai_response_length={len(ai_response) if ai_response else 0}"
        )

        # Detect if AI made a promise
        detector = PromiseDetector()
        promise = detector.detect_promise(ai_response)

        # [SMS-DEBUG] Log promise detection result
        logger.info(
            f"[SMS-DEBUG] Promise detection result - call_sid={call_sid}, "
            f"found={bool(promise)}, type={promise.asset_type if promise else 'N/A'}, "
            f"confidence={promise.confidence if promise else 0:.2f}"
        )

        if not promise:
            return

        logger.info(
            f"Promise detected in voice response - call_sid={call_sid}, "
            f"asset_type={promise.asset_type}, confidence={promise.confidence:.2f}"
        )

        # Get caller phone and name
        call = await _get_call_by_sid(call_sid, db)
        if not call:
            logger.warning(f"[SMS-DEBUG] Could not find call for promise fulfillment: {call_sid}")
            return

        caller_phone = call.from_number
        caller_name = await _extract_caller_name_from_conversation(db, conversation_id)

        # [SMS-DEBUG] Log caller info for debugging transfer issues
        logger.info(
            f"[SMS-DEBUG] Caller info retrieved - call_sid={call_sid}, "
            f"caller_phone={caller_phone}, caller_name={caller_name or 'Unknown'}, "
            f"has_phone={bool(caller_phone)}"
        )

        # Handle email promises separately - alert tenant instead of fulfilling
        if promise.asset_type == "email_promise":
            try:
                from app.infrastructure.notifications import NotificationService
                notification_service = NotificationService(db)

                # Try to get caller email from conversation if available
                caller_email = await _extract_caller_email_from_conversation(db, conversation_id)

                # Extract topic from the AI response
                combined_text = promise.original_text.lower() if promise.original_text else ""
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
                    customer_phone=caller_phone,
                    customer_email=caller_email,
                    conversation_id=conversation_id,
                    channel="voice",
                    topic=topic,
                )
                logger.info(
                    f"Email promise alert sent - call_sid={call_sid}, "
                    f"caller={caller_name or 'Unknown'}, phone={caller_phone}, topic={topic}"
                )
            except Exception as e:
                logger.error(f"Failed to send email promise alert: {e}", exc_info=True)
            return  # Don't try to fulfill email promises via SMS

        # Fulfill the promise (for non-email promises)
        fulfillment_service = PromiseFulfillmentService(db)
        result = await fulfillment_service.fulfill_promise(
            tenant_id=tenant_id,
            conversation_id=conversation_id or 0,
            promise=promise,
            phone=caller_phone,
            name=caller_name,
        )

        logger.info(
            f"Promise fulfillment result - call_sid={call_sid}, "
            f"status={result.get('status')}, asset_type={promise.asset_type}"
        )

    except Exception as e:
        logger.error(f"Error in promise fulfillment: {e}", exc_info=True)


async def _check_and_fulfill_user_request(
    db: AsyncSession,
    tenant_id: int,
    conversation_id: int | None,
    call_sid: str,
    user_message: str,
) -> None:
    """Check if user message contains a request for info and fulfill it.

    This runs in the background to avoid blocking voice response.

    Args:
        db: Database session
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        call_sid: Twilio call SID
        user_message: The user's transcribed speech
    """
    try:
        from app.domain.services.user_request_detector import UserRequestDetector
        from app.domain.services.promise_detector import DetectedPromise
        from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService

        # Detect if user requested information
        detector = UserRequestDetector()
        request = detector.detect_request(user_message)

        if not request or request.confidence < 0.6:
            return

        logger.info(
            f"User request detected in voice call - call_sid={call_sid}, "
            f"asset_type={request.asset_type}, confidence={request.confidence:.2f}"
        )

        # Get caller phone and name
        call = await _get_call_by_sid(call_sid, db)
        if not call:
            logger.warning(f"Could not find call for user request fulfillment: {call_sid}")
            return

        caller_phone = call.from_number
        caller_name = await _extract_caller_name_from_conversation(db, conversation_id)

        # Create a DetectedPromise to use the same fulfillment service
        promise = DetectedPromise(
            asset_type=request.asset_type,
            confidence=request.confidence,
            original_text=request.original_text,
        )

        # Fulfill the request
        fulfillment_service = PromiseFulfillmentService(db)
        result = await fulfillment_service.fulfill_promise(
            tenant_id=tenant_id,
            conversation_id=conversation_id or 0,
            promise=promise,
            phone=caller_phone,
            name=caller_name,
        )

        logger.info(
            f"User request fulfillment result - call_sid={call_sid}, "
            f"status={result.get('status')}, asset_type={request.asset_type}"
        )

    except Exception as e:
        logger.error(f"Error in user request fulfillment: {e}", exc_info=True)


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
    
    # Optimized TwiML with:
    # - speechTimeout="2" (reduced from 3s for faster turn-taking)
    # - hints for better speech recognition
    # - voice="Polly.Joanna" for more natural sound (faster than default)
    # - Barge-in enabled: <Say> inside <Gather> allows caller to interrupt
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="2" language="en-US" hints="yes, no, help, schedule, appointment, price, hours, information">
        <Say voice="Polly.Joanna">{escaped_greeting}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn&apos;t catch that. Please call back if you need assistance. Goodbye!</Say>
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
    
    # Optimized TwiML with:
    # - speechTimeout="2" (reduced from 3s for faster turn-taking)
    # - hints for better speech recognition
    # - voice="Polly.Joanna" for more natural sound
    # - Barge-in enabled: <Say> inside <Gather> allows caller to interrupt
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="2" language="en-US" hints="yes, no, help, schedule, appointment, price, hours, information, thank you, goodbye">
        <Say voice="Polly.Joanna">{escaped_message}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn&apos;t hear a response. Thank you for calling. Goodbye!</Say>
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
    <Say voice="Polly.Joanna">{escaped_message}</Say>
    <Record maxLength="300" finishOnKey="#"/>
    <Say voice="Polly.Joanna">Thank you for your message. We&apos;ll contact you soon. Goodbye.</Say>
    <Hangup/>
</Response>'''


def _generate_gather_twiml_streaming(
    call_sid: str,
    tenant_id: int | None,
    conversation_id: int | None,
    turn: int,
    message: str,
) -> str:
    """Generate TwiML with a message and next streaming-enabled gather.
    
    Similar to _generate_gather_twiml but uses the streaming gather endpoint
    for the next action, enabling streaming LLM responses.
    
    Args:
        call_sid: Twilio call SID
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        turn: Current turn number
        message: Message to speak (can be empty)
        
    Returns:
        TwiML XML string
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "tenant_id": tenant_id or "",
        "conversation_id": conversation_id or "",
        "turn": turn,
    })
    # Use streaming endpoint
    action_url = f"{base_url}/api/v1/voice/gather-streaming?{params}".replace("&", "&amp;")
    
    # Handle empty message (just gather, no Say)
    if not message or not message.strip():
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="2" language="en-US" hints="yes, no, help, schedule, appointment, price, hours, information, thank you, goodbye">
        <Say></Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn&apos;t hear a response. Thank you for calling. Goodbye!</Say>
    <Hangup/>
</Response>'''
    
    # Escape XML special characters in message
    escaped_message = (
        message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    # Barge-in enabled: <Say> inside <Gather> allows caller to interrupt
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="2" language="en-US" hints="yes, no, help, schedule, appointment, price, hours, information, thank you, goodbye">
        <Say voice="Polly.Joanna">{escaped_message}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn&apos;t hear a response. Thank you for calling. Goodbye!</Say>
    <Hangup/>
</Response>'''


def _generate_first_chunk_with_redirect_twiml(
    chunk_text: str,
    call_sid: str,
    chunk_id: str,
    tenant_id: int | None,
    conversation_id: int | None,
    turn: int,
) -> str:
    """Generate TwiML for first chunk with redirect to continue-chunk.
    
    This is used for TTFA optimization: we return the first chunk immediately
    and use <Redirect> to fetch and speak remaining chunks.
    
    Args:
        chunk_text: Text of the first chunk to speak
        call_sid: Twilio call SID
        chunk_id: ID for retrieving remaining chunks from Redis
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        turn: Current turn number
        
    Returns:
        TwiML XML string with Say and Redirect
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "chunk_id": chunk_id,
        "tenant_id": tenant_id or "",
        "conversation_id": conversation_id or "",
        "turn": turn,
    })
    redirect_url = f"{base_url}/api/v1/voice/continue-chunk?{params}".replace("&", "&amp;")
    
    # Escape XML special characters
    escaped_chunk = (
        chunk_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escaped_chunk}</Say>
    <Redirect method="POST">{redirect_url}</Redirect>
</Response>'''


def _generate_chunk_continuation_twiml(
    chunk_text: str,
    call_sid: str,
    chunk_id: str,
    tenant_id: int | None,
    conversation_id: int | None,
    turn: int,
) -> str:
    """Generate TwiML for continuing with remaining chunks.
    
    This TwiML says the current chunk and then redirects to continue
    with any remaining chunks.
    
    Args:
        chunk_text: Text of the current chunk to speak
        call_sid: Twilio call SID
        chunk_id: ID for retrieving remaining chunks
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        turn: Current turn number
        
    Returns:
        TwiML XML string with Say and Redirect
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "chunk_id": chunk_id,
        "tenant_id": tenant_id or "",
        "conversation_id": conversation_id or "",
        "turn": turn,
    })
    redirect_url = f"{base_url}/api/v1/voice/continue-chunk?{params}".replace("&", "&amp;")
    
    # Escape XML special characters
    escaped_chunk = (
        chunk_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escaped_chunk}</Say>
    <Redirect method="POST">{redirect_url}</Redirect>
</Response>'''


def _generate_greeting_twiml_streaming(
    call_sid: str,
    tenant_id: int,
    conversation_id: int,
    greeting: str | None = None,
    disclosure: str | None = None,
) -> str:
    """Generate TwiML for greeting that uses streaming gather endpoint.
    
    Similar to _generate_greeting_twiml but uses streaming endpoint
    for subsequent interactions.
    
    Args:
        call_sid: Twilio call SID
        tenant_id: Tenant ID
        conversation_id: Conversation ID
        greeting: Custom greeting text
        disclosure: Recording disclosure text
        
    Returns:
        TwiML XML string with greeting and streaming-enabled gather
    """
    base_url = _get_webhook_base_url()
    params = urlencode({
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "turn": 0,
    })
    # Use streaming endpoint
    action_url = f"{base_url}/api/v1/voice/gather-streaming?{params}".replace("&", "&amp;")
    
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
    
    # Barge-in enabled: <Say> inside <Gather> allows caller to interrupt
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="{action_url}" method="POST" speechTimeout="2" language="en-US" hints="yes, no, help, schedule, appointment, price, hours, information">
        <Say voice="Polly.Joanna">{escaped_greeting}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn&apos;t catch that. Please call back if you need assistance. Goodbye!</Say>
    <Hangup/>
</Response>'''
