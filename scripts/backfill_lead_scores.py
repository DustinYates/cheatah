"""Backfill score, score_band, and score_updated_at for all existing leads.

Derives `score_signals` from existing data so historical leads aren't unfairly
scored as cold. Sources used:
  - lead.extra_data: sources, voice_calls, drip_enrolled, drip_enrollment_ids,
    linked_conversations
  - Conversations linked via lead.conversation_id and extra_data.linked_conversations
    → channel + inbound_count from Message rows where role='user'
  - DripEnrollment rows → drip_sent_count (max current_step) and drip_replies
    (steps where the lead was in 'responded' status)
  - EmailConversation linked to lead → adds 'email' channel

Idempotent — re-running just refreshes scores from current state.

Usage:
    uv run python scripts/backfill_lead_scores.py [--dry-run] [--tenant-id N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import func, select

from app.domain.services.lead_scoring_service import (
    record_signal,
    recompute_quietly,
)
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.drip_campaign import DripEnrollment
from app.persistence.models.lead import Lead
from app.persistence.models.tenant_email_config import EmailConversation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


SOURCE_TO_CHANNEL = {
    "voice_call": "voice",
    "sms": "sms",
    "email": "email",
    "chatbot": "chat",
    "chat": "chat",
    "web_form": "web",
}


def _conv_channel_to_score_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    c = channel.lower()
    if c in ("sms", "telnyx_sms"):
        return "sms"
    if c in ("voice", "telnyx_voice"):
        return "voice"
    if c in ("web", "chat"):
        return "chat"
    if c == "email":
        return "email"
    return None


async def _gather_message_signals(
    db, conversation_ids: list[int]
) -> tuple[int, set[str], bool]:
    """Returns (inbound_count, channels_set, replied_to_outbound)."""
    if not conversation_ids:
        return 0, set(), False

    user_count_stmt = (
        select(Message.conversation_id, func.count(Message.id))
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.role == "user",
        )
        .group_by(Message.conversation_id)
    )
    result = await db.execute(user_count_stmt)
    user_counts: dict[int, int] = {row[0]: row[1] for row in result.all()}
    inbound_count = sum(user_counts.values())

    assistant_stmt = (
        select(Message.conversation_id)
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.role == "assistant",
        )
        .distinct()
    )
    assistant_convs = {row[0] for row in (await db.execute(assistant_stmt)).all()}
    replied_to_outbound = any(
        cid in user_counts and cid in assistant_convs for cid in conversation_ids
    )

    chan_stmt = (
        select(Conversation.id, Conversation.channel)
        .where(Conversation.id.in_(conversation_ids))
    )
    chan_rows = (await db.execute(chan_stmt)).all()
    channels: set[str] = set()
    for _, ch in chan_rows:
        mapped = _conv_channel_to_score_channel(ch)
        if mapped:
            channels.add(mapped)

    return inbound_count, channels, replied_to_outbound


async def backfill(dry_run: bool = False, tenant_filter: int | None = None) -> None:
    band_counts: dict[str, int] = defaultdict(int)
    total = 0

    async with AsyncSessionLocal() as db:
        stmt = select(Lead)
        if tenant_filter is not None:
            stmt = stmt.where(Lead.tenant_id == tenant_filter)

        leads = (await db.execute(stmt)).scalars().all()
        logger.info(f"Scoring {len(leads)} leads (dry_run={dry_run})")

        # Bulk-load drip enrollments per lead (one query, then index by lead_id).
        lead_ids = [l.id for l in leads]
        drip_by_lead: dict[int, list[DripEnrollment]] = defaultdict(list)
        if lead_ids:
            drip_rows = (
                await db.execute(
                    select(DripEnrollment).where(DripEnrollment.lead_id.in_(lead_ids))
                )
            ).scalars().all()
            for e in drip_rows:
                drip_by_lead[e.lead_id].append(e)

        # Bulk-check email conversations.
        email_lead_ids: set[int] = set()
        if lead_ids:
            email_rows = (
                await db.execute(
                    select(EmailConversation.lead_id)
                    .where(EmailConversation.lead_id.in_(lead_ids))
                    .distinct()
                )
            ).all()
            email_lead_ids = {r[0] for r in email_rows if r[0] is not None}

        for lead in leads:
            extra = lead.extra_data or {}

            # Channels from extra_data.sources / source
            channels: set[str] = set()
            for s in extra.get("sources") or []:
                ch = SOURCE_TO_CHANNEL.get(s)
                if ch:
                    channels.add(ch)
            primary_source = extra.get("source")
            if primary_source and primary_source in SOURCE_TO_CHANNEL:
                channels.add(SOURCE_TO_CHANNEL[primary_source])

            # Voice calls in extra_data
            voice_calls = extra.get("voice_calls") or []
            if voice_calls:
                channels.add("voice")

            # Email conversation linked
            if lead.id in email_lead_ids:
                channels.add("email")

            # Conversation IDs to scan for messages
            conv_ids: list[int] = []
            if lead.conversation_id:
                conv_ids.append(lead.conversation_id)
            for cid in extra.get("linked_conversations") or []:
                if isinstance(cid, int) and cid not in conv_ids:
                    conv_ids.append(cid)

            inbound_count, msg_channels, replied = await _gather_message_signals(
                db, conv_ids
            )
            channels |= msg_channels

            # Voice call count adds to inbound_count too (each call is an engagement event)
            inbound_count += len(voice_calls)

            # Record channel diversity
            for ch in channels:
                record_signal(lead, channel=ch)

            # Inbound count — add as a single bulk update.
            if inbound_count > 0:
                # Use record_signal repeatedly to leverage its counter logic.
                # Simpler: write the field directly.
                extra_now = dict(lead.extra_data or {})
                signals_now = dict(extra_now.get("score_signals") or {})
                signals_now["inbound_count"] = inbound_count
                if replied:
                    signals_now["replied_to_outbound"] = True
                extra_now["score_signals"] = signals_now
                lead.extra_data = extra_now

            # Drip signals
            enrollments = drip_by_lead.get(lead.id, [])
            if enrollments:
                deepest = max((e.current_step or 0) for e in enrollments)
                if deepest > 0:
                    extra_now = dict(lead.extra_data or {})
                    signals_now = dict(extra_now.get("score_signals") or {})
                    signals_now["drip_sent_count"] = deepest
                    if any(e.status == "responded" for e in enrollments):
                        # We don't know which specific touch they replied to;
                        # use the deepest step as a conservative proxy.
                        signals_now["drip_replies"] = [deepest]
                    extra_now["score_signals"] = signals_now
                    lead.extra_data = extra_now

            score_result = await recompute_quietly(db, lead)
            band_counts[score_result.band] += 1
            total += 1
            if total % 250 == 0:
                logger.info(f"  ... {total} processed")

        if dry_run:
            await db.rollback()
            logger.info(f"DRY RUN — rolled back. Would have scored {total} leads.")
        else:
            await db.commit()
            logger.info(f"Committed scores for {total} leads.")

    logger.info(f"Distribution: {dict(band_counts)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant-id", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run, tenant_filter=args.tenant_id))


if __name__ == "__main__":
    main()
