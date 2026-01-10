"""Promise worker for fulfilling AI promises to send information via SMS."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.promise_detector import DetectedPromise
from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
from app.persistence.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class PromiseFulfillmentPayload(BaseModel):
    """Payload for promise fulfillment task."""

    tenant_id: int
    conversation_id: int
    asset_type: str
    confidence: float
    phone: str
    name: str | None = None


@router.post("/fulfill-promise")
async def fulfill_promise_task(
    request: Request,
    payload: PromiseFulfillmentPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Fulfill an AI promise to send information via SMS.

    This endpoint is called immediately after a promise is detected
    in the AI response. It sends the promised content to the customer.

    Args:
        request: FastAPI request
        payload: Promise fulfillment payload
        db: Database session

    Returns:
        Result dictionary with status and details
    """
    logger.info(
        f"Processing promise fulfillment - tenant_id={payload.tenant_id}, "
        f"conversation_id={payload.conversation_id}, asset_type={payload.asset_type}, "
        f"phone={payload.phone}"
    )

    try:
        # Reconstruct the detected promise
        promise = DetectedPromise(
            asset_type=payload.asset_type,
            confidence=payload.confidence,
            original_text="",  # Not needed for fulfillment
        )

        # Fulfill the promise
        fulfillment_service = PromiseFulfillmentService(db)
        result = await fulfillment_service.fulfill_promise(
            tenant_id=payload.tenant_id,
            conversation_id=payload.conversation_id,
            promise=promise,
            phone=payload.phone,
            name=payload.name,
        )

        logger.info(
            f"Promise fulfillment complete - tenant_id={payload.tenant_id}, "
            f"status={result.get('status')}"
        )

        return result

    except Exception as e:
        logger.error(
            f"Promise fulfillment failed - tenant_id={payload.tenant_id}, "
            f"error={str(e)}",
            exc_info=True,
        )
        return {
            "status": "error",
            "error": str(e),
        }
