"""Lead scoring — compute a 0-100 score from signals stored on the lead.

The pure `compute_score` function reads from `Lead` fields and `lead.extra_data["score_signals"]`,
which signal handlers (SMS inbound, drip reply, intent detection, etc.) populate as events arrive.

Signal handlers should:
1. Mutate `extra_data["score_signals"]` (using `dict()` copy — see CLAUDE memory on JSON mutation)
2. Call `recompute_and_persist(session, lead)` to refresh the persisted score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.persistence.models.lead import Lead

logger = logging.getLogger(__name__)


# 4-band gradient for finer visual distinction at low scores.
HOT_THRESHOLD = 65
WARM_THRESHOLD = 40
COOL_THRESHOLD = 20

PLACEHOLDER_NAME_PREFIXES = ("Caller +", "SMS Contact +", "Caller+", "SMS Contact+")


@dataclass
class ScoreResult:
    score: int
    band: str
    breakdown: dict[str, int]


def _is_real_name(name: str | None) -> bool:
    if not name or not name.strip():
        return False
    return not any(name.startswith(p) for p in PLACEHOLDER_NAME_PREFIXES)


def _band_for(score: int) -> str:
    if score >= HOT_THRESHOLD:
        return "hot"
    if score >= WARM_THRESHOLD:
        return "warm"
    if score >= COOL_THRESHOLD:
        return "cool"
    return "cold"


def _signals(lead: Lead) -> dict[str, Any]:
    extra = lead.extra_data or {}
    return extra.get("score_signals") or {}


def compute_score(lead: Lead, *, now: datetime | None = None) -> ScoreResult:
    """Pure scoring function. No I/O.

    Reads lead fields plus `lead.extra_data["score_signals"]`. Signal handlers populate
    that sub-dict; this function just sums weighted contributions.
    """
    now = now or datetime.utcnow()
    breakdown: dict[str, int] = {}

    # Hard overrides
    if (lead.status or "").lower() == "dismissed":
        return ScoreResult(score=0, band="cold", breakdown={"dismissed": 0})
    if (lead.pipeline_stage or "") == "enrolled":
        return ScoreResult(score=100, band="hot", breakdown={"enrolled": 100})

    signals = _signals(lead)

    # Contact completeness (max 10) — having info matters less than engaging.
    completeness = 0
    if _is_real_name(lead.name):
        completeness += 4
    if lead.phone:
        completeness += 3
    if lead.email:
        completeness += 3
    if completeness:
        breakdown["completeness"] = completeness

    # Engagement (max 40) — chat volume is the strongest signal of intent.
    # More inbound messages → significantly stronger lead.
    engagement = 0
    inbound_count = signals.get("inbound_count") or 0
    # Graduated curve: each message worth ~4 points, capped at 25 (~6 msgs saturates).
    engagement += min(inbound_count * 4, 25)
    if signals.get("replied_to_outbound"):
        engagement += 10
    if signals.get("replied_within_1h"):
        engagement += 5
    if engagement:
        breakdown["engagement"] = engagement

    # Drip re-engagement (max 15) — Nth-touch reply scores higher.
    drip = 0
    drip_replies = signals.get("drip_replies") or []
    if drip_replies:
        deepest = max(drip_replies)
        if deepest >= 3:
            drip += 12
        elif deepest == 2:
            drip += 8
        else:
            drip += 4
    drip_sent = signals.get("drip_sent_count") or 0
    drip_decay = min(drip_sent - len(drip_replies), 5) if drip_sent > len(drip_replies) else 0
    if drip_decay > 0:
        drip -= drip_decay
        breakdown["drip_decay"] = -drip_decay
    drip = max(drip, -5)
    if drip > 0:
        breakdown["drip_engagement"] = drip

    # Intent (max 30)
    intent = 0
    if signals.get("high_intent"):
        intent += 18
    max_conf = signals.get("max_enrollment_confidence") or 0.0
    if max_conf >= 0.5:
        intent += 8
    intents = set(signals.get("intents") or [])
    if intents & {"pricing", "scheduling"}:
        intent += 4
    if intent:
        breakdown["intent"] = intent

    # Pipeline progress (max 25) — bumped so contacted/interested leads aren't unfairly cold.
    pipeline = 0
    stage = (lead.pipeline_stage or "").lower()
    if stage == "registered":
        pipeline = 25
    elif stage == "interested":
        pipeline = 18
    elif stage == "contacted":
        pipeline = 10
    if pipeline:
        breakdown["pipeline"] = pipeline

    # Recency (max +5, min -5)
    recency = 0
    if lead.updated_at:
        age = now - lead.updated_at
        if age <= timedelta(hours=24):
            recency = 5
        elif age <= timedelta(days=7):
            recency = 2
        elif age > timedelta(days=30):
            recency = -5
    if recency:
        breakdown["recency"] = recency

    score = completeness + engagement + drip + intent + pipeline + recency
    score = max(0, min(100, score))

    return ScoreResult(score=score, band=_band_for(score), breakdown=breakdown)


async def recompute_and_persist(session: AsyncSession, lead: Lead) -> ScoreResult:
    """Recompute and write back score, band, and timestamp. Caller commits.

    Live call sites (signal handlers reacting to actual activity) want
    `updated_at` to bump — that's the correct behavior since something just
    happened. For backfill / batch recompute that should NOT lie about
    last-activity time, use `recompute_quietly`.
    """
    result = compute_score(lead)
    lead.score = result.score
    lead.score_band = result.band
    lead.score_updated_at = datetime.utcnow()
    return result


async def recompute_quietly(session: AsyncSession, lead: Lead) -> ScoreResult:
    """Recompute and write back score WITHOUT bumping `updated_at`.

    Uses a raw UPDATE that includes `updated_at=lead.updated_at` so SQLAlchemy's
    `onupdate=datetime.utcnow` doesn't fire. Use this for backfill or any batch
    recompute where the lead hasn't actually had new activity.
    """
    result = compute_score(lead)
    extra_data_value = lead.extra_data
    await session.execute(
        sa_update(Lead)
        .where(Lead.id == lead.id)
        .values(
            score=result.score,
            score_band=result.band,
            score_updated_at=datetime.utcnow(),
            updated_at=lead.updated_at,
            extra_data=extra_data_value,
        )
    )
    # Sync the in-memory model so callers see the new values.
    lead.score = result.score
    lead.score_band = result.band
    return result


def record_signal(lead: Lead, **updates: Any) -> None:
    """Merge signal updates into `lead.extra_data["score_signals"]`.

    Special-case keys:
      - `channel`: str — appended to channels_used set
      - `intent`: str — appended to intents set
      - `drip_reply_touch`: int — appended to drip_replies list (deduped)
      - `inbound_message`: bool — increments inbound_count
      - `drip_sent`: bool — increments drip_sent_count
      - `enrollment_confidence`: float — bubbles up to max_enrollment_confidence

    Other kwargs are set directly (e.g. `replied_to_outbound=True`, `high_intent=True`).

    Important: rebuilds extra_data as a new dict so SQLAlchemy detects the change
    (see CLAUDE memory on JSON mutation).
    """
    extra = dict(lead.extra_data or {})
    signals = dict(extra.get("score_signals") or {})

    if updates.pop("inbound_message", False):
        signals["inbound_count"] = (signals.get("inbound_count") or 0) + 1
    if updates.pop("drip_sent", False):
        signals["drip_sent_count"] = (signals.get("drip_sent_count") or 0) + 1

    channel = updates.pop("channel", None)
    if channel:
        channels = list(signals.get("channels_used") or [])
        if channel not in channels:
            channels.append(channel)
        signals["channels_used"] = channels

    intent = updates.pop("intent", None)
    if intent:
        intents = list(signals.get("intents") or [])
        if intent not in intents:
            intents.append(intent)
        signals["intents"] = intents

    touch = updates.pop("drip_reply_touch", None)
    if touch is not None:
        replies = list(signals.get("drip_replies") or [])
        if touch not in replies:
            replies.append(int(touch))
        signals["drip_replies"] = replies

    conf = updates.pop("enrollment_confidence", None)
    if conf is not None:
        prev = signals.get("max_enrollment_confidence") or 0.0
        signals["max_enrollment_confidence"] = max(prev, float(conf))

    for k, v in updates.items():
        signals[k] = v

    extra["score_signals"] = signals
    lead.extra_data = extra
    flag_modified(lead, "extra_data")
