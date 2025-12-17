"""SMS worker for processing queued SMS messages from Cloud Tasks."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.domain.services.sms_service import SmsService
from app.persistence.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


class SmsTaskPayload(BaseModel):
    """Payload for SMS processing task."""
    
    tenant_id: int
    phone_number: str
    message_body: str
    twilio_message_sid: str | None = None
    to_number: str | None = None


@router.post("/process-sms")
async def process_sms_task(
    request: Request,
    payload: SmsTaskPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process queued SMS message.
    
    This endpoint is called by Cloud Tasks to process SMS messages asynchronously.
    
    Args:
        request: FastAPI request
        payload: SMS task payload
        db: Database session
        
    Returns:
        Processing result
    """
    try:
        # Validate Cloud Tasks request (in production, verify Cloud Tasks headers)
        # X-CloudTasks-QueueName, X-CloudTasks-TaskName, etc.
        
        sms_service = SmsService(db)
        result = await sms_service.process_inbound_sms(
            tenant_id=payload.tenant_id,
            phone_number=payload.phone_number,
            message_body=payload.message_body,
            twilio_message_sid=payload.twilio_message_sid,
        )
        
        logger.info(
            f"SMS processed: tenant_id={payload.tenant_id}, "
            f"phone={payload.phone_number}, message_sid={result.message_sid}"
        )
        
        return {
            "status": "success",
            "message_sid": result.message_sid,
            "requires_escalation": result.requires_escalation,
            "escalation_id": result.escalation_id,
        }
        
    except Exception as e:
        logger.error(f"Error processing SMS task: {e}", exc_info=True)
        # Return error so Cloud Tasks can retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SMS processing failed: {str(e)}",
        )

