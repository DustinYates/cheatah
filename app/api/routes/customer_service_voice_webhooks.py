"""Customer service voice webhooks for Twilio calls."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.domain.services.customer_service_voice_service import CustomerServiceVoiceService
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.repositories.jackrabbit_customer_repository import JackrabbitCustomerRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def generate_twiml_say(text: str, voice: str = "Polly.Joanna") -> str:
    """Generate TwiML Say element."""
    return f'<Say voice="{voice}">{text}</Say>'


def generate_twiml_gather(
    action_url: str,
    prompt: str,
    voice: str = "Polly.Joanna",
    timeout: int = 5,
) -> str:
    """Generate TwiML Gather element for speech input."""
    return f'''<Gather input="speech" action="{action_url}" timeout="{timeout}" speechTimeout="auto">
    <Say voice="{voice}">{prompt}</Say>
</Gather>'''


def generate_twiml_dial(number: str, caller_id: str | None = None) -> str:
    """Generate TwiML Dial element for call transfer."""
    if caller_id:
        return f'<Dial callerId="{caller_id}">{number}</Dial>'
    return f'<Dial>{number}</Dial>'


def wrap_twiml(*elements: str) -> str:
    """Wrap elements in TwiML Response."""
    content = "".join(elements)
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{content}</Response>'


@router.post("/inbound")
async def customer_service_voice_inbound(
    request: Request,
    CallSid: Annotated[str, Form()],
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    CallStatus: Annotated[str, Form()],
    AccountSid: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Handle inbound voice call via customer service flow.

    Performs customer lookup at call start, personalizes greeting if found.
    Routes to lead capture flow if customer not found.

    Args:
        CallSid: Twilio call SID
        From: Caller phone number
        To: Called phone number (our Twilio number)
        CallStatus: Call status
        AccountSid: Twilio account SID
        db: Database session

    Returns:
        TwiML response with greeting and gather
    """
    logger.info(
        f"Customer service voice inbound",
        extra={
            "call_sid": CallSid,
            "from": From,
            "to": To,
            "status": CallStatus,
        },
    )

    # Get tenant from phone number
    telephony_factory = TelephonyProviderFactory(db)
    tenant_id = await telephony_factory.get_tenant_by_voice_phone_number(To)

    if not tenant_id:
        logger.warning(f"No tenant found for voice number: {To}")
        # Return generic message
        twiml = wrap_twiml(
            generate_twiml_say("Sorry, this number is not configured."),
            "<Hangup/>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Process through customer service voice flow
    voice_service = CustomerServiceVoiceService(db)
    try:
        result = await voice_service.handle_inbound_call(
            tenant_id=tenant_id,
            call_sid=CallSid,
            from_number=From,
        )

        if result.routed_to_lead_capture:
            # Redirect to standard voice webhook
            logger.info(
                f"Routing to lead capture voice flow",
                extra={"tenant_id": tenant_id, "call_sid": CallSid},
            )
            redirect_url = f"{settings.api_v1_prefix}/voice/inbound?from_customer_service=1"
            twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Redirect>{redirect_url}</Redirect></Response>'
            return Response(content=twiml, media_type="application/xml")

        if result.requires_escalation:
            # Handle escalation - could transfer or take message
            twiml = wrap_twiml(
                generate_twiml_say(result.response_text),
                "<Hangup/>"  # For now, just end call - could add transfer logic
            )
            return Response(content=twiml, media_type="application/xml")

        # Customer found - generate greeting and gather
        gather_url = (
            f"{settings.api_v1_prefix}/customer-service/voice/gather"
            f"?tenant_id={tenant_id}"
            f"&jackrabbit_id={result.jackrabbit_customer_id}"
            f"&turn=1"
        )

        twiml = wrap_twiml(
            generate_twiml_gather(
                action_url=gather_url,
                prompt=result.response_text,
            ),
            # If no input, prompt again
            generate_twiml_say("I didn't catch that. How can I help you?"),
            f'<Redirect>{gather_url}</Redirect>',
        )

        logger.info(
            f"Customer service voice greeting sent",
            extra={
                "tenant_id": tenant_id,
                "call_sid": CallSid,
                "jackrabbit_id": result.jackrabbit_customer_id,
            },
        )

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.exception(f"Error processing customer service voice: {e}")
        twiml = wrap_twiml(
            generate_twiml_say("I'm sorry, there was an error. Please try again later."),
            "<Hangup/>"
        )
        return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def customer_service_gather(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    CallSid: Annotated[str, Form()],
    From: Annotated[str, Form()],
    SpeechResult: Annotated[str | None, Form()] = None,
    tenant_id: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
    jackrabbit_id: Annotated[str | None, Query()] = None,
    turn: Annotated[str | None, Query()] = None,
) -> Response:
    """Handle speech input for customer service voice flow.

    Args:
        CallSid: Twilio call SID
        From: Caller phone number
        SpeechResult: Transcribed speech
        tenant_id: Tenant ID from query params
        conversation_id: Conversation ID
        jackrabbit_id: Jackrabbit customer ID
        turn: Turn number
        db: Database session

    Returns:
        TwiML response
    """
    logger.info(
        f"Customer service voice gather",
        extra={
            "call_sid": CallSid,
            "speech_result": SpeechResult,
            "tenant_id": tenant_id,
            "jackrabbit_id": jackrabbit_id,
            "turn": turn,
        },
    )

    if not tenant_id:
        twiml = wrap_twiml(
            generate_twiml_say("I'm sorry, there was an error."),
            "<Hangup/>"
        )
        return Response(content=twiml, media_type="application/xml")

    tenant_id_int = int(tenant_id)
    turn_num = int(turn) if turn else 1

    # Check max turns
    if turn_num > 10:
        twiml = wrap_twiml(
            generate_twiml_say("Thank you for calling. Goodbye!"),
            "<Hangup/>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Get customer from jackrabbit_id
    jackrabbit_customer = None
    if jackrabbit_id:
        customer_repo = JackrabbitCustomerRepository(db)
        jackrabbit_customer = await customer_repo.get_by_jackrabbit_id(
            tenant_id_int, jackrabbit_id
        )

    # Handle no speech input
    if not SpeechResult:
        gather_url = (
            f"{settings.api_v1_prefix}/customer-service/voice/gather"
            f"?tenant_id={tenant_id}"
            f"&jackrabbit_id={jackrabbit_id}"
            f"&turn={turn_num + 1}"
        )
        twiml = wrap_twiml(
            generate_twiml_gather(
                action_url=gather_url,
                prompt="I didn't hear anything. How can I help you?",
            )
        )
        return Response(content=twiml, media_type="application/xml")

    # Process speech through customer service
    voice_service = CustomerServiceVoiceService(db)
    try:
        # Get or find conversation
        conv_id = int(conversation_id) if conversation_id else None

        result = await voice_service.process_voice_turn(
            tenant_id=tenant_id_int,
            call_sid=CallSid,
            from_number=From,
            conversation_id=conv_id or 0,  # Will be created if needed
            transcribed_text=SpeechResult,
            jackrabbit_customer=jackrabbit_customer,
        )

        if result.requires_escalation:
            # End call or transfer
            twiml = wrap_twiml(
                generate_twiml_say(result.response_text),
                "<Hangup/>"
            )
            return Response(content=twiml, media_type="application/xml")

        # Continue conversation
        gather_url = (
            f"{settings.api_v1_prefix}/customer-service/voice/gather"
            f"?tenant_id={tenant_id}"
            f"&jackrabbit_id={jackrabbit_id}"
            f"&turn={turn_num + 1}"
        )

        twiml = wrap_twiml(
            generate_twiml_gather(
                action_url=gather_url,
                prompt=result.response_text,
            ),
            generate_twiml_say("Is there anything else I can help you with?"),
            f'<Redirect>{gather_url}</Redirect>',
        )

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.exception(f"Error processing customer service gather: {e}")
        twiml = wrap_twiml(
            generate_twiml_say("I'm sorry, there was an error. Please try again."),
            "<Hangup/>"
        )
        return Response(content=twiml, media_type="application/xml")
