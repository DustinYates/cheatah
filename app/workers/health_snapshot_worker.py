"""Health snapshot worker for pre-computing communications metrics.

Runs hourly via Cloud Tasks. Aggregates operational data into
communications_health_snapshots for fast dashboard queries.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.persistence.models.anomaly_alert import AnomalyAlert
from app.persistence.models.call import Call
from app.persistence.models.communications_health_snapshot import (
    CommunicationsHealthSnapshot,
)
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.escalation import Escalation
from app.persistence.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()

# Anomaly detection thresholds (defaults)
VOLUME_DROP_PCT = 50
ESCALATION_SPIKE_MULTIPLIER = 2.0
DURATION_SPIKE_MULTIPLIER = 2.0
SMS_FAILURE_RATE_PCT = 10
SHORT_CALL_PCT = 40


@router.post("/compute-health-snapshot")
async def compute_health_snapshot_task(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Compute health snapshots for all active tenants for the previous hour.

    Called hourly by Cloud Tasks.
    """
    now = datetime.utcnow()
    # Compute for the hour that just ended
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1)
    snapshot_hour = hour_start.hour

    # Get all active tenants
    tenant_stmt = select(Tenant.id).where(Tenant.is_active.is_(True))
    tenant_result = await db.execute(tenant_stmt)
    tenant_ids = [r[0] for r in tenant_result.all()]

    processed = 0
    errors = 0

    for tenant_id in tenant_ids:
        try:
            await _compute_for_tenant(
                db, tenant_id, hour_start, hour_end, snapshot_hour
            )
            processed += 1
        except Exception as e:
            logger.error(
                f"Health snapshot failed for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            errors += 1

    logger.info(
        f"Health snapshot complete: {processed} tenants processed, {errors} errors"
    )
    return {"processed": processed, "errors": errors, "hour": snapshot_hour}


async def _compute_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    hour_start: datetime,
    hour_end: datetime,
    snapshot_hour: int,
) -> None:
    """Compute and store metrics for one tenant for one hour."""
    # --- Calls ---
    call_stmt = select(Call).where(
        Call.tenant_id == tenant_id,
        Call.started_at >= hour_start,
        Call.started_at < hour_end,
    )
    call_result = await db.execute(call_stmt)
    calls = list(call_result.scalars().all())

    total_calls = len(calls)
    inbound_calls = sum(1 for c in calls if c.direction == "inbound")
    outbound_calls = sum(1 for c in calls if c.direction == "outbound")

    durations = [c.duration for c in calls if c.duration is not None]
    total_minutes = sum(durations) / 60 if durations else 0.0
    avg_dur = sum(durations) / len(durations) if durations else 0.0
    sorted_dur = sorted(durations)
    median_dur = sorted_dur[len(sorted_dur) // 2] if sorted_dur else 0.0
    short_calls = sum(1 for d in durations if d < 30)
    long_calls = sum(1 for d in durations if d > 600)
    dropped = sum(1 for c in calls if c.status in ("no-answer", "busy", "canceled"))
    failed_calls = sum(1 for c in calls if c.status == "failed")

    # --- SMS ---
    sms_stmt = (
        select(Message.role, func.count())
        .join(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Message.created_at >= hour_start,
            Message.created_at < hour_end,
        )
        .group_by(Message.role)
    )
    sms_result = await db.execute(sms_stmt)
    sms_counts = dict(sms_result.all())
    inbound_sms = sms_counts.get("user", 0)
    outbound_sms = sms_counts.get("assistant", 0)

    # --- Email ---
    email_stmt = (
        select(Message.role, func.count())
        .join(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "email",
            Message.created_at >= hour_start,
            Message.created_at < hour_end,
        )
        .group_by(Message.role)
    )
    email_result = await db.execute(email_stmt)
    email_counts = dict(email_result.all())
    inbound_emails = email_counts.get("user", 0)
    outbound_emails = email_counts.get("assistant", 0)

    # --- Bot vs Human ---
    conv_stmt = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= hour_start,
            Conversation.created_at < hour_end,
        )
    )
    conv_result = await db.execute(conv_stmt)
    total_convs = conv_result.scalar() or 0

    esc_stmt = (
        select(func.count())
        .select_from(Escalation)
        .where(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= hour_start,
            Escalation.created_at < hour_end,
        )
    )
    esc_result = await db.execute(esc_stmt)
    escalated = esc_result.scalar() or 0
    bot_handled = max(0, total_convs - escalated)

    # --- Upsert snapshot ---
    existing_stmt = select(CommunicationsHealthSnapshot).where(
        CommunicationsHealthSnapshot.tenant_id == tenant_id,
        CommunicationsHealthSnapshot.snapshot_date == hour_start.date(),
        CommunicationsHealthSnapshot.snapshot_hour == snapshot_hour,
    )
    existing_result = await db.execute(existing_stmt)
    snapshot = existing_result.scalar_one_or_none()

    if not snapshot:
        snapshot = CommunicationsHealthSnapshot(
            tenant_id=tenant_id,
            snapshot_date=datetime.combine(hour_start.date(), datetime.min.time()),
            snapshot_hour=snapshot_hour,
        )
        db.add(snapshot)

    snapshot.total_calls = total_calls
    snapshot.inbound_calls = inbound_calls
    snapshot.outbound_calls = outbound_calls
    snapshot.total_sms = inbound_sms + outbound_sms
    snapshot.inbound_sms = inbound_sms
    snapshot.outbound_sms = outbound_sms
    snapshot.total_emails = inbound_emails + outbound_emails
    snapshot.inbound_emails = inbound_emails
    snapshot.outbound_emails = outbound_emails
    snapshot.total_call_minutes = round(total_minutes, 2)
    snapshot.avg_call_duration_seconds = round(avg_dur, 2)
    snapshot.median_call_duration_seconds = round(median_dur, 2)
    snapshot.short_calls_count = short_calls
    snapshot.long_calls_count = long_calls
    snapshot.bot_handled_count = bot_handled
    snapshot.escalated_count = escalated
    snapshot.bot_resolution_count = bot_handled  # Simplified
    snapshot.dropped_calls_count = dropped
    snapshot.failed_calls_count = failed_calls

    await db.commit()

    # --- Anomaly detection ---
    await _check_anomalies(db, tenant_id, snapshot, hour_start)


async def _check_anomalies(
    db: AsyncSession,
    tenant_id: int,
    current: CommunicationsHealthSnapshot,
    hour_start: datetime,
) -> None:
    """Compare current hour against 7-day baseline and create alerts."""
    baseline_start = hour_start - timedelta(days=7)

    baseline_stmt = (
        select(
            func.avg(CommunicationsHealthSnapshot.total_calls).label("avg_calls"),
            func.avg(CommunicationsHealthSnapshot.total_sms).label("avg_sms"),
            func.avg(CommunicationsHealthSnapshot.escalated_count).label("avg_esc"),
            func.avg(CommunicationsHealthSnapshot.avg_call_duration_seconds).label("avg_dur"),
        )
        .where(
            CommunicationsHealthSnapshot.tenant_id == tenant_id,
            CommunicationsHealthSnapshot.snapshot_date >= baseline_start.date(),
            CommunicationsHealthSnapshot.snapshot_hour == current.snapshot_hour,
        )
    )
    result = await db.execute(baseline_stmt)
    baseline = result.one_or_none()

    if not baseline or baseline.avg_calls is None:
        return  # Not enough data for baseline

    # Volume drop
    if baseline.avg_calls > 5:
        total_vol = current.total_calls + current.total_sms
        baseline_vol = (baseline.avg_calls or 0) + (baseline.avg_sms or 0)
        if baseline_vol > 0 and total_vol < baseline_vol * (1 - VOLUME_DROP_PCT / 100):
            await _create_alert(
                db, tenant_id, "volume_drop", "warning", "total_volume",
                total_vol, baseline_vol, VOLUME_DROP_PCT,
            )

    # Escalation spike
    if baseline.avg_esc and baseline.avg_esc > 0:
        if current.escalated_count > baseline.avg_esc * ESCALATION_SPIKE_MULTIPLIER:
            await _create_alert(
                db, tenant_id, "escalation_spike", "warning", "escalation_count",
                current.escalated_count, baseline.avg_esc,
                (ESCALATION_SPIKE_MULTIPLIER - 1) * 100,
            )

    # Duration spike
    if baseline.avg_dur and baseline.avg_dur > 0:
        if current.avg_call_duration_seconds > baseline.avg_dur * DURATION_SPIKE_MULTIPLIER:
            await _create_alert(
                db, tenant_id, "duration_spike", "info", "avg_call_duration",
                current.avg_call_duration_seconds, baseline.avg_dur,
                (DURATION_SPIKE_MULTIPLIER - 1) * 100,
            )


async def _create_alert(
    db: AsyncSession,
    tenant_id: int,
    alert_type: str,
    severity: str,
    metric_name: str,
    current_value: float,
    baseline_value: float,
    threshold_percent: float,
) -> None:
    """Create an anomaly alert if one doesn't already exist for this hour."""
    # Check for existing active alert of same type in last 2 hours
    recent_stmt = (
        select(func.count())
        .select_from(AnomalyAlert)
        .where(
            AnomalyAlert.tenant_id == tenant_id,
            AnomalyAlert.alert_type == alert_type,
            AnomalyAlert.status == "active",
            AnomalyAlert.detected_at >= datetime.utcnow() - timedelta(hours=2),
        )
    )
    result = await db.execute(recent_stmt)
    if (result.scalar() or 0) > 0:
        return  # Avoid duplicate alerts

    alert = AnomalyAlert(
        tenant_id=tenant_id,
        alert_type=alert_type,
        severity=severity,
        metric_name=metric_name,
        current_value=current_value,
        baseline_value=baseline_value,
        threshold_percent=threshold_percent,
    )
    db.add(alert)
    await db.commit()
    logger.warning(
        f"Anomaly alert created: tenant={tenant_id}, type={alert_type}, "
        f"current={current_value}, baseline={baseline_value}"
    )
