"""Dashboard analytics API endpoints.

Endpoints for Communications Health, CHI, SMS Burst Detection,
and Anomaly Alerts.
"""

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin, require_tenant_context
from app.persistence.models.tenant import User
from app.api.schemas.dashboard_analytics import (
    AnomalyAlertListResponse,
    AnomalyAlertResponse,
    BotHumanWorkload,
    CallDurationMetrics,
    ChannelMetrics,
    CHIAnalyticsResponse,
    CHIByHandler,
    CHIDetailResponse,
    CHIDistributionBucket,
    CHISignalItem,
    CHISummaryResponse,
    CommunicationsHealthResponse,
    FrustrationDriver,
    HeatmapCell,
    HeatmapResponse,
    ImprovementOpportunity,
    ReliabilityMetrics,
    SmsBurstConfigResponse,
    SmsBurstConfigUpdate,
    SmsBurstDashboardResponse,
    SmsBurstIncidentResponse,
    SmsBurstSummary,
    TrendComparison,
    YearlyActivityCell,
    YearlyActivityResponse,
)
from app.domain.services.chi_service import CHIService
from app.persistence.database import get_db
from app.persistence.models.anomaly_alert import AnomalyAlert
from app.persistence.models.call import Call
from app.persistence.models.communications_health_snapshot import (
    CommunicationsHealthSnapshot,
)
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.escalation import Escalation
from app.persistence.models.sms_burst_config import SmsBurstConfig
from app.persistence.models.sms_burst_incident import SmsBurstIncident

logger = logging.getLogger(__name__)

router = APIRouter()


def _mask_phone(number: str) -> str:
    """Mask phone number for display: +1234567890 -> ***-***-7890."""
    if len(number) >= 4:
        return f"***-***-{number[-4:]}"
    return "***"


# ============================================================
# Communications Health
# ============================================================


@router.get("/communications-health", response_model=CommunicationsHealthResponse)
async def get_communications_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    days: int = Query(7, ge=1, le=90),
) -> CommunicationsHealthResponse:
    """Get communications health metrics for a tenant."""
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    # Try snapshots first, fall back to real-time queries
    snapshot_stmt = (
        select(CommunicationsHealthSnapshot)
        .where(
            CommunicationsHealthSnapshot.tenant_id == tenant_id,
            CommunicationsHealthSnapshot.snapshot_date >= start,
            CommunicationsHealthSnapshot.snapshot_hour.is_(None),  # Daily rollups
        )
    )
    snap_result = await db.execute(snapshot_stmt)
    snapshots = list(snap_result.scalars().all())

    if snapshots:
        return _aggregate_from_snapshots(snapshots, tenant_id, days)

    # Real-time fallback: query operational tables directly
    return await _compute_health_realtime(db, tenant_id, start, now, prev_start)


async def _compute_health_realtime(
    db: AsyncSession,
    tenant_id: int,
    start: datetime,
    end: datetime,
    prev_start: datetime,
) -> CommunicationsHealthResponse:
    """Compute health metrics from operational tables."""
    # Calls
    call_stmt = select(Call).where(
        Call.tenant_id == tenant_id,
        Call.started_at >= start,
        Call.started_at < end,
    )
    call_result = await db.execute(call_stmt)
    calls = list(call_result.scalars().all())

    inbound_calls = sum(1 for c in calls if c.direction == "inbound")
    outbound_calls = sum(1 for c in calls if c.direction == "outbound")
    total_calls = len(calls)

    durations = [c.duration for c in calls if c.duration is not None]
    total_minutes = sum(durations) / 60 if durations else 0.0
    avg_dur = sum(durations) / len(durations) if durations else 0.0
    sorted_dur = sorted(durations)
    median_dur = sorted_dur[len(sorted_dur) // 2] if sorted_dur else 0.0
    short_calls = sum(1 for d in durations if d < 30)
    long_calls = sum(1 for d in durations if d > 600)
    short_pct = (short_calls / len(durations) * 100) if durations else 0.0
    long_pct = (long_calls / len(durations) * 100) if durations else 0.0

    dropped = sum(1 for c in calls if c.status in ("no-answer", "busy", "canceled"))
    failed = sum(1 for c in calls if c.status == "failed")

    # SMS
    sms_stmt = (
        select(Message.role, func.count())
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.created_at >= start,
            Message.created_at < end,
        )
        .group_by(Message.role)
    )
    sms_result = await db.execute(sms_stmt)
    sms_counts = dict(sms_result.all())
    inbound_sms = sms_counts.get("user", 0)
    outbound_sms = sms_counts.get("assistant", 0)
    total_sms = inbound_sms + outbound_sms

    # Email (count from email channel conversations)
    email_stmt = (
        select(Message.role, func.count())
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "email",
            Message.created_at >= start,
            Message.created_at < end,
        )
        .group_by(Message.role)
    )
    email_result = await db.execute(email_stmt)
    email_counts = dict(email_result.all())
    inbound_emails = email_counts.get("user", 0)
    outbound_emails = email_counts.get("assistant", 0)
    total_emails = inbound_emails + outbound_emails

    total_interactions = total_calls + total_sms + total_emails

    # Channel mix
    channel_mix = {}
    if total_interactions > 0:
        channel_mix = {
            "calls": round(total_calls / total_interactions * 100, 1),
            "sms": round(total_sms / total_interactions * 100, 1),
            "email": round(total_emails / total_interactions * 100, 1),
        }

    # Trend vs previous period
    prev_count_stmt = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= prev_start,
            Conversation.created_at < start,
        )
    )
    prev_result = await db.execute(prev_count_stmt)
    prev_count = prev_result.scalar() or 0
    change_pct = None
    if prev_count > 0:
        change_pct = round((total_interactions - prev_count) / prev_count * 100, 1)

    # Bot vs human (based on escalations)
    esc_stmt = (
        select(func.count())
        .select_from(Escalation)
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= start,
            Escalation.created_at < end,
        )
    )
    esc_result = await db.execute(esc_stmt)
    escalated = esc_result.scalar() or 0

    conv_count_stmt = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
    )
    conv_result = await db.execute(conv_count_stmt)
    total_convs = conv_result.scalar() or 1  # Avoid division by zero

    bot_handled = total_convs - escalated
    esc_rate = round(escalated / total_convs * 100, 1) if total_convs else 0.0
    bot_pct = round(bot_handled / total_convs * 100, 1) if total_convs else 0.0

    return CommunicationsHealthResponse(
        calls=ChannelMetrics(total=total_calls, inbound=inbound_calls, outbound=outbound_calls),
        sms=ChannelMetrics(total=total_sms, inbound=inbound_sms, outbound=outbound_sms),
        email=ChannelMetrics(total=total_emails, inbound=inbound_emails, outbound=outbound_emails),
        total_interactions=total_interactions,
        channel_mix=channel_mix,
        trend=TrendComparison(current=total_interactions, previous=prev_count, change_pct=change_pct),
        call_duration=CallDurationMetrics(
            total_minutes=round(total_minutes, 1),
            avg_seconds=round(avg_dur, 1),
            median_seconds=round(median_dur, 1),
            short_call_pct=round(short_pct, 1),
            long_call_pct=round(long_pct, 1),
            total_calls=total_calls,
        ),
        bot_human=BotHumanWorkload(
            bot_handled_pct=bot_pct,
            human_handled_pct=0.0,  # No dedicated human handling yet
            escalated_pct=esc_rate,
            bot_resolution_rate=round(100 - esc_rate, 1),
            escalation_rate=esc_rate,
        ),
        reliability=ReliabilityMetrics(
            dropped_calls=dropped,
            failed_calls=failed,
        ),
    )


def _aggregate_from_snapshots(
    snapshots: list[CommunicationsHealthSnapshot],
    tenant_id: int,
    days: int,
) -> CommunicationsHealthResponse:
    """Aggregate pre-computed snapshots into a response."""
    total_calls = sum(s.total_calls for s in snapshots)
    inbound_calls = sum(s.inbound_calls for s in snapshots)
    outbound_calls = sum(s.outbound_calls for s in snapshots)
    total_sms = sum(s.total_sms for s in snapshots)
    inbound_sms = sum(s.inbound_sms for s in snapshots)
    outbound_sms = sum(s.outbound_sms for s in snapshots)
    total_emails = sum(s.total_emails for s in snapshots)
    inbound_emails = sum(s.inbound_emails for s in snapshots)
    outbound_emails = sum(s.outbound_emails for s in snapshots)
    total_interactions = total_calls + total_sms + total_emails

    channel_mix = {}
    if total_interactions > 0:
        channel_mix = {
            "calls": round(total_calls / total_interactions * 100, 1),
            "sms": round(total_sms / total_interactions * 100, 1),
            "email": round(total_emails / total_interactions * 100, 1),
        }

    total_minutes = sum(s.total_call_minutes for s in snapshots)
    call_count = sum(s.total_calls for s in snapshots)
    avg_dur = sum(s.avg_call_duration_seconds * s.total_calls for s in snapshots if s.total_calls) / max(call_count, 1)
    short_count = sum(s.short_calls_count for s in snapshots)
    long_count = sum(s.long_calls_count for s in snapshots)
    short_pct = (short_count / call_count * 100) if call_count else 0.0
    long_pct = (long_count / call_count * 100) if call_count else 0.0

    bot_handled = sum(s.bot_handled_count for s in snapshots)
    escalated = sum(s.escalated_count for s in snapshots)
    total_handled = bot_handled + escalated
    esc_rate = round(escalated / total_handled * 100, 1) if total_handled else 0.0

    return CommunicationsHealthResponse(
        calls=ChannelMetrics(total=total_calls, inbound=inbound_calls, outbound=outbound_calls),
        sms=ChannelMetrics(total=total_sms, inbound=inbound_sms, outbound=outbound_sms),
        email=ChannelMetrics(total=total_emails, inbound=inbound_emails, outbound=outbound_emails),
        total_interactions=total_interactions,
        channel_mix=channel_mix,
        trend=TrendComparison(current=total_interactions),
        call_duration=CallDurationMetrics(
            total_minutes=round(total_minutes, 1),
            avg_seconds=round(avg_dur, 1),
            short_call_pct=round(short_pct, 1),
            long_call_pct=round(long_pct, 1),
            total_calls=call_count,
        ),
        bot_human=BotHumanWorkload(
            bot_handled_pct=round(100 - esc_rate, 1),
            escalated_pct=esc_rate,
            bot_resolution_rate=round(100 - esc_rate, 1),
            escalation_rate=esc_rate,
        ),
        reliability=ReliabilityMetrics(
            dropped_calls=sum(s.dropped_calls_count for s in snapshots),
            failed_calls=sum(s.failed_calls_count for s in snapshots),
            failed_sms=sum(s.failed_sms_count for s in snapshots),
            bounced_emails=sum(s.bounced_emails_count for s in snapshots),
            api_errors=sum(s.api_errors_count for s in snapshots),
        ),
    )


@router.get("/communications-health/heatmap", response_model=HeatmapResponse)
async def get_communications_heatmap(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    days: int = Query(7, ge=1, le=30),
) -> HeatmapResponse:
    """Get time-of-day heatmap for call/SMS volume."""
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    # Try snapshots
    stmt = (
        select(CommunicationsHealthSnapshot)
        .where(
            CommunicationsHealthSnapshot.tenant_id == tenant_id,
            CommunicationsHealthSnapshot.snapshot_date >= start,
            CommunicationsHealthSnapshot.snapshot_hour.isnot(None),
        )
    )
    result = await db.execute(stmt)
    snapshots = list(result.scalars().all())

    if snapshots:
        cells = []
        # Group by (day_of_week, hour)
        grid: dict[tuple[int, int], dict] = {}
        for s in snapshots:
            dow = s.snapshot_date.weekday() if hasattr(s.snapshot_date, 'weekday') else 0
            key = (dow, s.snapshot_hour)
            if key not in grid:
                grid[key] = {"calls": 0, "sms": 0}
            grid[key]["calls"] += s.total_calls
            grid[key]["sms"] += s.total_sms
        for (day, hour), vals in grid.items():
            cells.append(HeatmapCell(day=day, hour=hour, calls=vals["calls"], sms=vals["sms"]))
        return HeatmapResponse(cells=cells)

    # Real-time fallback: query calls and messages by hour
    call_stmt = (
        select(
            func.extract("dow", Call.started_at).label("dow"),
            func.extract("hour", Call.started_at).label("hour"),
            func.count().label("cnt"),
        )
        .where(Call.tenant_id == tenant_id, Call.started_at >= start)
        .group_by("dow", "hour")
    )
    call_res = await db.execute(call_stmt)
    call_data = {(int(r.dow), int(r.hour)): r.cnt for r in call_res.all()}

    sms_stmt = (
        select(
            func.extract("dow", Message.created_at).label("dow"),
            func.extract("hour", Message.created_at).label("hour"),
            func.count().label("cnt"),
        )
        .join(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.created_at >= start,
        )
        .group_by("dow", "hour")
    )
    sms_res = await db.execute(sms_stmt)
    sms_data = {(int(r.dow), int(r.hour)): r.cnt for r in sms_res.all()}

    cells = []
    for day in range(7):
        for hour in range(24):
            c = call_data.get((day, hour), 0)
            s = sms_data.get((day, hour), 0)
            if c or s:
                cells.append(HeatmapCell(day=day, hour=hour, calls=c, sms=s))

    return HeatmapResponse(cells=cells)


@router.get("/communications-health/yearly", response_model=YearlyActivityResponse)
async def get_yearly_activity(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> YearlyActivityResponse:
    """Get daily activity data for the past year (GitHub-style contribution graph)."""
    now = datetime.utcnow()
    start = now - timedelta(days=365)

    # Calls by date
    call_stmt = (
        select(
            func.date(Call.started_at).label("date"),
            func.count().label("cnt"),
        )
        .where(Call.tenant_id == tenant_id, Call.started_at >= start)
        .group_by(func.date(Call.started_at))
    )
    call_res = await db.execute(call_stmt)
    call_data = {str(r.date): r.cnt for r in call_res.all()}

    # SMS by date
    sms_stmt = (
        select(
            func.date(Message.created_at).label("date"),
            func.count().label("cnt"),
        )
        .join(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.created_at >= start,
        )
        .group_by(func.date(Message.created_at))
    )
    sms_res = await db.execute(sms_stmt)
    sms_data = {str(r.date): r.cnt for r in sms_res.all()}

    # Emails by date
    email_stmt = (
        select(
            func.date(Message.created_at).label("date"),
            func.count().label("cnt"),
        )
        .join(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "email",
            Message.created_at >= start,
        )
        .group_by(func.date(Message.created_at))
    )
    email_res = await db.execute(email_stmt)
    email_data = {str(r.date): r.cnt for r in email_res.all()}

    # Generate all dates in range
    cells = []
    current = start.date()
    end_date = now.date()
    while current <= end_date:
        date_str = current.isoformat()
        calls = call_data.get(date_str, 0)
        sms = sms_data.get(date_str, 0)
        emails = email_data.get(date_str, 0)
        if calls or sms or emails:
            cells.append(YearlyActivityCell(
                date=date_str,
                calls=calls,
                sms=sms,
                emails=emails,
            ))
        current += timedelta(days=1)

    return YearlyActivityResponse(cells=cells)


# ============================================================
# Anomaly Alerts
# ============================================================


@router.get("/anomalies", response_model=AnomalyAlertListResponse)
async def get_anomaly_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=100),
) -> AnomalyAlertListResponse:
    """Get recent anomaly alerts."""
    stmt = (
        select(AnomalyAlert)
        .where(AnomalyAlert.tenant_id == tenant_id)
        .order_by(AnomalyAlert.detected_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(AnomalyAlert.status == status_filter)

    result = await db.execute(stmt)
    alerts = list(result.scalars().all())

    active_count = sum(1 for a in alerts if a.status == "active")

    return AnomalyAlertListResponse(
        alerts=[
            AnomalyAlertResponse(
                id=a.id,
                alert_type=a.alert_type,
                severity=a.severity,
                metric_name=a.metric_name,
                current_value=a.current_value,
                baseline_value=a.baseline_value,
                threshold_percent=a.threshold_percent,
                details=a.details,
                status=a.status,
                detected_at=a.detected_at,
            )
            for a in alerts
        ],
        active_count=active_count,
    )


@router.patch("/anomalies/{alert_id}")
async def update_anomaly_alert(
    alert_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    new_status: str = Query(..., alias="status"),
) -> dict:
    """Acknowledge or resolve an anomaly alert."""
    stmt = select(AnomalyAlert).where(
        AnomalyAlert.id == alert_id,
        AnomalyAlert.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.utcnow()
    if new_status == "acknowledged":
        alert.status = "acknowledged"
        alert.acknowledged_at = now
    elif new_status == "resolved":
        alert.status = "resolved"
        alert.resolved_at = now
    else:
        raise HTTPException(status_code=400, detail="Invalid status")

    await db.commit()
    return {"id": alert_id, "status": alert.status}


# ============================================================
# Customer Happiness Index (CHI)
# ============================================================


@router.get("/chi", response_model=CHIAnalyticsResponse)
async def get_chi_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    days: int = Query(7, ge=1, le=90),
) -> CHIAnalyticsResponse:
    """Get CHI analytics summary."""
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get conversations with CHI scores
    stmt = (
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= start,
            Conversation.chi_score.isnot(None),
        )
    )
    result = await db.execute(stmt)
    scored = list(result.scalars().all())

    # Today's avg
    today_scores = [c.chi_score for c in scored if c.created_at >= today_start]
    avg_today = round(sum(today_scores) / len(today_scores), 1) if today_scores else None

    # Period avg
    period_scores = [c.chi_score for c in scored]
    avg_period = round(sum(period_scores) / len(period_scores), 1) if period_scores else None

    # Previous period avg for trend
    prev_stmt = (
        select(func.avg(Conversation.chi_score))
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= prev_start,
            Conversation.created_at < start,
            Conversation.chi_score.isnot(None),
        )
    )
    prev_result = await db.execute(prev_stmt)
    prev_avg = prev_result.scalar()
    trend_pct = None
    if prev_avg and avg_period:
        trend_pct = round((avg_period - prev_avg) / prev_avg * 100, 1)

    # Distribution
    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for c in scored:
        s = c.chi_score
        if s < 20:
            buckets["0-20"] += 1
        elif s < 40:
            buckets["20-40"] += 1
        elif s < 60:
            buckets["40-60"] += 1
        elif s < 80:
            buckets["60-80"] += 1
        else:
            buckets["80-100"] += 1

    total = len(scored) or 1
    distribution = [
        CHIDistributionBucket(bucket=k, count=v, pct=round(v / total * 100, 1))
        for k, v in buckets.items()
    ]

    # Top frustration drivers from chi_signals
    signal_counter: Counter = Counter()
    signal_impacts: dict[str, list[int]] = {}
    for c in scored:
        if c.chi_signals and isinstance(c.chi_signals, dict):
            for sig in c.chi_signals.get("signals", []):
                name = sig.get("name", "")
                weight = sig.get("weight", 0)
                if weight < 0:
                    signal_counter[name] += 1
                    signal_impacts.setdefault(name, []).append(weight)

    top_drivers = [
        FrustrationDriver(
            signal=name,
            count=count,
            avg_impact=round(sum(signal_impacts.get(name, [0])) / max(count, 1), 1),
        )
        for name, count in signal_counter.most_common(5)
    ]

    # Repeat contact rate
    repeat_count = sum(
        1 for c in scored
        if c.chi_signals and isinstance(c.chi_signals, dict)
        and any(s.get("name") == "repeat_contact_48h" for s in c.chi_signals.get("signals", []))
    )
    repeat_rate = round(repeat_count / total * 100, 1) if total else 0.0

    # Improvement opportunities (top 3 drivers reformatted)
    improvements = []
    for driver in top_drivers[:3]:
        improvements.append(ImprovementOpportunity(
            recommendation=f"Reduce {driver.signal.replace('_', ' ')} ({driver.count} this period)",
            supporting_count=driver.count,
            estimated_chi_impact=driver.avg_impact,
        ))

    return CHIAnalyticsResponse(
        summary=CHISummaryResponse(
            avg_chi_today=avg_today,
            avg_chi_7d=avg_period,
            trend_pct=trend_pct,
            conversations_scored=len(scored),
        ),
        distribution=distribution,
        top_frustration_drivers=top_drivers,
        repeat_contact_rate_48h=repeat_rate,
        improvement_opportunities=improvements,
    )


@router.get("/chi/{conversation_id}", response_model=CHIDetailResponse)
async def get_conversation_chi(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CHIDetailResponse:
    """Get detailed CHI breakdown for a specific conversation."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Compute on-demand if not yet computed
    if conv.chi_score is None:
        chi_service = CHIService(db)
        chi_result = await chi_service.compute_for_conversation(conv)
        conv.chi_score = chi_result.score
        conv.chi_computed_at = datetime.utcnow()
        conv.chi_signals = chi_result.to_json()
        await db.commit()

    signals_data = conv.chi_signals or {}
    return CHIDetailResponse(
        conversation_id=conv.id,
        score=conv.chi_score,
        computed_at=conv.chi_computed_at,
        frustration_score=signals_data.get("frustration_score", 0.0),
        satisfaction_score=signals_data.get("satisfaction_score", 0.0),
        outcome_score=signals_data.get("outcome_score", 0.0),
        signals=[
            CHISignalItem(
                name=s.get("name", ""),
                weight=s.get("weight", 0),
                detail=s.get("detail", ""),
            )
            for s in signals_data.get("signals", [])
        ],
    )


# ============================================================
# SMS Burst Detection
# ============================================================


@router.get("/sms-bursts", response_model=SmsBurstDashboardResponse)
async def get_sms_burst_dashboard(
    _admin: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    hours: int = Query(24, ge=1, le=168),
) -> SmsBurstDashboardResponse:
    """Get SMS burst detection dashboard data."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stmt = (
        select(SmsBurstIncident)
        .where(
            SmsBurstIncident.tenant_id == tenant_id,
            SmsBurstIncident.detected_at >= cutoff,
        )
        .order_by(SmsBurstIncident.detected_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    incidents = list(result.scalars().all())

    # Summary
    numbers = set(i.to_number for i in incidents)
    total_messages = sum(i.message_count for i in incidents)
    critical_count = sum(1 for i in incidents if i.status == "active" and i.severity == "critical")

    worst = None
    worst_count = 0
    for i in incidents:
        if i.message_count > worst_count:
            worst = i.to_number
            worst_count = i.message_count

    return SmsBurstDashboardResponse(
        summary=SmsBurstSummary(
            total_incidents_24h=len(incidents),
            numbers_impacted=len(numbers),
            total_messages_in_bursts=total_messages,
            worst_offender_number=_mask_phone(worst) if worst else None,
            worst_offender_count=worst_count,
            active_critical_count=critical_count,
        ),
        incidents=[
            SmsBurstIncidentResponse(
                id=i.id,
                tenant_id=i.tenant_id,
                to_number_masked=_mask_phone(i.to_number),
                message_count=i.message_count,
                first_message_at=i.first_message_at,
                last_message_at=i.last_message_at,
                time_window_seconds=i.time_window_seconds,
                avg_gap_seconds=i.avg_gap_seconds,
                severity=i.severity,
                has_identical_content=i.has_identical_content,
                content_similarity_score=i.content_similarity_score,
                likely_cause=i.likely_cause,
                handler=i.handler,
                status=i.status,
                auto_blocked=i.auto_blocked,
                notes=i.notes,
                detected_at=i.detected_at,
            )
            for i in incidents
        ],
    )


@router.patch("/sms-bursts/{incident_id}")
async def update_burst_incident(
    incident_id: int,
    _admin: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    new_status: str = Query(..., alias="status"),
    notes: str | None = Query(None),
) -> dict:
    """Acknowledge or resolve an SMS burst incident."""
    stmt = select(SmsBurstIncident).where(
        SmsBurstIncident.id == incident_id,
        SmsBurstIncident.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    now = datetime.utcnow()
    if new_status == "acknowledged":
        incident.status = "acknowledged"
        incident.acknowledged_at = now
    elif new_status == "resolved":
        incident.status = "resolved"
        incident.resolved_at = now
    else:
        raise HTTPException(status_code=400, detail="Invalid status")

    if notes:
        incident.notes = notes
    await db.commit()
    return {"id": incident_id, "status": incident.status}


@router.get("/sms-burst-config", response_model=SmsBurstConfigResponse)
async def get_burst_config(
    _admin: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> SmsBurstConfigResponse:
    """Get current SMS burst detection configuration."""
    stmt = select(SmsBurstConfig).where(SmsBurstConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        return SmsBurstConfigResponse()  # Defaults

    return SmsBurstConfigResponse(
        enabled=config.enabled,
        time_window_seconds=config.time_window_seconds,
        message_threshold=config.message_threshold,
        high_severity_threshold=config.high_severity_threshold,
        rapid_gap_min_seconds=config.rapid_gap_min_seconds,
        rapid_gap_max_seconds=config.rapid_gap_max_seconds,
        identical_content_threshold=config.identical_content_threshold,
        similarity_threshold=config.similarity_threshold,
        auto_block_enabled=config.auto_block_enabled,
        auto_block_threshold=config.auto_block_threshold,
        excluded_flows=config.excluded_flows or [],
    )


@router.put("/sms-burst-config", response_model=SmsBurstConfigResponse)
async def update_burst_config(
    update: SmsBurstConfigUpdate,
    _admin: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> SmsBurstConfigResponse:
    """Update SMS burst detection configuration."""
    stmt = select(SmsBurstConfig).where(SmsBurstConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        config = SmsBurstConfig(tenant_id=tenant_id)
        db.add(config)

    # Apply only provided fields
    for field_name, value in update.model_dump(exclude_unset=True).items():
        setattr(config, field_name, value)

    await db.commit()
    await db.refresh(config)

    return SmsBurstConfigResponse(
        enabled=config.enabled,
        time_window_seconds=config.time_window_seconds,
        message_threshold=config.message_threshold,
        high_severity_threshold=config.high_severity_threshold,
        rapid_gap_min_seconds=config.rapid_gap_min_seconds,
        rapid_gap_max_seconds=config.rapid_gap_max_seconds,
        identical_content_threshold=config.identical_content_threshold,
        similarity_threshold=config.similarity_threshold,
        auto_block_enabled=config.auto_block_enabled,
        auto_block_threshold=config.auto_block_threshold,
        excluded_flows=config.excluded_flows or [],
    )
