"""Analytics API endpoints."""

from datetime import date, datetime, time, timedelta
from typing import Annotated

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Date, String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import require_tenant_context
from app.persistence.database import get_db
from app.domain.services.pushback_detector import PushbackDetector
from app.domain.services.repetition_detector import RepetitionDetector
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.escalation import Escalation
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import Tenant
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.sent_asset import SentAsset
from app.persistence.models.widget_event import WidgetEvent

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


# Conversation Analytics Models


class ChannelMetrics(BaseModel):
    """Metrics for a single channel."""

    avg_messages: float
    avg_duration_minutes: float


class ConversationLengthMetrics(BaseModel):
    """Metrics for conversation length."""

    avg_message_count: float
    avg_duration_minutes: float
    by_channel: dict[str, ChannelMetrics]


class EscalationMetrics(BaseModel):
    """Escalation rate metrics."""

    total_conversations: int
    total_escalations: int
    escalation_rate: float


class IntentDistribution(BaseModel):
    """Intent distribution from call summaries."""

    intent: str
    count: int
    percentage: float


class ResponseTimeMetrics(BaseModel):
    """Response time metrics."""

    avg_response_time_seconds: float
    by_channel: dict[str, float]


class ResponseTimeDistribution(BaseModel):
    """Response time metrics with percentiles."""

    avg_response_time_seconds: float
    p50_seconds: float
    p90_seconds: float
    p99_seconds: float
    first_response_avg_seconds: float
    by_channel: dict[str, dict]  # {channel: {avg, p50, p90, p99, first_response}}


class EscalationChannelDetail(BaseModel):
    """Escalation metrics for a single channel."""

    count: int
    rate: float
    conversations: int


class EscalationByChannelMetrics(BaseModel):
    """Escalation metrics broken down by channel and reason."""

    total_conversations: int
    total_escalations: int
    escalation_rate: float
    by_channel: dict[str, EscalationChannelDetail]  # {channel: {count, rate, conversations}}
    by_reason: dict[str, int]  # {reason: count}
    avg_messages_before_escalation: float
    escalation_timing: dict[str, float]  # {early: %, mid: %, late: %}


class RegistrationLinksMetrics(BaseModel):
    """Registration link send metrics."""

    total_sent: int
    unique_leads_sent: int
    by_asset_type: dict[str, int]  # {registration_link: X, pricing: Y}


class ChannelEffectiveness(BaseModel):
    """Effectiveness metrics for a single channel."""

    total_conversations: int
    leads_captured: int
    conversion_rate: float
    escalation_rate: float
    avg_messages: float
    avg_duration_minutes: float


class ChannelEffectivenessMatrix(BaseModel):
    """Channel effectiveness comparison matrix."""

    channels: dict[str, ChannelEffectiveness]


class AIValueMetrics(BaseModel):
    """Metrics showing AI value/impact."""

    conversations_resolved_without_human: int
    resolution_rate: float  # % resolved without escalation
    estimated_staff_minutes_saved: float
    leads_captured_automatically: int


# Phase 2 Models


class DropOffMetrics(BaseModel):
    """Drop-off analytics metrics."""

    total_conversations: int
    completed_conversations: int  # With lead or link sent
    dropped_conversations: int
    drop_off_rate: float
    by_exit_topic: dict[str, int]  # {pricing: X, location: Y, contact: Z}
    avg_messages_before_dropoff: float
    avg_time_to_dropoff_minutes: float


class PushbackMetrics(BaseModel):
    """User pushback/frustration metrics."""

    total_pushback_signals: int
    conversations_with_pushback: int
    pushback_rate: float  # % of conversations with pushback
    by_type: dict[str, int]  # {impatience: X, frustration: Y, ...}
    common_triggers: list[str]  # Most common trigger phrases


class RepetitionMetrics(BaseModel):
    """Repetition and confusion signal metrics."""

    conversations_with_repetition: int
    repetition_rate: float
    total_repeated_questions: int
    total_user_clarifications: int
    total_bot_clarifications: int
    avg_repetition_score: float  # 0-1 friction score


class DemandMetrics(BaseModel):
    """Location and class demand intelligence (BSS-specific)."""

    requests_by_location: dict[str, int]
    location_mention_rate: float
    requests_by_class_level: dict[str, int]
    adult_vs_child: dict[str, int]  # {adult: X, child: Y}
    by_hour_of_day: dict[int, int]  # {hour: count}


class PhoneCallLanguageStats(BaseModel):
    """Phone call statistics for a specific language."""

    call_count: int
    total_minutes: float
    avg_duration_minutes: float
    leads_generated: int


class PhoneCallStatistics(BaseModel):
    """Phone call statistics broken down by language (Spanish vs English)."""

    total_calls: int
    total_minutes: float
    by_language: dict[str, PhoneCallLanguageStats]  # {english: {...}, spanish: {...}, unknown: {...}}
    language_distribution: dict[str, float]  # {english: 65.5, spanish: 34.5, unknown: 0}


class ConversationAnalyticsResponse(BaseModel):
    """Response model for conversation analytics."""

    start_date: str
    end_date: str
    timezone: str
    conversation_length: ConversationLengthMetrics
    escalation_metrics: EscalationMetrics
    intent_distribution: list[IntentDistribution]
    response_times: ResponseTimeMetrics
    # Phase 1 metrics
    escalation_by_channel: EscalationByChannelMetrics | None = None
    response_time_distribution: ResponseTimeDistribution | None = None
    registration_links: RegistrationLinksMetrics | None = None
    channel_effectiveness: ChannelEffectivenessMatrix | None = None
    ai_value: AIValueMetrics | None = None
    # Phase 2 metrics
    drop_off: DropOffMetrics | None = None
    pushback: PushbackMetrics | None = None
    repetition: RepetitionMetrics | None = None
    demand: DemandMetrics | None = None
    # Phone call statistics by language
    phone_call_statistics: PhoneCallStatistics | None = None


@router.get("/conversations", response_model=ConversationAnalyticsResponse)
async def get_conversation_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
) -> ConversationAnalyticsResponse:
    """Get conversation analytics including length, escalation rate, intents, and response times."""
    # Get tenant info
    tenant_result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    tenant_created_at = tenant_result.scalar_one_or_none()
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Resolve timezone
    sms_config_result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    tenant_timezone = sms_config_result.scalar_one_or_none()
    requested_timezone = _resolve_timezone(timezone)
    effective_timezone = (
        _resolve_timezone(tenant_timezone) if tenant_timezone else requested_timezone
    )

    # Parse date range
    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()
    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=29)  # Default to 30 days
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=29)
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

    # Convert to UTC datetime range
    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_datetime = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_datetime = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Query 1: Conversation length metrics
    conv_metrics_stmt = (
        select(
            Conversation.channel,
            func.count(Message.id).label("msg_count"),
            func.extract(
                "epoch",
                func.max(Message.created_at) - func.min(Message.created_at),
            ).label("duration_seconds"),
        )
        .select_from(Conversation)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
        )
        .group_by(Conversation.id, Conversation.channel)
    )
    conv_metrics_result = await db.execute(conv_metrics_stmt)

    channel_totals: dict[str, dict] = {}
    total_msg_count = 0
    total_duration = 0.0
    total_conversations = 0

    for row in conv_metrics_result:
        channel = row.channel or "unknown"
        msg_count = int(row.msg_count or 0)
        duration_seconds = float(row.duration_seconds or 0)

        if channel not in channel_totals:
            channel_totals[channel] = {
                "msg_sum": 0,
                "duration_sum": 0.0,
                "count": 0,
            }

        channel_totals[channel]["msg_sum"] += msg_count
        channel_totals[channel]["duration_sum"] += duration_seconds
        channel_totals[channel]["count"] += 1

        total_msg_count += msg_count
        total_duration += duration_seconds
        total_conversations += 1

    by_channel = {}
    for channel, totals in channel_totals.items():
        count = totals["count"]
        by_channel[channel] = ChannelMetrics(
            avg_messages=round(totals["msg_sum"] / count, 1) if count > 0 else 0,
            avg_duration_minutes=round(totals["duration_sum"] / count / 60, 1)
            if count > 0
            else 0,
        )

    avg_msg = round(total_msg_count / total_conversations, 1) if total_conversations > 0 else 0
    avg_duration = (
        round(total_duration / total_conversations / 60, 1) if total_conversations > 0 else 0
    )

    conversation_length = ConversationLengthMetrics(
        avg_message_count=avg_msg,
        avg_duration_minutes=avg_duration,
        by_channel=by_channel,
    )

    # Query 2: Escalation metrics
    escalation_count_stmt = (
        select(func.count(Escalation.id))
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= start_datetime,
            Escalation.created_at <= end_datetime,
        )
    )
    escalation_result = await db.execute(escalation_count_stmt)
    total_escalations = escalation_result.scalar() or 0

    escalation_rate = (
        round(total_escalations / total_conversations, 3)
        if total_conversations > 0
        else 0
    )

    escalation_metrics = EscalationMetrics(
        total_conversations=total_conversations,
        total_escalations=total_escalations,
        escalation_rate=escalation_rate,
    )

    # Query 3: Intent distribution from call summaries
    call_timestamp = func.coalesce(Call.started_at, Call.created_at)
    intent_stmt = (
        select(
            CallSummary.intent,
            func.count(CallSummary.id).label("count"),
        )
        .select_from(CallSummary)
        .join(Call, Call.id == CallSummary.call_id)
        .where(
            Call.tenant_id == tenant_id,
            call_timestamp >= start_datetime,
            call_timestamp <= end_datetime,
            CallSummary.intent.isnot(None),
        )
        .group_by(CallSummary.intent)
        .order_by(func.count(CallSummary.id).desc())
    )
    intent_result = await db.execute(intent_stmt)

    intent_rows = list(intent_result)
    total_intents = sum(row.count for row in intent_rows)
    intent_distribution = [
        IntentDistribution(
            intent=row.intent,
            count=row.count,
            percentage=round(row.count / total_intents * 100, 1) if total_intents > 0 else 0,
        )
        for row in intent_rows
    ]

    # Query 4: Response time metrics
    # Get pairs of consecutive user->assistant messages and calculate time diff
    UserMessage = aliased(Message)
    AssistantMessage = aliased(Message)

    response_time_stmt = (
        select(
            Conversation.channel,
            func.avg(
                func.extract(
                    "epoch",
                    AssistantMessage.created_at - UserMessage.created_at,
                )
            ).label("avg_response_seconds"),
        )
        .select_from(UserMessage)
        .join(Conversation, Conversation.id == UserMessage.conversation_id)
        .join(
            AssistantMessage,
            and_(
                AssistantMessage.conversation_id == UserMessage.conversation_id,
                AssistantMessage.sequence_number == UserMessage.sequence_number + 1,
                AssistantMessage.role == "assistant",
            ),
        )
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            UserMessage.role == "user",
        )
        .group_by(Conversation.channel)
    )
    response_time_result = await db.execute(response_time_stmt)

    response_by_channel: dict[str, float] = {}
    total_response_time = 0.0
    channel_count = 0

    for row in response_time_result:
        channel = row.channel or "unknown"
        avg_seconds = float(row.avg_response_seconds or 0)
        response_by_channel[channel] = round(avg_seconds, 1)
        total_response_time += avg_seconds
        channel_count += 1

    avg_response = (
        round(total_response_time / channel_count, 1) if channel_count > 0 else 0
    )

    response_times = ResponseTimeMetrics(
        avg_response_time_seconds=avg_response,
        by_channel=response_by_channel,
    )

    # Query 5: Escalation by channel and reason
    # Get conversations per channel for rate calculation
    conv_per_channel_stmt = (
        select(
            Conversation.channel,
            func.count(Conversation.id).label("count"),
        )
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
        )
        .group_by(Conversation.channel)
    )
    conv_per_channel_result = await db.execute(conv_per_channel_stmt)
    conv_per_channel = {row.channel: row.count for row in conv_per_channel_result}

    # Get escalations by channel (from metadata) and reason
    # Define cast expression once to avoid PostgreSQL GROUP BY parameter mismatch
    channel_cast_expr = cast(Escalation.escalation_metadata["channel"], String)
    escalation_detail_stmt = (
        select(
            channel_cast_expr.label("channel"),
            Escalation.reason,
            func.count(Escalation.id).label("count"),
        )
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= start_datetime,
            Escalation.created_at <= end_datetime,
        )
        .group_by(
            channel_cast_expr,
            Escalation.reason,
        )
    )
    escalation_detail_result = await db.execute(escalation_detail_stmt)

    escalation_by_channel: dict[str, dict] = {}
    escalation_by_reason: dict[str, int] = {}

    for row in escalation_detail_result:
        channel = row.channel or "unknown"
        reason = row.reason or "unknown"
        count = int(row.count or 0)

        # Aggregate by channel
        if channel not in escalation_by_channel:
            escalation_by_channel[channel] = {"count": 0}
        escalation_by_channel[channel]["count"] += count

        # Aggregate by reason
        escalation_by_reason[reason] = escalation_by_reason.get(reason, 0) + count

    # Calculate rates per channel
    for channel, data in escalation_by_channel.items():
        channel_convs = conv_per_channel.get(channel, 0)
        data["conversations"] = channel_convs
        data["rate"] = round(data["count"] / channel_convs, 3) if channel_convs > 0 else 0

    # Query 6: Messages before escalation and timing distribution
    escalation_timing_stmt = (
        select(
            Escalation.id,
            func.count(Message.id).label("messages_before"),
        )
        .select_from(Escalation)
        .outerjoin(Conversation, Conversation.id == Escalation.conversation_id)
        .outerjoin(
            Message,
            and_(
                Message.conversation_id == Conversation.id,
                Message.created_at < Escalation.created_at,
            ),
        )
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= start_datetime,
            Escalation.created_at <= end_datetime,
        )
        .group_by(Escalation.id)
    )
    escalation_timing_result = await db.execute(escalation_timing_stmt)

    timing_data = list(escalation_timing_result)
    total_msgs_before = sum(row.messages_before or 0 for row in timing_data)
    escalation_count_for_timing = len(timing_data)
    avg_messages_before = (
        round(total_msgs_before / escalation_count_for_timing, 1)
        if escalation_count_for_timing > 0
        else 0
    )

    # Calculate timing distribution (early: 0-3 msgs, mid: 4-7 msgs, late: 8+ msgs)
    early_count = sum(1 for row in timing_data if (row.messages_before or 0) <= 3)
    mid_count = sum(1 for row in timing_data if 4 <= (row.messages_before or 0) <= 7)
    late_count = sum(1 for row in timing_data if (row.messages_before or 0) >= 8)

    timing_total = early_count + mid_count + late_count
    escalation_timing = {
        "early": round(early_count / timing_total * 100, 1) if timing_total > 0 else 0,
        "mid": round(mid_count / timing_total * 100, 1) if timing_total > 0 else 0,
        "late": round(late_count / timing_total * 100, 1) if timing_total > 0 else 0,
    }

    escalation_by_channel_metrics = EscalationByChannelMetrics(
        total_conversations=total_conversations,
        total_escalations=total_escalations,
        escalation_rate=escalation_rate,
        by_channel={
            ch: EscalationChannelDetail(
                count=data["count"],
                rate=data["rate"],
                conversations=data["conversations"],
            )
            for ch, data in escalation_by_channel.items()
        },
        by_reason=escalation_by_reason,
        avg_messages_before_escalation=avg_messages_before,
        escalation_timing=escalation_timing,
    )

    # Query 7: Registration links sent
    # Count leads with sms_sent_for_assets in extra_data
    links_sent_stmt = (
        select(
            Lead.id,
            Lead.extra_data,
        )
        .where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= start_datetime,
            Lead.created_at <= end_datetime,
            Lead.extra_data.isnot(None),
        )
    )
    links_sent_result = await db.execute(links_sent_stmt)

    total_links_sent = 0
    unique_leads_with_links = 0
    links_by_asset_type: dict[str, int] = {}

    for row in links_sent_result:
        extra_data = row.extra_data or {}
        sent_assets = extra_data.get("sms_sent_for_assets", [])
        if sent_assets:
            unique_leads_with_links += 1
            for asset in sent_assets:
                total_links_sent += 1
                asset_type = asset if isinstance(asset, str) else str(asset)
                links_by_asset_type[asset_type] = links_by_asset_type.get(asset_type, 0) + 1

    registration_links_metrics = RegistrationLinksMetrics(
        total_sent=total_links_sent,
        unique_leads_sent=unique_leads_with_links,
        by_asset_type=links_by_asset_type,
    )

    # Query 8: Channel effectiveness matrix
    # Join conversations with leads to get conversion rates
    channel_effectiveness_stmt = (
        select(
            Conversation.channel,
            func.count(func.distinct(Conversation.id)).label("total_conversations"),
            func.count(func.distinct(Lead.id)).label("leads_captured"),
        )
        .select_from(Conversation)
        .outerjoin(Lead, Lead.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
        )
        .group_by(Conversation.channel)
    )
    channel_eff_result = await db.execute(channel_effectiveness_stmt)

    channel_effectiveness_data: dict[str, ChannelEffectiveness] = {}

    for row in channel_eff_result:
        channel = row.channel or "unknown"
        total_convs = int(row.total_conversations or 0)
        leads = int(row.leads_captured or 0)
        conversion_rate = round(leads / total_convs, 3) if total_convs > 0 else 0

        # Get escalation rate for this channel
        channel_esc_data = escalation_by_channel.get(channel, {"count": 0, "conversations": 0})
        channel_esc_rate = channel_esc_data.get("rate", 0)

        # Get avg messages and duration for this channel from earlier calculation
        channel_metrics = by_channel.get(channel)
        avg_msgs = channel_metrics.avg_messages if channel_metrics else 0
        avg_dur = channel_metrics.avg_duration_minutes if channel_metrics else 0

        channel_effectiveness_data[channel] = ChannelEffectiveness(
            total_conversations=total_convs,
            leads_captured=leads,
            conversion_rate=conversion_rate,
            escalation_rate=channel_esc_rate,
            avg_messages=avg_msgs,
            avg_duration_minutes=avg_dur,
        )

    channel_effectiveness_matrix = ChannelEffectivenessMatrix(
        channels=channel_effectiveness_data,
    )

    # Query 9: AI Value metrics
    # Count conversations without escalations
    resolved_without_human_stmt = (
        select(func.count(func.distinct(Conversation.id)))
        .select_from(Conversation)
        .outerjoin(Escalation, Escalation.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            Escalation.id.is_(None),
        )
    )
    resolved_result = await db.execute(resolved_without_human_stmt)
    resolved_without_human = resolved_result.scalar() or 0

    resolution_rate = (
        round(resolved_without_human / total_conversations, 3)
        if total_conversations > 0
        else 0
    )

    # Estimate staff minutes saved (avg_duration * resolved_count)
    # Using avg_duration calculated earlier (in minutes)
    estimated_minutes_saved = round(avg_duration * resolved_without_human, 1)

    # Count leads captured without escalation
    leads_auto_stmt = (
        select(func.count(func.distinct(Lead.id)))
        .select_from(Lead)
        .join(Conversation, Conversation.id == Lead.conversation_id)
        .outerjoin(Escalation, Escalation.conversation_id == Conversation.id)
        .where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= start_datetime,
            Lead.created_at <= end_datetime,
            Escalation.id.is_(None),
        )
    )
    leads_auto_result = await db.execute(leads_auto_stmt)
    leads_captured_auto = leads_auto_result.scalar() or 0

    ai_value_metrics = AIValueMetrics(
        conversations_resolved_without_human=resolved_without_human,
        resolution_rate=resolution_rate,
        estimated_staff_minutes_saved=estimated_minutes_saved,
        leads_captured_automatically=leads_captured_auto,
    )

    # Query 10: Response time distribution with percentiles
    # Note: percentile_cont requires PostgreSQL - we'll compute it in Python for compatibility
    all_response_times_stmt = (
        select(
            Conversation.channel,
            func.extract(
                "epoch",
                AssistantMessage.created_at - UserMessage.created_at,
            ).label("response_seconds"),
            UserMessage.sequence_number.label("seq_num"),
        )
        .select_from(UserMessage)
        .join(Conversation, Conversation.id == UserMessage.conversation_id)
        .join(
            AssistantMessage,
            and_(
                AssistantMessage.conversation_id == UserMessage.conversation_id,
                AssistantMessage.sequence_number == UserMessage.sequence_number + 1,
                AssistantMessage.role == "assistant",
            ),
        )
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            UserMessage.role == "user",
        )
    )
    all_rt_result = await db.execute(all_response_times_stmt)

    rt_by_channel: dict[str, list[float]] = {}
    first_response_by_channel: dict[str, list[float]] = {}

    for row in all_rt_result:
        channel = row.channel or "unknown"
        rt = float(row.response_seconds or 0)
        seq_num = int(row.seq_num or 0)

        if channel not in rt_by_channel:
            rt_by_channel[channel] = []
            first_response_by_channel[channel] = []

        rt_by_channel[channel].append(rt)

        # First response is sequence_number == 0 (first user message)
        if seq_num == 0:
            first_response_by_channel[channel].append(rt)

    def calc_percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * pct)
        idx = min(idx, len(sorted_vals) - 1)
        return round(sorted_vals[idx], 1)

    all_rts = [rt for rts in rt_by_channel.values() for rt in rts]
    all_first_rts = [rt for rts in first_response_by_channel.values() for rt in rts]

    rt_distribution_by_channel: dict[str, dict] = {}
    for channel, rts in rt_by_channel.items():
        first_rts = first_response_by_channel.get(channel, [])
        rt_distribution_by_channel[channel] = {
            "avg": round(sum(rts) / len(rts), 1) if rts else 0,
            "p50": calc_percentile(rts, 0.5),
            "p90": calc_percentile(rts, 0.9),
            "p99": calc_percentile(rts, 0.99),
            "first_response": round(sum(first_rts) / len(first_rts), 1) if first_rts else 0,
        }

    response_time_distribution = ResponseTimeDistribution(
        avg_response_time_seconds=round(sum(all_rts) / len(all_rts), 1) if all_rts else 0,
        p50_seconds=calc_percentile(all_rts, 0.5),
        p90_seconds=calc_percentile(all_rts, 0.9),
        p99_seconds=calc_percentile(all_rts, 0.99),
        first_response_avg_seconds=round(sum(all_first_rts) / len(all_first_rts), 1) if all_first_rts else 0,
        by_channel=rt_distribution_by_channel,
    )

    # ============================================================
    # Phase 2 Analytics
    # ============================================================

    # Query 11: Drop-off analytics
    # A conversation is "completed" if it has a lead or registration link sent
    # A conversation is "dropped" if it has neither and no recent activity

    # Get conversations with their outcomes
    conv_outcome_stmt = (
        select(
            Conversation.id,
            Conversation.created_at,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
            func.min(Message.created_at).label("first_message_at"),
        )
        .select_from(Conversation)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
        )
        .group_by(Conversation.id)
    )
    conv_outcome_result = await db.execute(conv_outcome_stmt)
    conv_outcomes = list(conv_outcome_result)

    # Get conversation IDs with leads
    conv_with_leads_stmt = (
        select(func.distinct(Lead.conversation_id))
        .where(
            Lead.tenant_id == tenant_id,
            Lead.conversation_id.isnot(None),
            Lead.created_at >= start_datetime,
            Lead.created_at <= end_datetime,
        )
    )
    conv_with_leads_result = await db.execute(conv_with_leads_stmt)
    conv_ids_with_leads = {row[0] for row in conv_with_leads_result}

    # Get conversation IDs with registration links sent
    conv_with_links_stmt = (
        select(func.distinct(Lead.conversation_id))
        .where(
            Lead.tenant_id == tenant_id,
            Lead.conversation_id.isnot(None),
            Lead.extra_data.isnot(None),
            Lead.created_at >= start_datetime,
            Lead.created_at <= end_datetime,
        )
    )
    conv_with_links_result = await db.execute(conv_with_links_stmt)
    conv_ids_with_links = {row[0] for row in conv_with_links_result if row[0]}

    # Get conversation IDs with escalations
    conv_with_esc_stmt = (
        select(func.distinct(Escalation.conversation_id))
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.conversation_id.isnot(None),
            Escalation.created_at >= start_datetime,
            Escalation.created_at <= end_datetime,
        )
    )
    conv_with_esc_result = await db.execute(conv_with_esc_stmt)
    conv_ids_with_esc = {row[0] for row in conv_with_esc_result if row[0]}

    completed_conv_ids = conv_ids_with_leads | conv_ids_with_links | conv_ids_with_esc
    completed_count = len(completed_conv_ids)
    dropped_count = 0
    drop_off_messages = []
    drop_off_durations = []

    for row in conv_outcomes:
        if row.id not in completed_conv_ids and row.message_count and row.message_count > 0:
            dropped_count += 1
            drop_off_messages.append(row.message_count)
            if row.last_message_at and row.first_message_at:
                duration_seconds = (row.last_message_at - row.first_message_at).total_seconds()
                drop_off_durations.append(duration_seconds / 60)  # Convert to minutes

    drop_off_rate = round(dropped_count / total_conversations, 3) if total_conversations > 0 else 0
    avg_msgs_before_dropoff = round(sum(drop_off_messages) / len(drop_off_messages), 1) if drop_off_messages else 0
    avg_time_to_dropoff = round(sum(drop_off_durations) / len(drop_off_durations), 1) if drop_off_durations else 0

    drop_off_metrics = DropOffMetrics(
        total_conversations=total_conversations,
        completed_conversations=completed_count,
        dropped_conversations=dropped_count,
        drop_off_rate=drop_off_rate,
        by_exit_topic={},  # Would require message content analysis - simplified for now
        avg_messages_before_dropoff=avg_msgs_before_dropoff,
        avg_time_to_dropoff_minutes=avg_time_to_dropoff,
    )

    # Query 12: Pushback detection
    # Fetch user messages and analyze for pushback signals
    pushback_detector = PushbackDetector()

    user_messages_stmt = (
        select(
            Message.conversation_id,
            Message.content,
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            Message.role == "user",
            Message.content.isnot(None),
        )
    )
    user_messages_result = await db.execute(user_messages_stmt)

    pushback_by_type: dict[str, int] = {}
    pushback_triggers: list[str] = []
    conversations_with_pushback: set[int] = set()
    total_pushback_signals = 0

    for row in user_messages_result:
        signal = pushback_detector.detect(row.content)
        if signal:
            total_pushback_signals += 1
            conversations_with_pushback.add(row.conversation_id)
            pushback_by_type[signal.pushback_type] = pushback_by_type.get(signal.pushback_type, 0) + 1
            if signal.trigger_phrase not in pushback_triggers:
                pushback_triggers.append(signal.trigger_phrase)

    pushback_rate = round(len(conversations_with_pushback) / total_conversations, 3) if total_conversations > 0 else 0

    # Limit to top 10 common triggers
    common_triggers = pushback_triggers[:10]

    pushback_metrics = PushbackMetrics(
        total_pushback_signals=total_pushback_signals,
        conversations_with_pushback=len(conversations_with_pushback),
        pushback_rate=pushback_rate,
        by_type=pushback_by_type,
        common_triggers=common_triggers,
    )

    # Query 13: Repetition signals
    # Group messages by conversation for analysis
    repetition_detector = RepetitionDetector()

    conv_messages_stmt = (
        select(
            Message.conversation_id,
            Message.role,
            Message.content,
            Message.sequence_number,
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            Message.content.isnot(None),
        )
        .order_by(Message.conversation_id, Message.sequence_number)
    )
    conv_messages_result = await db.execute(conv_messages_stmt)

    # Group messages by conversation
    messages_by_conv: dict[int, list[dict]] = {}
    for row in conv_messages_result:
        if row.conversation_id not in messages_by_conv:
            messages_by_conv[row.conversation_id] = []
        messages_by_conv[row.conversation_id].append({
            "role": row.role,
            "content": row.content,
        })

    conversations_with_repetition = 0
    total_repeated_questions = 0
    total_user_clarifications = 0
    total_bot_clarifications = 0
    repetition_scores = []

    for conv_id, messages in messages_by_conv.items():
        analysis = repetition_detector.analyze_conversation(messages)
        if analysis.has_repetitions:
            conversations_with_repetition += 1
        total_repeated_questions += analysis.repeated_question_count
        total_user_clarifications += analysis.clarification_count
        total_bot_clarifications += analysis.bot_clarification_count
        repetition_scores.append(repetition_detector.get_repetition_score(analysis))

    repetition_rate = round(conversations_with_repetition / total_conversations, 3) if total_conversations > 0 else 0
    avg_repetition_score = round(sum(repetition_scores) / len(repetition_scores), 3) if repetition_scores else 0

    repetition_metrics = RepetitionMetrics(
        conversations_with_repetition=conversations_with_repetition,
        repetition_rate=repetition_rate,
        total_repeated_questions=total_repeated_questions,
        total_user_clarifications=total_user_clarifications,
        total_bot_clarifications=total_bot_clarifications,
        avg_repetition_score=avg_repetition_score,
    )

    # Query 14: Demand intelligence (BSS-specific)
    # Extract location and class mentions from call summaries and messages

    # Location patterns for BSS
    location_patterns = {
        "LAFCypress": r"(?:la\s*f\s*)?cypress|lafcypress",
        "LALANG": r"la\s*lang|langley|lalang",
        "24Spring": r"24\s*spring|spring\s*24|24spring",
    }

    # Class level patterns
    class_patterns = {
        "Little Snappers": r"little\s*snapper|snapper",
        "Turtle": r"turtle\s*\d*|turtle\s*level",
        "Level 1": r"level\s*1|lvl\s*1",
        "Level 2": r"level\s*2|lvl\s*2",
        "Level 3": r"level\s*3|lvl\s*3",
        "Adult": r"adult\s*(?:class|level|swim)?|grown\s*up",
    }

    import re

    requests_by_location: dict[str, int] = {}
    requests_by_class: dict[str, int] = {}
    adult_vs_child = {"adult": 0, "child": 0}
    by_hour: dict[int, int] = {}

    # Analyze call summaries for demand data
    call_demand_stmt = (
        select(
            CallSummary.extracted_fields,
            Call.started_at,
        )
        .select_from(CallSummary)
        .join(Call, Call.id == CallSummary.call_id)
        .where(
            Call.tenant_id == tenant_id,
            func.coalesce(Call.started_at, Call.created_at) >= start_datetime,
            func.coalesce(Call.started_at, Call.created_at) <= end_datetime,
        )
    )
    call_demand_result = await db.execute(call_demand_stmt)

    location_mentions = 0

    for row in call_demand_result:
        # Track time of day (convert UTC to tenant timezone)
        if row.started_at:
            utc_dt = pytz.UTC.localize(row.started_at)
            local_dt = utc_dt.astimezone(tz)
            hour = local_dt.hour
            by_hour[hour] = by_hour.get(hour, 0) + 1

        # Check extracted fields for location/class mentions
        extracted = row.extracted_fields or {}
        reason = str(extracted.get("reason", "")).lower()

        # Check for location mentions
        for loc_name, pattern in location_patterns.items():
            if re.search(pattern, reason, re.IGNORECASE):
                requests_by_location[loc_name] = requests_by_location.get(loc_name, 0) + 1
                location_mentions += 1

        # Check for class mentions
        for class_name, pattern in class_patterns.items():
            if re.search(pattern, reason, re.IGNORECASE):
                requests_by_class[class_name] = requests_by_class.get(class_name, 0) + 1
                if "adult" in class_name.lower():
                    adult_vs_child["adult"] += 1
                else:
                    adult_vs_child["child"] += 1

    # Also analyze SMS/chat message content for demand signals
    demand_messages_stmt = (
        select(
            Message.content,
            Message.created_at,
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start_datetime,
            Conversation.created_at <= end_datetime,
            Message.role == "user",
            Message.content.isnot(None),
        )
    )
    demand_messages_result = await db.execute(demand_messages_stmt)

    for row in demand_messages_result:
        content = row.content.lower() if row.content else ""

        # Track time of day (convert UTC to tenant timezone)
        if row.created_at:
            utc_dt = pytz.UTC.localize(row.created_at)
            local_dt = utc_dt.astimezone(tz)
            hour = local_dt.hour
            by_hour[hour] = by_hour.get(hour, 0) + 1

        # Check for location mentions
        for loc_name, pattern in location_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                requests_by_location[loc_name] = requests_by_location.get(loc_name, 0) + 1
                location_mentions += 1

        # Check for class mentions
        for class_name, pattern in class_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                requests_by_class[class_name] = requests_by_class.get(class_name, 0) + 1
                if "adult" in class_name.lower():
                    adult_vs_child["adult"] += 1
                else:
                    adult_vs_child["child"] += 1

    total_messages_analyzed = sum(by_hour.values()) if by_hour else 0
    location_mention_rate = round(location_mentions / total_messages_analyzed, 3) if total_messages_analyzed > 0 else 0

    demand_metrics = DemandMetrics(
        requests_by_location=requests_by_location,
        location_mention_rate=location_mention_rate,
        requests_by_class_level=requests_by_class,
        adult_vs_child=adult_vs_child,
        by_hour_of_day=by_hour,
    )

    # Query 15: Phone call statistics by language (Spanish vs English)
    # Wrapped in try-except to handle case where language column doesn't exist yet
    phone_call_stats: PhoneCallStatistics | None = None
    try:
        call_timestamp = func.coalesce(Call.started_at, Call.created_at)
        duration_seconds = func.coalesce(
            func.nullif(Call.duration, 0),
            func.extract("epoch", Call.ended_at - Call.started_at),
            0,
        )

        # Get call stats grouped by language
        call_lang_stmt = (
            select(
                func.coalesce(Call.language, "unknown").label("language"),
                func.count(Call.id).label("call_count"),
                func.sum(duration_seconds).label("total_seconds"),
            )
            .where(
                Call.tenant_id == tenant_id,
                call_timestamp >= start_datetime,
                call_timestamp <= end_datetime,
            )
            .group_by(func.coalesce(Call.language, "unknown"))
        )
        call_lang_result = await db.execute(call_lang_stmt)

        # Get leads generated from calls by language
        call_leads_stmt = (
            select(
                func.coalesce(Call.language, "unknown").label("language"),
                func.count(func.distinct(CallSummary.lead_id)).label("lead_count"),
            )
            .select_from(Call)
            .join(CallSummary, CallSummary.call_id == Call.id)
            .where(
                Call.tenant_id == tenant_id,
                call_timestamp >= start_datetime,
                call_timestamp <= end_datetime,
                CallSummary.lead_id.isnot(None),
            )
            .group_by(func.coalesce(Call.language, "unknown"))
        )
        call_leads_result = await db.execute(call_leads_stmt)

        # Build language-to-leads map
        leads_by_language = {row.language: row.lead_count for row in call_leads_result}

        # Build phone call statistics
        by_language: dict[str, PhoneCallLanguageStats] = {}
        total_calls = 0
        total_minutes = 0.0

        for row in call_lang_result:
            lang = row.language
            count = int(row.call_count or 0)
            seconds = float(row.total_seconds or 0)
            minutes = round(seconds / 60, 2)
            leads = leads_by_language.get(lang, 0)

            by_language[lang] = PhoneCallLanguageStats(
                call_count=count,
                total_minutes=minutes,
                avg_duration_minutes=round(minutes / count, 2) if count > 0 else 0,
                leads_generated=leads,
            )
            total_calls += count
            total_minutes += minutes

        # Calculate language distribution percentages
        language_distribution: dict[str, float] = {}
        if total_calls > 0:
            for lang, stats in by_language.items():
                language_distribution[lang] = round((stats.call_count / total_calls) * 100, 1)

        phone_call_stats = PhoneCallStatistics(
            total_calls=total_calls,
            total_minutes=round(total_minutes, 2),
            by_language=by_language,
            language_distribution=language_distribution,
        )
    except Exception:
        # Language column may not exist yet - return None for phone_call_statistics
        phone_call_stats = None

    return ConversationAnalyticsResponse(
        start_date=range_start.isoformat(),
        end_date=range_end.isoformat(),
        timezone=effective_timezone,
        conversation_length=conversation_length,
        escalation_metrics=escalation_metrics,
        intent_distribution=intent_distribution,
        response_times=response_times,
        # Phase 1 metrics
        escalation_by_channel=escalation_by_channel_metrics,
        response_time_distribution=response_time_distribution,
        registration_links=registration_links_metrics,
        channel_effectiveness=channel_effectiveness_matrix,
        ai_value=ai_value_metrics,
        # Phase 2 metrics
        drop_off=drop_off_metrics,
        pushback=pushback_metrics,
        repetition=repetition_metrics,
        demand=demand_metrics,
        phone_call_statistics=phone_call_stats,
    )


# Widget Analytics Models


class VisibilityMetrics(BaseModel):
    """Widget visibility metrics."""

    impressions: int
    render_attempts: int
    render_successes: int
    render_success_rate: float
    above_fold_views: int
    above_fold_rate: float
    avg_time_to_first_view_ms: float


class AttentionMetrics(BaseModel):
    """Widget attention capture metrics."""

    widget_opens: int
    open_rate: float
    manual_opens: int
    manual_open_rate: float
    auto_opens: int
    auto_open_dismiss_count: int
    auto_open_dismiss_rate: float
    hover_count: int
    hover_rate: float


class WidgetAnalyticsResponse(BaseModel):
    """Widget analytics metrics response."""

    start_date: str
    end_date: str
    timezone: str
    visibility: VisibilityMetrics
    attention: AttentionMetrics


@router.get("/widget", response_model=WidgetAnalyticsResponse)
async def get_widget_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
) -> WidgetAnalyticsResponse:
    """Get widget engagement analytics including visibility and attention metrics."""
    # Get tenant info
    tenant_result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    tenant_created_at = tenant_result.scalar_one_or_none()
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Resolve timezone
    sms_config_result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    tenant_timezone = sms_config_result.scalar_one_or_none()
    requested_timezone = _resolve_timezone(timezone)
    effective_timezone = (
        _resolve_timezone(tenant_timezone) if tenant_timezone else requested_timezone
    )

    # Parse date range
    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()
    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=29)  # Default to 30 days
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=29)
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

    # Convert to UTC datetime range
    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_datetime = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_datetime = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Helper function to count events by type
    async def count_events(event_type: str) -> int:
        stmt = (
            select(func.count(WidgetEvent.id))
            .where(
                WidgetEvent.tenant_id == tenant_id,
                WidgetEvent.event_type == event_type,
                WidgetEvent.created_at >= start_datetime,
                WidgetEvent.created_at <= end_datetime,
            )
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    # Count basic events
    impressions = await count_events("impression")
    render_successes = await count_events("render_success")
    render_failures = await count_events("render_failure")
    widget_opens = await count_events("widget_open")
    manual_opens = await count_events("manual_open")
    auto_opens = await count_events("auto_open")
    auto_open_dismissals = await count_events("auto_open_dismiss")
    hover_count = await count_events("hover")
    focus_count = await count_events("focus")

    # Total hover/focus events
    total_hover_focus = hover_count + focus_count

    # Calculate render attempts (successes + failures, or use impressions if no render events)
    render_attempts = render_successes + render_failures
    if render_attempts == 0:
        render_attempts = impressions  # Fallback: assume all impressions were render attempts

    # Query viewport_visible events for above-fold and time-to-view data
    viewport_stmt = (
        select(WidgetEvent.event_data)
        .where(
            WidgetEvent.tenant_id == tenant_id,
            WidgetEvent.event_type == "viewport_visible",
            WidgetEvent.created_at >= start_datetime,
            WidgetEvent.created_at <= end_datetime,
        )
    )
    viewport_result = await db.execute(viewport_stmt)

    above_fold_count = 0
    total_viewport_events = 0
    total_time_to_view = 0.0

    for row in viewport_result:
        total_viewport_events += 1
        event_data = row.event_data or {}
        if event_data.get("was_above_fold"):
            above_fold_count += 1
        time_to_view = event_data.get("time_to_first_view_ms")
        if time_to_view is not None:
            total_time_to_view += float(time_to_view)

    # Calculate rates
    render_success_rate = render_successes / render_attempts if render_attempts > 0 else 0
    above_fold_rate = above_fold_count / total_viewport_events if total_viewport_events > 0 else 0
    avg_time_to_first_view = total_time_to_view / total_viewport_events if total_viewport_events > 0 else 0

    open_rate = widget_opens / impressions if impressions > 0 else 0
    manual_open_rate = manual_opens / impressions if impressions > 0 else 0
    auto_open_dismiss_rate = auto_open_dismissals / auto_opens if auto_opens > 0 else 0
    hover_rate = total_hover_focus / impressions if impressions > 0 else 0

    visibility_metrics = VisibilityMetrics(
        impressions=impressions,
        render_attempts=render_attempts,
        render_successes=render_successes if render_successes > 0 else impressions,
        render_success_rate=round(render_success_rate, 3) if render_successes > 0 else 1.0,
        above_fold_views=above_fold_count,
        above_fold_rate=round(above_fold_rate, 3),
        avg_time_to_first_view_ms=round(avg_time_to_first_view, 1),
    )

    attention_metrics = AttentionMetrics(
        widget_opens=widget_opens,
        open_rate=round(open_rate, 3),
        manual_opens=manual_opens,
        manual_open_rate=round(manual_open_rate, 3),
        auto_opens=auto_opens,
        auto_open_dismiss_count=auto_open_dismissals,
        auto_open_dismiss_rate=round(auto_open_dismiss_rate, 3),
        hover_count=total_hover_focus,
        hover_rate=round(hover_rate, 3),
    )

    return WidgetAnalyticsResponse(
        start_date=range_start.isoformat(),
        end_date=range_end.isoformat(),
        timezone=effective_timezone,
        visibility=visibility_metrics,
        attention=attention_metrics,
    )


class SettingsVariationMetrics(BaseModel):
    """Metrics for a specific widget settings configuration."""

    impressions: int
    widget_opens: int
    open_rate: float
    manual_opens: int
    auto_opens: int
    first_seen: str
    last_seen: str


class SettingsVariation(BaseModel):
    """A unique widget settings configuration with its performance metrics."""

    settings_hash: str
    settings: dict
    metrics: SettingsVariationMetrics


class SettingsSnapshotsResponse(BaseModel):
    """Response containing all widget settings variations and their metrics."""

    start_date: str
    end_date: str
    timezone: str
    variations: list[SettingsVariation]
    total_variations: int


@router.get("/widget/settings-snapshots", response_model=SettingsSnapshotsResponse)
async def get_widget_settings_snapshots(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
) -> SettingsSnapshotsResponse:
    """Get unique widget settings configurations and their performance metrics for A/B testing analysis."""
    # Get tenant info
    tenant_result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    tenant_created_at = tenant_result.scalar_one_or_none()
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Resolve timezone
    sms_config_result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    tenant_timezone = sms_config_result.scalar_one_or_none()
    requested_timezone = _resolve_timezone(timezone)
    effective_timezone = (
        _resolve_timezone(tenant_timezone) if tenant_timezone else requested_timezone
    )

    # Parse date range
    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()
    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=29)
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=29)
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

    # Convert to UTC datetime range
    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_datetime = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_datetime = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Get all impression events with settings snapshots
    impressions_stmt = (
        select(
            WidgetEvent.settings_snapshot,
            WidgetEvent.visitor_id,
            WidgetEvent.created_at,
        )
        .where(
            WidgetEvent.tenant_id == tenant_id,
            WidgetEvent.event_type == "impression",
            WidgetEvent.created_at >= start_datetime,
            WidgetEvent.created_at <= end_datetime,
            WidgetEvent.settings_snapshot.isnot(None),
        )
    )
    impressions_result = await db.execute(impressions_stmt)

    # Group impressions by settings snapshot
    import hashlib
    import json

    settings_groups: dict[str, dict] = {}

    for row in impressions_result:
        settings = row.settings_snapshot
        if not settings:
            continue

        # Create a hash of the settings for grouping
        settings_str = json.dumps(settings, sort_keys=True)
        settings_hash = hashlib.md5(settings_str.encode()).hexdigest()[:12]

        if settings_hash not in settings_groups:
            settings_groups[settings_hash] = {
                "settings": settings,
                "visitor_ids": set(),
                "first_seen": row.created_at,
                "last_seen": row.created_at,
                "impressions": 0,
            }

        group = settings_groups[settings_hash]
        group["visitor_ids"].add(row.visitor_id)
        group["impressions"] += 1
        if row.created_at < group["first_seen"]:
            group["first_seen"] = row.created_at
        if row.created_at > group["last_seen"]:
            group["last_seen"] = row.created_at

    # Get open events for each visitor to calculate conversion rates
    if settings_groups:
        all_visitor_ids = set()
        for group in settings_groups.values():
            all_visitor_ids.update(group["visitor_ids"])

        opens_stmt = (
            select(
                WidgetEvent.visitor_id,
                WidgetEvent.event_type,
            )
            .where(
                WidgetEvent.tenant_id == tenant_id,
                WidgetEvent.event_type.in_(["widget_open", "manual_open", "auto_open"]),
                WidgetEvent.created_at >= start_datetime,
                WidgetEvent.created_at <= end_datetime,
                WidgetEvent.visitor_id.in_(list(all_visitor_ids)),
            )
        )
        opens_result = await db.execute(opens_stmt)

        # Map visitors to their open events
        visitor_opens: dict[str, dict] = {}
        for row in opens_result:
            if row.visitor_id not in visitor_opens:
                visitor_opens[row.visitor_id] = {
                    "widget_open": 0,
                    "manual_open": 0,
                    "auto_open": 0,
                }
            visitor_opens[row.visitor_id][row.event_type] += 1

        # Calculate metrics for each settings variation
        variations = []
        for settings_hash, group in settings_groups.items():
            widget_opens = 0
            manual_opens = 0
            auto_opens = 0

            for visitor_id in group["visitor_ids"]:
                if visitor_id in visitor_opens:
                    widget_opens += visitor_opens[visitor_id]["widget_open"]
                    manual_opens += visitor_opens[visitor_id]["manual_open"]
                    auto_opens += visitor_opens[visitor_id]["auto_open"]

            impressions = group["impressions"]
            open_rate = widget_opens / impressions if impressions > 0 else 0

            variations.append(
                SettingsVariation(
                    settings_hash=settings_hash,
                    settings=group["settings"],
                    metrics=SettingsVariationMetrics(
                        impressions=impressions,
                        widget_opens=widget_opens,
                        open_rate=round(open_rate, 3),
                        manual_opens=manual_opens,
                        auto_opens=auto_opens,
                        first_seen=group["first_seen"].isoformat(),
                        last_seen=group["last_seen"].isoformat(),
                    ),
                )
            )

        # Sort by impressions descending
        variations.sort(key=lambda v: v.metrics.impressions, reverse=True)
    else:
        variations = []

    return SettingsSnapshotsResponse(
        start_date=range_start.isoformat(),
        end_date=range_end.isoformat(),
        timezone=effective_timezone,
        variations=variations,
        total_variations=len(variations),
    )


# Savings Analytics Models


class ChannelSavingsDetail(BaseModel):
    """Savings detail for a single channel."""

    count: int  # calls or assistant messages
    total_minutes: float
    hours_saved: float
    offshore_savings: float
    onshore_savings: float


class ConversionMetrics(BaseModel):
    """Registration link conversion tracking."""

    total_links_sent: int
    unique_phones_sent: int
    by_asset_type: dict[str, int]


class SavingsAnalyticsResponse(BaseModel):
    """Savings analytics response."""

    start_date: str
    end_date: str
    timezone: str
    total_hours_saved: float
    total_offshore_savings: float
    total_onshore_savings: float
    voice: ChannelSavingsDetail
    sms: ChannelSavingsDetail
    web_chat: ChannelSavingsDetail
    conversions: ConversionMetrics


OFFSHORE_RATE = 7.0
ONSHORE_RATE = 14.0
SMS_MINUTES_PER_MESSAGE = 2.0
WEB_MINUTES_PER_MESSAGE = 1.5


@router.get("/savings", response_model=SavingsAnalyticsResponse)
async def get_savings_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
) -> SavingsAnalyticsResponse:
    """Get savings analytics showing cost savings from AI handling calls and messages."""
    # Get tenant info
    tenant_result = await db.execute(
        select(Tenant.created_at).where(Tenant.id == tenant_id)
    )
    tenant_created_at = tenant_result.scalar_one_or_none()
    if not tenant_created_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Resolve timezone
    sms_config_result = await db.execute(
        select(TenantSmsConfig.timezone).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    tenant_timezone = sms_config_result.scalar_one_or_none()
    requested_timezone = _resolve_timezone(timezone)
    effective_timezone = (
        _resolve_timezone(tenant_timezone) if tenant_timezone else requested_timezone
    )

    # Parse date range
    tenant_start_date = tenant_created_at.date()
    today = datetime.utcnow().date()
    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=29)
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=29)
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

    # Convert to UTC datetime range
    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start, time.min))
    end_local = tz.localize(datetime.combine(range_end, time.max))
    start_datetime = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    end_datetime = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Query 1: Voice call duration
    call_timestamp = func.coalesce(Call.started_at, Call.created_at)
    duration_seconds = func.coalesce(
        func.nullif(Call.duration, 0),
        func.extract("epoch", Call.ended_at - Call.started_at),
        0,
    )
    voice_stmt = (
        select(
            func.count(Call.id).label("call_count"),
            func.sum(duration_seconds).label("total_seconds"),
        )
        .where(
            Call.tenant_id == tenant_id,
            call_timestamp >= start_datetime,
            call_timestamp <= end_datetime,
        )
    )
    voice_result = await db.execute(voice_stmt)
    voice_row = voice_result.one()
    voice_call_count = int(voice_row.call_count or 0)
    voice_total_seconds = float(voice_row.total_seconds or 0)
    voice_total_minutes = voice_total_seconds / 60
    voice_hours = voice_total_minutes / 60

    # Query 2: SMS assistant message count
    sms_msg_stmt = (
        select(func.count(Message.id).label("count"))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.role == "assistant",
            Message.created_at >= start_datetime,
            Message.created_at <= end_datetime,
        )
    )
    sms_result = await db.execute(sms_msg_stmt)
    sms_msg_count = sms_result.scalar() or 0
    sms_human_minutes = sms_msg_count * SMS_MINUTES_PER_MESSAGE
    sms_hours = sms_human_minutes / 60

    # Query 3: Web chat assistant message count
    web_msg_stmt = (
        select(func.count(Message.id).label("count"))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "web",
            Message.role == "assistant",
            Message.created_at >= start_datetime,
            Message.created_at <= end_datetime,
        )
    )
    web_result = await db.execute(web_msg_stmt)
    web_msg_count = web_result.scalar() or 0
    web_human_minutes = web_msg_count * WEB_MINUTES_PER_MESSAGE
    web_hours = web_human_minutes / 60

    # Calculate totals
    total_hours = voice_hours + sms_hours + web_hours
    total_offshore = round(total_hours * OFFSHORE_RATE, 2)
    total_onshore = round(total_hours * ONSHORE_RATE, 2)

    # Query 4: Sent assets / conversion tracking
    conversions_stmt = (
        select(
            SentAsset.asset_type,
            func.count(SentAsset.id).label("total_sent"),
            func.count(func.distinct(SentAsset.phone_normalized)).label("unique_phones"),
        )
        .where(
            SentAsset.tenant_id == tenant_id,
            SentAsset.sent_at >= start_datetime,
            SentAsset.sent_at <= end_datetime,
        )
        .group_by(SentAsset.asset_type)
    )
    conversions_result = await db.execute(conversions_stmt)

    total_links_sent = 0
    unique_phones_sent = 0
    by_asset_type: dict[str, int] = {}

    for row in conversions_result:
        count = int(row.total_sent or 0)
        phones = int(row.unique_phones or 0)
        total_links_sent += count
        unique_phones_sent += phones
        by_asset_type[row.asset_type] = count

    return SavingsAnalyticsResponse(
        start_date=range_start.isoformat(),
        end_date=range_end.isoformat(),
        timezone=effective_timezone,
        total_hours_saved=round(total_hours, 2),
        total_offshore_savings=total_offshore,
        total_onshore_savings=total_onshore,
        voice=ChannelSavingsDetail(
            count=voice_call_count,
            total_minutes=round(voice_total_minutes, 2),
            hours_saved=round(voice_hours, 2),
            offshore_savings=round(voice_hours * OFFSHORE_RATE, 2),
            onshore_savings=round(voice_hours * ONSHORE_RATE, 2),
        ),
        sms=ChannelSavingsDetail(
            count=sms_msg_count,
            total_minutes=round(sms_human_minutes, 2),
            hours_saved=round(sms_hours, 2),
            offshore_savings=round(sms_hours * OFFSHORE_RATE, 2),
            onshore_savings=round(sms_hours * ONSHORE_RATE, 2),
        ),
        web_chat=ChannelSavingsDetail(
            count=web_msg_count,
            total_minutes=round(web_human_minutes, 2),
            hours_saved=round(web_hours, 2),
            offshore_savings=round(web_hours * OFFSHORE_RATE, 2),
            onshore_savings=round(web_hours * ONSHORE_RATE, 2),
        ),
        conversions=ConversionMetrics(
            total_links_sent=total_links_sent,
            unique_phones_sent=unique_phones_sent,
            by_asset_type=by_asset_type,
        ),
    )


# ---------------------------------------------------------------------------
# Topic Analytics
# ---------------------------------------------------------------------------


class TopicCount(BaseModel):
    """Count for a single topic."""

    topic: str
    count: int
    percentage: float


class TopicAnalyticsResponse(BaseModel):
    """Response model for topic analytics."""

    start_date: str
    end_date: str
    timezone: str
    total_classified: int
    total_unclassified: int
    topics: list[TopicCount]
    by_channel: dict[str, list[TopicCount]]


TOPIC_LABELS = {
    "pricing": "Pricing & Costs",
    "scheduling": "Scheduling & Booking",
    "hours_location": "Hours & Location",
    "class_info": "Class Information",
    "registration": "Registration & Enrollment",
    "support_request": "Support / Human",
    "wrong_number": "Wrong Number",
    "general_inquiry": "General Questions",
}


@router.get("/topics", response_model=TopicAnalyticsResponse)
async def get_topic_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    timezone: Annotated[str | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
) -> TopicAnalyticsResponse:
    """Get topic distribution analytics for conversations.

    Returns counts and percentages of conversation topics, optionally
    filtered by channel, with a per-channel breakdown.
    """
    # Resolve date range (same pattern as other analytics endpoints)
    effective_timezone = _resolve_timezone(timezone)
    today = date.today()

    parsed_start = _normalize_date(start_date)
    parsed_end = _normalize_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = parsed_end - timedelta(days=29)
    elif parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=29)
    elif parsed_end is None and parsed_start is not None:
        parsed_end = today

    range_start_date = parsed_start or today - timedelta(days=29)
    range_end_date = parsed_end or today

    if range_end_date > today:
        range_end_date = today
    if range_start_date > range_end_date:
        range_start_date = range_end_date

    # Convert to UTC datetime range
    tz = pytz.timezone(effective_timezone)
    start_local = tz.localize(datetime.combine(range_start_date, time.min))
    end_local = tz.localize(datetime.combine(range_end_date, time.max))
    range_start = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
    range_end = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

    # Build base filters
    filters = [
        Conversation.tenant_id == tenant_id,
        Conversation.created_at >= range_start,
        Conversation.created_at <= range_end,
    ]
    if channel:
        filters.append(Conversation.channel == channel)

    # Total classified
    classified_stmt = (
        select(func.count(Conversation.id))
        .where(*filters, Conversation.topic.isnot(None))
    )
    classified_result = await db.execute(classified_stmt)
    total_classified = classified_result.scalar() or 0

    # Total unclassified
    unclassified_stmt = (
        select(func.count(Conversation.id))
        .where(*filters, Conversation.topic.is_(None))
    )
    unclassified_result = await db.execute(unclassified_stmt)
    total_unclassified = unclassified_result.scalar() or 0

    # Topic counts (overall)
    topic_stmt = (
        select(
            Conversation.topic,
            func.count(Conversation.id).label("count"),
        )
        .where(*filters, Conversation.topic.isnot(None))
        .group_by(Conversation.topic)
        .order_by(func.count(Conversation.id).desc())
    )
    topic_result = await db.execute(topic_stmt)
    topic_rows = list(topic_result)

    topics = [
        TopicCount(
            topic=row.topic,
            count=row.count,
            percentage=round(row.count / total_classified * 100, 1) if total_classified > 0 else 0,
        )
        for row in topic_rows
    ]

    # Topic counts by channel
    channel_stmt = (
        select(
            Conversation.channel,
            Conversation.topic,
            func.count(Conversation.id).label("count"),
        )
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= range_start,
            Conversation.created_at <= range_end,
            Conversation.topic.isnot(None),
        )
        .group_by(Conversation.channel, Conversation.topic)
        .order_by(Conversation.channel, func.count(Conversation.id).desc())
    )
    channel_result = await db.execute(channel_stmt)
    channel_rows = list(channel_result)

    # Group by channel
    by_channel: dict[str, list[TopicCount]] = {}
    channel_totals: dict[str, int] = {}
    for row in channel_rows:
        channel_totals.setdefault(row.channel, 0)
        channel_totals[row.channel] += row.count

    for row in channel_rows:
        ch_total = channel_totals.get(row.channel, 1)
        by_channel.setdefault(row.channel, []).append(
            TopicCount(
                topic=row.topic,
                count=row.count,
                percentage=round(row.count / ch_total * 100, 1) if ch_total > 0 else 0,
            )
        )

    return TopicAnalyticsResponse(
        start_date=range_start_date.isoformat(),
        end_date=range_end_date.isoformat(),
        timezone=effective_timezone,
        total_classified=total_classified,
        total_unclassified=total_unclassified,
        topics=topics,
        by_channel=by_channel,
    )
