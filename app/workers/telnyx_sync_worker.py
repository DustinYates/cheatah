"""Telnyx sync worker for detecting data discrepancies.

Runs hourly via Cloud Tasks. Compares local DB records against
the Telnyx API to catch missing calls, SMS, and stale delivery statuses.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.telnyx_sync_monitor import TelnyxSyncMonitorService
from app.persistence.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/check-telnyx-sync")
async def check_telnyx_sync_task(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Run Telnyx sync check for all enabled tenants.

    Called hourly by Cloud Tasks. Compares our DB against Telnyx API
    and records any discrepancies in telnyx_sync_results.
    """
    service = TelnyxSyncMonitorService()
    results = await service.run_all_tenants(db, lookback_hours=2)

    await db.commit()

    total_discrepancies = sum(r.total_discrepancies for r in results)
    total_errors = sum(len(r.errors) for r in results)

    summary = {
        "tenants_checked": len(results),
        "total_discrepancies": total_discrepancies,
        "total_errors": total_errors,
        "by_tenant": [
            {
                "tenant_id": r.tenant_id,
                "missing_calls": len(r.missing_calls),
                "missing_sms": len(r.missing_sms),
                "stale_deliveries": len(r.stale_deliveries),
                "errors": r.errors,
            }
            for r in results
            if r.total_discrepancies > 0 or r.errors
        ],
    }

    logger.info(
        f"[TELNYX-SYNC] Worker complete: {len(results)} tenants, "
        f"{total_discrepancies} discrepancies, {total_errors} errors"
    )

    return summary
