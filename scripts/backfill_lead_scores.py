"""Backfill score, score_band, and score_updated_at for all existing leads.

Computes scoring from each lead's current state + extra_data["score_signals"].
Idempotent — re-running just refreshes scores.

Usage:
    uv run python scripts/backfill_lead_scores.py [--dry-run] [--tenant-id N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.domain.services.lead_scoring_service import recompute_and_persist
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.lead import Lead

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(dry_run: bool = False, tenant_filter: int | None = None) -> None:
    band_counts: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}
    total = 0

    async with AsyncSessionLocal() as db:
        stmt = select(Lead)
        if tenant_filter is not None:
            stmt = stmt.where(Lead.tenant_id == tenant_filter)

        result = await db.execute(stmt)
        leads = result.scalars().all()
        logger.info(f"Scoring {len(leads)} leads (dry_run={dry_run})")

        for lead in leads:
            score_result = await recompute_and_persist(db, lead)
            band_counts[score_result.band] = band_counts.get(score_result.band, 0) + 1
            total += 1
            if total % 500 == 0:
                logger.info(f"  ... {total} processed")

        if dry_run:
            await db.rollback()
            logger.info(f"DRY RUN — rolled back. Would have scored {total} leads.")
        else:
            await db.commit()
            logger.info(f"Committed scores for {total} leads.")

    logger.info(f"Distribution: {band_counts}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant-id", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run, tenant_filter=args.tenant_id))


if __name__ == "__main__":
    main()
