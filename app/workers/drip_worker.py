"""Worker for processing scheduled drip campaign steps."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.drip_campaign_service import DripCampaignService
from app.persistence.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class DripStepPayload(BaseModel):
    """Payload for drip step processing task."""

    tenant_id: int
    enrollment_id: int
    type: str = "advance"  # "advance" or "resume_check"


@router.post("/drip-step")
async def process_drip_step(
    request: Request,
    payload: DripStepPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process a scheduled drip campaign step.

    Called by Cloud Tasks after a configured delay.
    Handles both step advancement and resume checks after response timeouts.
    """
    try:
        drip_service = DripCampaignService(db)

        if payload.type == "resume_check":
            logger.info(
                f"Processing drip resume check: enrollment_id={payload.enrollment_id}"
            )
            result = await drip_service.resume_if_still_responded(payload.enrollment_id)
        else:
            logger.info(
                f"Processing drip step: enrollment_id={payload.enrollment_id}"
            )
            result = await drip_service.advance_step(payload.enrollment_id)

        logger.info(f"Drip step result: {result}")
        return result

    except Exception as e:
        logger.error(f"Error processing drip step: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drip step processing failed: {str(e)}",
        )
