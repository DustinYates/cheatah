"""Admin endpoints for customer service configuration."""

import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_tenant_admin
from app.persistence.models.tenant import User
from app.persistence.models.zapier_request import ZapierRequest
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository

logger = logging.getLogger(__name__)

router = APIRouter()


class RoutingRulesSchema(BaseModel):
    """Routing rules configuration."""
    enable_sms: bool = True
    enable_voice: bool = True
    fallback_to_lead_capture: bool = True
    auto_respond_pending_lookup: bool = True


class CustomerServiceConfigResponse(BaseModel):
    """Response schema for customer service config."""
    id: int
    tenant_id: int
    is_enabled: bool
    zapier_webhook_url: str | None
    zapier_callback_secret_set: bool  # Don't expose actual secret
    customer_lookup_timeout_seconds: int
    query_timeout_seconds: int
    llm_fallback_enabled: bool
    llm_fallback_prompt_override: str | None
    routing_rules: RoutingRulesSchema | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerServiceConfigUpdate(BaseModel):
    """Update schema for customer service config."""
    is_enabled: bool | None = None
    zapier_webhook_url: str | None = None
    zapier_callback_secret: str | None = None
    customer_lookup_timeout_seconds: int | None = None
    query_timeout_seconds: int | None = None
    llm_fallback_enabled: bool | None = None
    llm_fallback_prompt_override: str | None = None
    routing_rules: RoutingRulesSchema | None = None


class LookupStatsResponse(BaseModel):
    """Response schema for lookup statistics."""
    total_lookups: int
    successful_lookups: int
    failed_lookups: int
    timeout_lookups: int
    average_lookup_time_ms: float | None
    cache_hit_rate: float | None
    period_days: int


class ZapierTestResponse(BaseModel):
    """Response schema for Zapier connection test."""
    success: bool
    message: str
    webhook_url: str | None


@router.get("/config", response_model=CustomerServiceConfigResponse)
async def get_customer_service_config(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerServiceConfigResponse:
    """Get customer service configuration for tenant.

    Returns the current customer service configuration including
    Zapier integration settings and routing rules.
    """
    user, tenant_id = auth
    config_repo = CustomerServiceConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if not config:
        # Return default config (not yet created)
        raise HTTPException(
            status_code=404,
            detail="Customer service not configured. Use PUT to create configuration.",
        )

    return CustomerServiceConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        zapier_webhook_url=config.zapier_webhook_url,
        zapier_callback_secret_set=bool(config.zapier_callback_secret),
        customer_lookup_timeout_seconds=config.customer_lookup_timeout_seconds,
        query_timeout_seconds=config.query_timeout_seconds,
        llm_fallback_enabled=config.llm_fallback_enabled,
        llm_fallback_prompt_override=config.llm_fallback_prompt_override,
        routing_rules=RoutingRulesSchema(**(config.routing_rules or {})),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/config", response_model=CustomerServiceConfigResponse)
async def update_customer_service_config(
    config_update: CustomerServiceConfigUpdate,
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerServiceConfigResponse:
    """Update customer service configuration.

    Creates or updates the customer service configuration for the tenant.
    Includes Zapier webhook URL, callback secret, timeouts, and routing rules.
    """
    user, tenant_id = auth
    config_repo = CustomerServiceConfigRepository(db)

    # Build update data
    update_data = {}
    if config_update.is_enabled is not None:
        update_data["is_enabled"] = config_update.is_enabled
    if config_update.zapier_webhook_url is not None:
        update_data["zapier_webhook_url"] = config_update.zapier_webhook_url
    if config_update.zapier_callback_secret is not None:
        update_data["zapier_callback_secret"] = config_update.zapier_callback_secret
    if config_update.customer_lookup_timeout_seconds is not None:
        update_data["customer_lookup_timeout_seconds"] = config_update.customer_lookup_timeout_seconds
    if config_update.query_timeout_seconds is not None:
        update_data["query_timeout_seconds"] = config_update.query_timeout_seconds
    if config_update.llm_fallback_enabled is not None:
        update_data["llm_fallback_enabled"] = config_update.llm_fallback_enabled
    if config_update.llm_fallback_prompt_override is not None:
        update_data["llm_fallback_prompt_override"] = config_update.llm_fallback_prompt_override
    if config_update.routing_rules is not None:
        update_data["routing_rules"] = config_update.routing_rules.model_dump()

    config = await config_repo.create_or_update(tenant_id, **update_data)

    logger.info(
        f"Customer service config updated",
        extra={
            "tenant_id": tenant_id,
            "user_id": user.id,
            "is_enabled": config.is_enabled,
        },
    )

    return CustomerServiceConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        zapier_webhook_url=config.zapier_webhook_url,
        zapier_callback_secret_set=bool(config.zapier_callback_secret),
        customer_lookup_timeout_seconds=config.customer_lookup_timeout_seconds,
        query_timeout_seconds=config.query_timeout_seconds,
        llm_fallback_enabled=config.llm_fallback_enabled,
        llm_fallback_prompt_override=config.llm_fallback_prompt_override,
        routing_rules=RoutingRulesSchema(**(config.routing_rules or {})),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.post("/test-zapier", response_model=ZapierTestResponse)
async def test_zapier_connection(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ZapierTestResponse:
    """Test Zapier webhook connection.

    Sends a test ping to the configured Zapier webhook URL
    to verify connectivity.
    """
    import httpx

    user, tenant_id = auth
    config_repo = CustomerServiceConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if not config or not config.zapier_webhook_url:
        return ZapierTestResponse(
            success=False,
            message="Zapier webhook URL not configured",
            webhook_url=None,
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.zapier_webhook_url,
                json={
                    "type": "test",
                    "tenant_id": tenant_id,
                    "message": "Connection test from ChatterCheetah",
                },
            )
            response.raise_for_status()

        logger.info(
            f"Zapier connection test successful",
            extra={"tenant_id": tenant_id},
        )

        return ZapierTestResponse(
            success=True,
            message="Successfully connected to Zapier webhook",
            webhook_url=config.zapier_webhook_url,
        )

    except httpx.TimeoutException:
        return ZapierTestResponse(
            success=False,
            message="Connection timeout - Zapier webhook did not respond",
            webhook_url=config.zapier_webhook_url,
        )
    except httpx.HTTPStatusError as e:
        return ZapierTestResponse(
            success=False,
            message=f"HTTP error: {e.response.status_code}",
            webhook_url=config.zapier_webhook_url,
        )
    except Exception as e:
        logger.exception(f"Zapier test failed: {e}")
        return ZapierTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
            webhook_url=config.zapier_webhook_url,
        )


@router.get("/lookup-stats", response_model=LookupStatsResponse)
async def get_lookup_stats(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 7,
) -> LookupStatsResponse:
    """Get customer lookup statistics.

    Returns statistics on customer lookups including success rate,
    average lookup time, and cache hit rate.
    """
    user, tenant_id = auth
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Query lookup statistics
    stmt = select(
        func.count().label("total"),
        func.sum(func.cast(ZapierRequest.status == "completed", Integer)).label("successful"),
        func.sum(func.cast(ZapierRequest.status == "error", Integer)).label("failed"),
        func.sum(func.cast(ZapierRequest.status == "timeout", Integer)).label("timeout"),
    ).where(
        ZapierRequest.tenant_id == tenant_id,
        ZapierRequest.request_type == "customer_lookup",
        ZapierRequest.created_at >= cutoff,
    )

    result = await db.execute(stmt)
    row = result.one()

    total = row.total or 0
    successful = row.successful or 0
    failed = row.failed or 0
    timeout = row.timeout or 0

    # Calculate average lookup time for completed requests
    avg_time_stmt = select(
        func.avg(
            func.extract(
                "epoch",
                ZapierRequest.response_received_at - ZapierRequest.request_sent_at
            ) * 1000
        )
    ).where(
        ZapierRequest.tenant_id == tenant_id,
        ZapierRequest.request_type == "customer_lookup",
        ZapierRequest.status == "completed",
        ZapierRequest.created_at >= cutoff,
    )
    avg_result = await db.execute(avg_time_stmt)
    avg_time = avg_result.scalar()

    return LookupStatsResponse(
        total_lookups=total,
        successful_lookups=successful,
        failed_lookups=failed,
        timeout_lookups=timeout,
        average_lookup_time_ms=float(avg_time) if avg_time else None,
        cache_hit_rate=None,  # Would need to track cache hits separately
        period_days=days,
    )
