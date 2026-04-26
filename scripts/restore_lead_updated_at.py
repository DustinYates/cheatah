"""Restore each lead's `updated_at` to its real last-activity time.

Background: an earlier run of `backfill_lead_scores.py` used the ORM to write
score columns, which fired SQLAlchemy's `onupdate=datetime.utcnow` on the
`updated_at` column for ~1,400 leads — making old test leads appear as if
they were active "today" on the dashboard.

This script computes the real last-activity time per lead from:
  1. max(message.created_at) across the lead's conversation + linked_conversations
  2. max voice_call.call_date in extra_data.voice_calls
  3. lead.created_at (fallback)

It then writes that value to lead.updated_at via raw UPDATE, preserving
score columns. Idempotent.

Usage:
    uv run python scripts/restore_lead_updated_at.py [--dry-run] [--tenant-id N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select, update as sa_update

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.conversation import Message
from app.persistence.models.lead import Lead

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_voice_call_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


async def restore(dry_run: bool = False, tenant_filter: int | None = None) -> None:
    changed = 0
    unchanged = 0

    async with AsyncSessionLocal() as db:
        stmt = select(Lead)
        if tenant_filter is not None:
            stmt = stmt.where(Lead.tenant_id == tenant_filter)
        leads = (await db.execute(stmt)).scalars().all()
        logger.info(f"Restoring updated_at for {len(leads)} leads (dry_run={dry_run})")

        # Bulk-collect conversation IDs across all leads.
        conv_to_lead: dict[int, list[int]] = defaultdict(list)
        for lead in leads:
            extra = lead.extra_data or {}
            if lead.conversation_id:
                conv_to_lead[lead.conversation_id].append(lead.id)
            for cid in extra.get("linked_conversations") or []:
                if isinstance(cid, int):
                    conv_to_lead[cid].append(lead.id)

        # One query: max(created_at) per conversation_id.
        conv_max: dict[int, datetime] = {}
        if conv_to_lead:
            rows = (
                await db.execute(
                    select(Message.conversation_id, func.max(Message.created_at))
                    .where(Message.conversation_id.in_(list(conv_to_lead.keys())))
                    .group_by(Message.conversation_id)
                )
            ).all()
            conv_max = {cid: ts for cid, ts in rows if ts is not None}

        for lead in leads:
            extra = lead.extra_data or {}
            candidates: list[datetime] = []

            # Messages from conversation(s)
            cids: list[int] = []
            if lead.conversation_id:
                cids.append(lead.conversation_id)
            for cid in extra.get("linked_conversations") or []:
                if isinstance(cid, int) and cid not in cids:
                    cids.append(cid)
            for cid in cids:
                ts = conv_max.get(cid)
                if ts:
                    candidates.append(ts)

            # Voice calls
            for vc in extra.get("voice_calls") or []:
                ts = _parse_voice_call_date(vc.get("call_date"))
                if ts:
                    candidates.append(ts)

            # Fallback to created_at if nothing else
            real_updated_at = max(candidates) if candidates else lead.created_at
            if real_updated_at is None:
                unchanged += 1
                continue

            # Only rewrite if it differs by more than 1 second
            if (
                lead.updated_at
                and abs((lead.updated_at - real_updated_at).total_seconds()) < 1
            ):
                unchanged += 1
                continue

            await db.execute(
                sa_update(Lead)
                .where(Lead.id == lead.id)
                .values(updated_at=real_updated_at)
            )
            changed += 1

        if dry_run:
            await db.rollback()
            logger.info(f"DRY RUN: would update {changed}, leave {unchanged}")
        else:
            await db.commit()
            logger.info(f"Restored: {changed} updated, {unchanged} unchanged")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant-id", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(restore(dry_run=args.dry_run, tenant_filter=args.tenant_id))


if __name__ == "__main__":
    main()
