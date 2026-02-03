"""Shared dependencies and utilities for analytics endpoints.

This module consolidates the date range parsing, timezone resolution,
and datetime conversion logic that was duplicated across all analytics endpoints.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated

import pytz
from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_sms_config import TenantSmsConfig


@dataclass
class AnalyticsDateRange:
    """Resolved date range for analytics queries.

    Attributes:
        tenant_id: Tenant ID for queries
        start_date: Start date (local timezone)
        end_date: End date (local timezone)
        start_datetime: Start datetime in UTC (for DB queries)
        end_datetime: End datetime in UTC (for DB queries)
        timezone: Effective timezone name
        tenant_start_date: Tenant's onboarding date
    """
    tenant_id: int
    start_date: date
    end_date: date
    start_datetime: datetime
    end_datetime: datetime
    timezone: str
    tenant_start_date: date


def normalize_date(value: date | datetime | str | None) -> date | None:
    """Normalize various date inputs to a date object.

    Args:
        value: Date as date, datetime, ISO string, or None

    Returns:
        Normalized date or None if invalid
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return None
    return None


def resolve_timezone(value: str | None) -> str:
    """Resolve timezone string to valid pytz timezone name.

    Args:
        value: Timezone name or None

    Returns:
        Valid timezone name, defaults to "UTC" if invalid
    """
    if not value:
        return "UTC"
    try:
        pytz.timezone(value)
        return value
    except pytz.UnknownTimeZoneError:
        return "UTC"


async def get_tenant_timezone(
    db: AsyncSession,
    tenant_id: int,
) -> str | None:
    """Get tenant's configured timezone from SMS config.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Timezone string or None if not configured
    """
    result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_tenant_created_at(
    db: AsyncSession,
    tenant_id: int,
) -> datetime | None:
    """Get tenant's creation timestamp.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Tenant created_at timestamp or None if not found
    """
    result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    return result.scalar_one_or_none()


def compute_date_range(
    tenant_id: int,
    start_date: str | None,
    end_date: str | None,
    tenant_created_at: datetime,
    timezone: str,
    default_days: int = 30,
) -> AnalyticsDateRange:
    """Compute the effective date range for analytics queries.

    Handles:
    - Default to last N days if no dates provided
    - Clamp to tenant start date
    - Clamp to today (no future dates)
    - Convert local dates to UTC datetimes for DB queries

    Args:
        tenant_id: Tenant ID
        start_date: Start date string (optional)
        end_date: End date string (optional)
        tenant_created_at: Tenant's creation timestamp
        timezone: Effective timezone name
        default_days: Default range in days when no dates provided

    Returns:
        AnalyticsDateRange with all computed values
    """
    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()

    parsed_start = normalize_date(start_date)
    parsed_end = normalize_date(end_date)

    # Apply defaults
    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=default_days - 1)
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=default_days - 1)
    elif parsed_end is None and parsed_start is not None:
        parsed_end = today

    range_start = parsed_start or tenant_start_date
    range_end = parsed_end or today

    # Clamp to valid bounds
    if range_start < tenant_start_date:
        range_start = tenant_start_date
    if range_end > today:
        range_end = today
    if range_start > range_end:
        range_start = range_end

    # Convert to UTC datetimes
    tz = pytz.timezone(timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    return AnalyticsDateRange(
        tenant_id=tenant_id,
        start_date=range_start,
        end_date=range_end,
        start_datetime=start_utc,
        end_datetime=end_utc,
        timezone=timezone,
        tenant_start_date=tenant_start_date,
    )


async def get_analytics_date_range(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> AnalyticsDateRange:
    """FastAPI dependency for analytics date range resolution.

    Combines tenant lookup, timezone resolution, and date range computation
    into a single reusable dependency.

    Args:
        db: Database session
        tenant_id: Current tenant ID
        start_date: Optional start date query param
        end_date: Optional end date query param
        timezone: Optional timezone override
        days: Default number of days for range (default 30)

    Returns:
        Fully resolved AnalyticsDateRange

    Raises:
        HTTPException: If tenant not found
    """
    from fastapi import HTTPException, status

    # Get tenant creation date
    tenant_created_at = await get_tenant_created_at(db, tenant_id)
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Resolve timezone (prefer query param, fall back to tenant config)
    tenant_tz = await get_tenant_timezone(db, tenant_id)
    requested_tz = resolve_timezone(timezone)
    effective_tz = resolve_timezone(tenant_tz) if tenant_tz else requested_tz

    # Compute date range
    return compute_date_range(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        tenant_created_at=tenant_created_at,
        timezone=effective_tz,
        default_days=days,
    )


# Convenience type alias for use in route signatures (30-day default)
AnalyticsContext = Annotated[AnalyticsDateRange, Depends(get_analytics_date_range)]


def analytics_date_range_dependency(default_days: int = 30):
    """Factory for analytics date range dependencies with custom default days.

    Usage:
        @router.get("/usage")
        async def get_usage(
            ctx: Annotated[AnalyticsDateRange, Depends(analytics_date_range_dependency(7))],
        ):
            ...

    Args:
        default_days: Default number of days for the date range

    Returns:
        FastAPI dependency function
    """
    async def dependency(
        db: Annotated[AsyncSession, Depends(get_db)],
        tenant_id: Annotated[int, Depends(require_tenant_context)],
        start_date: Annotated[str | None, Query()] = None,
        end_date: Annotated[str | None, Query()] = None,
        timezone: Annotated[str | None, Query()] = None,
    ) -> AnalyticsDateRange:
        return await get_analytics_date_range(
            db, tenant_id, start_date, end_date, timezone, default_days
        )
    return dependency


# Pre-configured dependencies for common use cases
AnalyticsContext7d = Annotated[AnalyticsDateRange, Depends(analytics_date_range_dependency(7))]
AnalyticsContext30d = Annotated[AnalyticsDateRange, Depends(analytics_date_range_dependency(30))]
AnalyticsContext90d = Annotated[AnalyticsDateRange, Depends(analytics_date_range_dependency(90))]
