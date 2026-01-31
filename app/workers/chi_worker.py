"""CHI computation worker.

Runs daily via Cloud Tasks. Computes Customer Happiness Index scores
for recent conversations that haven't been scored yet.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.chi_service import CHIService
from app.persistence.database import get_db
from app.persistence.models.conversation import Conversation
from app.persistence.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/compute-chi")
async def compute_chi_task(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Compute CHI scores for recent unscored conversations.

    Called daily by Cloud Tasks. Processes conversations from the last
    7 days that don't have a CHI score yet.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)

    # Get active tenants
    tenant_stmt = select(Tenant.id).where(Tenant.is_active.is_(True))
    tenant_result = await db.execute(tenant_stmt)
    tenant_ids = [r[0] for r in tenant_result.all()]

    total_scored = 0
    errors = 0

    for tenant_id in tenant_ids:
        try:
            scored = await _compute_for_tenant(db, tenant_id, cutoff)
            total_scored += scored
        except Exception as e:
            logger.error(f"CHI computation failed for tenant {tenant_id}: {e}", exc_info=True)
            errors += 1

    logger.info(f"CHI worker complete: {total_scored} conversations scored, {errors} errors")
    return {"total_scored": total_scored, "errors": errors}


async def _compute_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    cutoff: datetime,
) -> int:
    """Compute CHI for unscored conversations of a single tenant."""
    # Find unscored conversations with at least 2 messages
    stmt = (
        select(Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= cutoff,
            Conversation.chi_score.is_(None),
        )
        .order_by(Conversation.created_at.desc())
        .limit(500)  # Process max 500 per tenant per run
    )
    result = await db.execute(stmt)
    conversation_ids = [r[0] for r in result.all()]

    if not conversation_ids:
        return 0

    chi_service = CHIService(db)
    results = await chi_service.batch_compute(conversation_ids, batch_size=50)

    logger.info(
        f"CHI computed for tenant {tenant_id}: {len(results)} conversations"
    )
    return len(results)
