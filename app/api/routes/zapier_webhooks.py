"""Zapier webhook endpoints for callbacks and customer updates."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.domain.services.jackrabbit_data_transformer import transform_jackrabbit_to_account_data
from app.domain.services.zapier_integration_service import ZapierIntegrationService
from app.persistence.repositories.customer_repository import CustomerRepository
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
    """Payload for proactive customer data update from Zapier.

    Accepts either nested `customer_data` dict or flat `name`/`email` fields
    for easier Zapier configuration (Zapier's UI mangles double-underscore keys).
    """
    tenant_id: int
    jackrabbit_id: str
    action: str  # "update" | "invalidate"
    phone_number: str | None = None
    customer_data: dict | None = None
    # Flat alternatives to customer_data (for Zapier convenience)
    name: str | None = None
    email: str | None = None

    def get_customer_data(self) -> dict | None:
        """Return customer_data, building it from flat fields if needed."""
        if self.customer_data:
            return self.customer_data
        if self.name or self.email:
            data = {}
            if self.name:
                data["name"] = self.name
            if self.email:
                data["email"] = self.email
            return data
        return None


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
        # Build customer_data from flat fields or nested dict
        customer_data = payload.get_customer_data()
        if not customer_data:
            raise HTTPException(
                status_code=400,
                detail="name, email, or customer_data required for update",
            )
        # Treat empty string phone as None
        phone = payload.phone_number or None

        customer = await customer_repo.upsert(
            tenant_id=payload.tenant_id,
            jackrabbit_id=payload.jackrabbit_id,
            phone_number=phone,
            email=customer_data.get("email"),
            name=customer_data.get("name"),
            customer_data=customer_data,
        )

        # Sync to customers table for UI display
        main_customer_repo = CustomerRepository(db)
        account_data = transform_jackrabbit_to_account_data(customer_data)
        await main_customer_repo.upsert_from_jackrabbit(
            tenant_id=payload.tenant_id,
            external_customer_id=payload.jackrabbit_id,
            phone=phone,
            name=customer_data.get("name"),
            email=customer_data.get("email"),
            account_data=account_data,
            jackrabbit_customer_id=customer.id,
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


@router.post("/family-sync/{tenant_id}")
async def zapier_family_sync(
    tenant_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Flexible family sync endpoint for Zapier free-tier POST action.

    Accepts raw Jackrabbit trigger data with Data Pass-Through=True.
    Tenant ID is in the URL path, so Zapier's key-value editor doesn't need
    to handle it. The endpoint fuzzy-matches Jackrabbit field names regardless
    of how Zapier mangles the keys.

    URL format: /api/v1/zapier/family-sync/{tenant_id}
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("family-sync: could not parse JSON body")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=400, detail="Empty payload")

    logger.info(f"family-sync raw payload for tenant {tenant_id}: {body}")

    # Fuzzy-match Jackrabbit fields from whatever keys Zapier sends.
    # We check both the key name and fall back to scanning all values.
    def _find(keys: list[str]) -> str | None:
        """Find value by checking multiple possible key names (case-insensitive)."""
        body_lower = {k.lower().replace(" ", "_").replace("-", "_"): v for k, v in body.items()}
        for key in keys:
            k = key.lower().replace(" ", "_").replace("-", "_")
            if k in body_lower:
                val = body_lower[k]
                return str(val).strip() if val else None
        return None

    jackrabbit_id = _find([
        "family_id", "familyid", "family_Id", "id", "fam_id",
        "jackrabbit_id", "jr_id",
    ])
    name = _find([
        "name", "family_name", "familyname", "full_name",
        "first_name", "lastname", "last_name",
    ])
    phone = _find([
        "phone_number", "phone", "home_phone", "homephone",
        "cell_phone", "cellphone", "mobile", "contacts_home_phone",
        "work_phone",
    ])
    email = _find([
        "email", "email1", "email_address", "students_email",
    ])

    if not jackrabbit_id:
        raise HTTPException(
            status_code=400,
            detail="Could not find family/jackrabbit ID in payload",
        )

    # Build customer data from whatever we found
    customer_data = {}
    if name:
        customer_data["name"] = name
    if email:
        customer_data["email"] = email

    if not customer_data:
        # Use the raw body as customer_data so nothing is lost
        customer_data = {k: str(v) for k, v in body.items() if v}

    # Normalize phone (treat empty as None)
    phone = phone if phone else None

    customer_repo = JackrabbitCustomerRepository(db)
    customer = await customer_repo.upsert(
        tenant_id=tenant_id,
        jackrabbit_id=jackrabbit_id,
        phone_number=phone,
        email=email,
        name=name,
        customer_data=customer_data,
    )

    # Sync to customers table
    main_customer_repo = CustomerRepository(db)
    account_data = transform_jackrabbit_to_account_data(customer_data)
    await main_customer_repo.upsert_from_jackrabbit(
        tenant_id=tenant_id,
        external_customer_id=jackrabbit_id,
        phone=phone,
        name=name,
        email=email,
        account_data=account_data,
        jackrabbit_customer_id=customer.id,
    )

    logger.info(
        f"Family synced via Zapier",
        extra={
            "tenant_id": tenant_id,
            "jackrabbit_id": jackrabbit_id,
            "customer_id": customer.id,
        },
    )

    return JSONResponse(
        content={"status": "synced", "customer_id": customer.id},
        status_code=200,
    )
