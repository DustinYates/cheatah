"""Worker for processing email outreach campaign batches."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.email_outreach_service import EmailOutreachService
from app.persistence.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailOutreachPayload(BaseModel):
    """Payload for email outreach batch processing task."""

    campaign_id: int
    type: str = "send_batch"


@router.post("/email-outreach")
async def process_email_outreach(
    request: Request,
    payload: EmailOutreachPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process a batch of email outreach sends.

    Called by Cloud Tasks. Sends one batch, then schedules
    the next batch if there are remaining recipients.
    """
    try:
        service = EmailOutreachService(db)

        logger.info(f"Processing email outreach batch: campaign_id={payload.campaign_id}")
        result = await service.send_batch(payload.campaign_id)

        logger.info(f"Email outreach batch result: {result}")
        return result

    except Exception as e:
        logger.error(f"Error processing email outreach batch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email outreach processing failed: {str(e)}",
        )
