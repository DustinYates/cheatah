"""Backfill `sent_assets` rows for registration links the AI inlined into SMS replies.

Tool-based sends (`send_link` / `send_registration_link`) write to `sent_assets`.
The Telnyx AI agent often skips the tool and types the registration URL directly
into a chat reply, which never gets recorded — so the conversion dashboard
under-counts.

This script scans every assistant SMS message, detects an inline registration
URL, and inserts a `sent_assets` row keyed on (tenant_id, phone, asset_type).
The unique constraint guarantees idempotency: re-running is safe.

Usage:
    uv run python scripts/backfill_inline_sent_assets.py [--dry-run] [--tenant-id N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.phone import normalize_phone_for_dedup
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.sent_asset import SentAsset
from app.utils.registration_url_detector import find_registration_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(dry_run: bool = False, tenant_filter: int | None = None) -> None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(
                Message.id,
                Message.content,
                Message.created_at,
                Message.conversation_id,
                Conversation.tenant_id,
                Conversation.phone_number,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.channel == "sms",
                Message.role == "assistant",
                Message.content.op("~")(r"https?://"),
            )
            .order_by(Message.created_at.asc())
        )
        if tenant_filter is not None:
            stmt = stmt.where(Conversation.tenant_id == tenant_filter)

        rows = (await db.execute(stmt)).all()
        logger.info(f"Scanning {len(rows)} assistant SMS messages with URLs...")

        # earliest_per_key: (tenant_id, phone10) -> (sent_at, conversation_id, url)
        earliest_per_key: dict[tuple[int, str], tuple] = {}
        scanned_with_link = 0
        for r in rows:
            url = find_registration_url(r.content)
            if not url:
                continue
            scanned_with_link += 1
            if not r.phone_number:
                continue
            phone10 = normalize_phone_for_dedup(r.phone_number)
            if len(phone10) != 10:
                continue
            key = (r.tenant_id, phone10)
            if key not in earliest_per_key or r.created_at < earliest_per_key[key][0]:
                earliest_per_key[key] = (r.created_at, r.conversation_id, url)

        logger.info(
            f"Found {scanned_with_link} messages containing a registration URL "
            f"across {len(earliest_per_key)} unique (tenant, phone) pairs."
        )

        # Pre-load existing sent_assets so we can report what's actually new.
        tenant_ids = sorted({k[0] for k in earliest_per_key})
        existing_keys: set[tuple[int, str]] = set()
        if tenant_ids:
            existing_stmt = select(SentAsset.tenant_id, SentAsset.phone_normalized).where(
                SentAsset.tenant_id.in_(tenant_ids),
                SentAsset.asset_type == "registration_link",
            )
            for row in (await db.execute(existing_stmt)).all():
                existing_keys.add((row.tenant_id, row.phone_normalized))

        to_insert = [
            (tenant_id, phone10, sent_at, conv_id, url)
            for (tenant_id, phone10), (sent_at, conv_id, url) in earliest_per_key.items()
            if (tenant_id, phone10) not in existing_keys
        ]

        per_tenant_count: dict[int, int] = defaultdict(int)
        for tenant_id, _, _, _, _ in to_insert:
            per_tenant_count[tenant_id] += 1

        logger.info(f"Will insert {len(to_insert)} new sent_assets rows:")
        for tid in sorted(per_tenant_count):
            logger.info(f"  tenant_id={tid}: +{per_tenant_count[tid]}")

        if dry_run:
            logger.info("--dry-run: not writing.")
            return

        if not to_insert:
            logger.info("Nothing to insert. Done.")
            return

        # ON CONFLICT DO NOTHING in case the table was modified mid-run.
        for tenant_id, phone10, sent_at, conv_id, _url in to_insert:
            stmt = pg_insert(SentAsset).values(
                tenant_id=tenant_id,
                phone_normalized=phone10,
                asset_type="registration_link",
                sent_at=sent_at,
                conversation_id=conv_id,
            ).on_conflict_do_nothing(constraint="uq_sent_assets_tenant_phone_asset")
            await db.execute(stmt)
        await db.commit()
        logger.info(f"Inserted {len(to_insert)} rows.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write.")
    parser.add_argument("--tenant-id", type=int, help="Restrict to a single tenant.")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run, tenant_filter=args.tenant_id))


if __name__ == "__main__":
    main()
