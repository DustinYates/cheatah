"""Zapier webhook endpoints for callbacks and customer updates."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.domain.services.zapier_integration_service import ZapierIntegrationService
from app.persistence.repositories.jackrabbit_customer_repository import JackrabbitCustomerRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ZapierCallbackPayload(BaseModel):
    """Payload for Zapier callback."""
    correlation_id: str
    type: str  # "customer_lookup" | "customer_query"
    status: str  # "success" | "error"
    data: dict | None = None
    error: str | None = None


class CustomerUpdatePayload(BaseModel):
    """Payload for proactive customer data update from Zapier."""
    tenant_id: int
    jackrabbit_id: str
    action: str  # "update" | "invalidate"
    phone_number: str | None = None
    customer_data: dict | None = None


@router.post("/callback")
async def zapier_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle callback from Zapier with response data.

    This endpoint receives async responses from Zapier after customer lookups
    or customer queries are processed.

    Request body schema:
    {
        "correlation_id": "uuid-string",
        "type": "customer_lookup" | "customer_query",
        "status": "success" | "error",
        "data": { ... response data ... },
        "error": "optional error message"
    }

    Headers:
    - X-Zapier-Signature: HMAC-SHA256 signature for verification (optional)
    """
    try:
        body = await request.json()
        payload = ZapierCallbackPayload(**body)
    except Exception as e:
        logger.warning(f"Invalid Zapier callback payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Get signature from header if present
    signature = request.headers.get(settings.zapier_signature_header)

    # Process the callback
    zapier_service = ZapierIntegrationService(db)
    result = await zapier_service.process_callback(
        correlation_id=payload.correlation_id,
        payload=body,
        signature=signature,
    )

    if not result:
        logger.warning(f"Callback for unknown correlation_id: {payload.correlation_id}")
        # Return 200 anyway to acknowledge receipt (Zapier expects success)
        return JSONResponse(
            content={"status": "ignored", "message": "Unknown correlation_id"},
            status_code=200,
        )

    logger.info(
        f"Processed Zapier callback",
        extra={
            "correlation_id": payload.correlation_id,
            "type": payload.type,
            "status": payload.status,
        },
    )

    return JSONResponse(
        content={"status": "received", "correlation_id": payload.correlation_id},
        status_code=200,
    )


@router.post("/customer-update")
async def zapier_customer_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Handle proactive customer data updates from Zapier.

    Used for cache invalidation when Jackrabbit data changes.
    Zapier can be configured to send updates when customer data is modified.

    Request body schema:
    {
        "tenant_id": 123,
        "jackrabbit_id": "JR-12345",
        "action": "update" | "invalidate",
        "phone_number": "+15551234567",
        "customer_data": { ... optional new data ... }
    }

    Headers:
    - X-Zapier-Signature: HMAC-SHA256 signature for verification (optional)
    """
    try:
        body = await request.json()
        payload = CustomerUpdatePayload(**body)
    except Exception as e:
        logger.warning(f"Invalid customer update payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    customer_repo = JackrabbitCustomerRepository(db)

    if payload.action == "invalidate":
        # Invalidate cached customer data
        if payload.jackrabbit_id:
            deleted = await customer_repo.invalidate_by_jackrabbit_id(
                payload.tenant_id, payload.jackrabbit_id
            )
        elif payload.phone_number:
            deleted = await customer_repo.invalidate_by_phone(
                payload.tenant_id, payload.phone_number
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Either jackrabbit_id or phone_number required for invalidation",
            )

        logger.info(
            f"Cache invalidation {'successful' if deleted else 'no-op'}",
            extra={
                "tenant_id": payload.tenant_id,
                "jackrabbit_id": payload.jackrabbit_id,
                "action": payload.action,
            },
        )

        return JSONResponse(
            content={"status": "invalidated" if deleted else "not_found"},
            status_code=200,
        )

    elif payload.action == "update":
        # Update cached customer data
        if not payload.phone_number or not payload.customer_data:
            raise HTTPException(
                status_code=400,
                detail="phone_number and customer_data required for update",
            )

        customer = await customer_repo.upsert(
            tenant_id=payload.tenant_id,
            jackrabbit_id=payload.jackrabbit_id,
            phone_number=payload.phone_number,
            email=payload.customer_data.get("email"),
            name=payload.customer_data.get("name"),
            customer_data=payload.customer_data,
        )

        logger.info(
            f"Customer cache updated",
            extra={
                "tenant_id": payload.tenant_id,
                "jackrabbit_id": payload.jackrabbit_id,
                "customer_id": customer.id,
            },
        )

        return JSONResponse(
            content={"status": "updated", "customer_id": customer.id},
            status_code=200,
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {payload.action}")
