"""Customer service SMS webhooks for Twilio inbound messages."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.domain.services.customer_service_sms_service import CustomerServiceSmsService
from app.infrastructure.telephony.factory import TelephonyProviderFactory

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/inbound")
async def customer_service_sms_inbound(
    request: Request,
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    Body: Annotated[str, Form()],
    MessageSid: Annotated[str, Form()],
    AccountSid: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Handle inbound SMS via customer service flow.

    This endpoint provides separate routing for customer service vs lead capture.
    It identifies existing customers via Jackrabbit/Zapier and routes them to
    the CustomerServiceAgent for specialized handling.

    Args:
        From: Sender phone number
        To: Recipient phone number (our Twilio number)
        Body: Message content
        MessageSid: Twilio message SID
        AccountSid: Twilio account SID
        db: Database session

    Returns:
        Empty TwiML response (we send response via API)
    """
    logger.info(
        f"Customer service SMS inbound",
        extra={
            "from": From,
            "to": To,
            "message_sid": MessageSid,
        },
    )

    # Get tenant from phone number
    telephony_factory = TelephonyProviderFactory(db)
    tenant_id = await telephony_factory.get_tenant_by_phone_number(To, "twilio")

    if not tenant_id:
        logger.warning(f"No tenant found for phone number: {To}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    # Process through customer service flow
    sms_service = CustomerServiceSmsService(db)
    try:
        result = await sms_service.process_inbound_sms(
            tenant_id=tenant_id,
            phone_number=From,
            message_body=Body,
            twilio_message_sid=MessageSid,
        )

        logger.info(
            f"Customer service SMS processed",
            extra={
                "tenant_id": tenant_id,
                "customer_type": result.customer_type,
                "jackrabbit_id": result.jackrabbit_customer_id,
                "routed_to_lead_capture": result.routed_to_lead_capture,
            },
        )

    except Exception as e:
        logger.exception(f"Error processing customer service SMS: {e}")

    # Return empty TwiML - response is sent via Twilio API
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
