"""SMS burst detection periodic scanner.

Runs every 15 minutes via Cloud Tasks. Scans recent outbound SMS for
burst patterns that may have been missed by the real-time detector.
Auto-resolves stale incidents.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.sms_burst_detector import SmsBurstDetector
from app.persistence.database import get_db
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.sms_burst_incident import SmsBurstIncident
from app.persistence.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/scan-sms-bursts")
async def scan_sms_bursts_task(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Scan for SMS burst patterns and auto-resolve stale incidents.

    Called every 15 minutes by Cloud Tasks.
    """
    now = datetime.utcnow()
    scan_window = now - timedelta(minutes=30)
    stale_cutoff = now - timedelta(hours=2)

    # Get active tenants
    tenant_stmt = select(Tenant.id).where(Tenant.is_active.is_(True))
    tenant_result = await db.execute(tenant_stmt)
    tenant_ids = [r[0] for r in tenant_result.all()]

    new_incidents = 0
    auto_resolved = 0
    errors = 0

    for tenant_id in tenant_ids:
        try:
            n = await _scan_tenant(db, tenant_id, scan_window, now)
            new_incidents += n
        except Exception as e:
            logger.error(f"Burst scan failed for tenant {tenant_id}: {e}", exc_info=True)
            errors += 1

    # Auto-resolve stale incidents across all tenants
    auto_resolved = await _auto_resolve_stale(db, stale_cutoff)

    logger.info(
        f"Burst scan complete: {new_incidents} new incidents, "
        f"{auto_resolved} auto-resolved, {errors} errors"
    )
    return {
        "new_incidents": new_incidents,
        "auto_resolved": auto_resolved,
        "errors": errors,
    }


async def _scan_tenant(
    db: AsyncSession,
    tenant_id: int,
    scan_start: datetime,
    scan_end: datetime,
) -> int:
    """Scan a single tenant for burst patterns."""
    # Find phone numbers with multiple outbound SMS in the scan window
    stmt = (
        select(
            Conversation.phone_number,
            func.count(Message.id).label("msg_count"),
        )
        .join(Message, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.channel == "sms",
            Conversation.phone_number.isnot(None),
            Message.role == "assistant",
            Message.created_at >= scan_start,
            Message.created_at < scan_end,
        )
        .group_by(Conversation.phone_number)
        .having(func.count(Message.id) >= 3)  # Minimum threshold
    )
    result = await db.execute(stmt)
    candidates = result.all()

    new_count = 0
    detector = SmsBurstDetector(db)

    for phone_number, msg_count in candidates:
        # Check if there's already an active incident for this number
        existing_stmt = (
            select(func.count())
            .select_from(SmsBurstIncident)
            .where(
                SmsBurstIncident.tenant_id == tenant_id,
                SmsBurstIncident.to_number == phone_number,
                SmsBurstIncident.status == "active",
                SmsBurstIncident.detected_at >= scan_start,
            )
        )
        existing_result = await db.execute(existing_stmt)
        if (existing_result.scalar() or 0) > 0:
            continue  # Already tracked

        # Run full burst check (will create incident if pattern confirmed)
        check_result = await detector.check_outbound_sms(
            tenant_id=tenant_id,
            to_number=phone_number,
            message_content="",  # Content checked from DB in _check_via_database
        )
        if check_result.is_burst:
            new_count += 1

    return new_count


async def _auto_resolve_stale(db: AsyncSession, cutoff: datetime) -> int:
    """Auto-resolve active incidents with no new messages in 2+ hours."""
    stmt = (
        select(SmsBurstIncident)
        .where(
            SmsBurstIncident.status == "active",
            SmsBurstIncident.last_message_at < cutoff,
        )
    )
    result = await db.execute(stmt)
    stale = list(result.scalars().all())

    now = datetime.utcnow()
    for incident in stale:
        incident.status = "resolved"
        incident.resolved_at = now
        incident.notes = "Auto-resolved: no new messages in 2+ hours"

    if stale:
        await db.commit()
        logger.info(f"Auto-resolved {len(stale)} stale burst incidents")

    return len(stale)
