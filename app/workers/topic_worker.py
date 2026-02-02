"""Topic classification worker.

Runs daily via Cloud Tasks. Classifies topics for recent conversations
that haven't been classified yet, populating conversations.topic for
the analytics histogram.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.topic_classifier import TopicClassifier
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()

# Mapping from CallSummary.intent to unified topic taxonomy
INTENT_TO_TOPIC = {
    "pricing_info": "pricing",
    "booking_request": "scheduling",
    "hours_location": "hours_location",
    "support_request": "support_request",
    "wrong_number": "wrong_number",
    "general_inquiry": "general_inquiry",
}


@router.post("/compute-topics")
async def compute_topics_task(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Classify topics for recent unclassified conversations.

    Called daily by Cloud Tasks. Processes conversations from the last
    7 days that don't have a topic yet.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)

    # Get active tenants
    tenant_stmt = select(Tenant.id).where(Tenant.is_active.is_(True))
    tenant_result = await db.execute(tenant_stmt)
    tenant_ids = [r[0] for r in tenant_result.all()]

    total_classified = 0
    errors = 0

    for tenant_id in tenant_ids:
        try:
            classified = await _classify_for_tenant(db, tenant_id, cutoff)
            total_classified += classified
        except Exception as e:
            logger.error(f"Topic classification failed for tenant {tenant_id}: {e}", exc_info=True)
            errors += 1

    logger.info(f"Topic worker complete: {total_classified} conversations classified, {errors} errors")
    return {"total_classified": total_classified, "errors": errors}


async def _classify_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    cutoff: datetime,
) -> int:
    """Classify topics for unclassified conversations of a single tenant."""
    # Find unclassified conversations with at least 1 user message
    conv_with_messages = (
        select(Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= cutoff,
            Conversation.topic.is_(None),
        )
        .order_by(Conversation.created_at.desc())
        .limit(500)
    )
    result = await db.execute(conv_with_messages)
    conversation_ids = [r[0] for r in result.all()]

    if not conversation_ids:
        return 0

    classified_count = 0
    classifier = TopicClassifier()

    # Process in batches of 50
    for i in range(0, len(conversation_ids), 50):
        batch_ids = conversation_ids[i : i + 50]

        for conv_id in batch_ids:
            topic = await _classify_single(db, conv_id, tenant_id, classifier)
            if topic:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conv_id)
                    .values(topic=topic)
                )
                classified_count += 1

        await db.commit()

    logger.info(f"Topics classified for tenant {tenant_id}: {classified_count} conversations")
    return classified_count


async def _classify_single(
    db: AsyncSession,
    conv_id: int,
    tenant_id: int,
    classifier: TopicClassifier,
) -> str | None:
    """Classify a single conversation's topic.

    For voice conversations, maps from CallSummary.intent.
    For other channels, uses keyword-based TopicClassifier.
    """
    # Get conversation channel
    conv_result = await db.execute(
        select(Conversation.channel, Conversation.phone_number, Conversation.created_at)
        .where(Conversation.id == conv_id)
    )
    conv_row = conv_result.one_or_none()
    if not conv_row:
        return None

    channel, phone_number, created_at = conv_row

    # For voice conversations, try to map from CallSummary.intent
    if channel == "voice" and phone_number:
        call_stmt = (
            select(CallSummary.intent)
            .join(Call, CallSummary.call_id == Call.id)
            .where(
                Call.tenant_id == tenant_id,
                Call.from_number == phone_number,
                Call.created_at >= created_at - timedelta(minutes=5),
                Call.created_at <= created_at + timedelta(minutes=30),
                CallSummary.intent.isnot(None),
            )
            .order_by(Call.created_at.desc())
            .limit(1)
        )
        call_result = await db.execute(call_stmt)
        intent_row = call_result.one_or_none()
        if intent_row and intent_row[0]:
            return INTENT_TO_TOPIC.get(intent_row[0], intent_row[0])

    # For all channels, use keyword classifier on user messages
    msg_stmt = (
        select(Message.content)
        .where(
            Message.conversation_id == conv_id,
            Message.role == "user",
        )
        .order_by(Message.sequence_number)
        .limit(20)  # Cap at 20 messages to avoid processing huge conversations
    )
    msg_result = await db.execute(msg_stmt)
    messages = [r[0] for r in msg_result.all() if r[0]]

    if not messages:
        return None

    result = classifier.classify(messages)
    return result.topic
