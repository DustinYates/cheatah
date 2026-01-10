"""Analytics API endpoints."""

from datetime import date, datetime, time, timedelta
from typing import Annotated

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_sms_config import TenantSmsConfig

router = APIRouter()


class UsageDay(BaseModel):
    """Usage metrics for a single day."""

    date: str
    sms_in: int
    sms_out: int
    chatbot_interactions: int
    call_count: int
    call_minutes: float


class UsageResponse(BaseModel):
    """Usage metrics response."""

    onboarded_date: str
    start_date: str
    end_date: str
    timezone: str
    series: list[UsageDay]


def _normalize_date(value: date | datetime | str | None) -> date | None:
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


def _resolve_timezone(value: str | None) -> str:
    if not value:
        return "UTC"
    try:
        pytz.timezone(value)
        return value
    except pytz.UnknownTimeZoneError:
        return "UTC"


def _supports_timezone(db: AsyncSession) -> bool:
    try:
        return db.bind and db.bind.dialect.name == "postgresql"
    except AttributeError:
        return False


def _day_bucket(column, timezone_name: str, use_timezone: bool):
    if use_timezone and timezone_name != "UTC":
        return cast(func.timezone(timezone_name, column), Date).label("day")
    return cast(column, Date).label("day")


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
) -> UsageResponse:
    """Get daily usage metrics for SMS, chatbot, and calls."""
    tenant_result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    tenant_created_at = tenant_result.scalar_one_or_none()
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    sms_config_result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    tenant_timezone = sms_config_result.scalar_one_or_none()
    requested_timezone = _resolve_timezone(timezone)
    effective_timezone = _resolve_timezone(tenant_timezone) if tenant_timezone else requested_timezone
    use_timezone = _supports_timezone(db)

    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()
    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=6)
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=6)
    elif parsed_end is None and parsed_start is not None:
        parsed_end = today

    range_start = parsed_start or tenant_start_date
    range_end = parsed_end or today

    if range_start < tenant_start_date:
        range_start = tenant_start_date
    if range_end > today:
        range_end = today
    if range_start > range_end:
        range_start = range_end

    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_datetime = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_datetime = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    sms_day = _day_bucket(Message.created_at, effective_timezone, use_timezone)
    sms_stmt = (
        select(
            sms_day,
            Message.role.label("role"),
            func.count(Message.id).label("count"),
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.role.in_(["user", "assistant"]),
            Message.created_at >= start_datetime,
            Message.created_at <= end_datetime,
        )
        .group_by(sms_day, Message.role)
    )
    sms_result = await db.execute(sms_stmt)

    sms_in = {}
    sms_out = {}
    for row in sms_result:
        day = _normalize_date(row.day)
        if not day:
            continue
        if row.role == "user":
            sms_in[day] = int(row.count or 0)
        elif row.role == "assistant":
            sms_out[day] = int(row.count or 0)

    chat_day = _day_bucket(Message.created_at, effective_timezone, use_timezone)
    chat_stmt = (
        select(
            chat_day,
            func.count(Message.id).label("count"),
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "web",
            Message.role == "user",
            Message.created_at >= start_datetime,
            Message.created_at <= end_datetime,
        )
        .group_by(chat_day)
    )
    chat_result = await db.execute(chat_stmt)

    chat_interactions = {}
    for row in chat_result:
        day = _normalize_date(row.day)
        if not day:
            continue
        chat_interactions[day] = int(row.count or 0)

    call_timestamp = func.coalesce(Call.started_at, Call.created_at)
    calls_day = _day_bucket(call_timestamp, effective_timezone, use_timezone)
    duration_seconds = func.coalesce(
        func.nullif(Call.duration, 0),
        func.extract("epoch", Call.ended_at - Call.started_at),
        0,
    )
    calls_stmt = (
        select(
            calls_day,
            func.sum(duration_seconds).label("duration_seconds"),
            func.count(Call.id).label("call_count"),
        )
        .where(
            Call.tenant_id == tenant_id,
            call_timestamp >= start_datetime,
            call_timestamp <= end_datetime,
        )
        .group_by(calls_day)
    )
    calls_result = await db.execute(calls_stmt)

    call_minutes = {}
    call_counts = {}
    for row in calls_result:
        day = _normalize_date(row.day)
        if not day:
            continue
        seconds = float(row.duration_seconds or 0)
        call_minutes[day] = round(seconds / 60, 2)
        call_counts[day] = int(row.call_count or 0)

    series = []
    current = range_start
    while current <= range_end:
        series.append(
            UsageDay(
                date=current.isoformat(),
                sms_in=sms_in.get(current, 0),
                sms_out=sms_out.get(current, 0),
                chatbot_interactions=chat_interactions.get(current, 0),
                call_count=call_counts.get(current, 0),
                call_minutes=call_minutes.get(current, 0.0),
            )
        )
        current += timedelta(days=1)

    return UsageResponse(
        onboarded_date=tenant_start_date.isoformat(),
        start_date=range_start.isoformat(),
        end_date=range_end.isoformat(),
        timezone=effective_timezone,
        series=series,
    )
