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

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.persistence.models.lead import Lead

logger = logging.getLogger(__name__)


HOT_THRESHOLD = 70
WARM_THRESHOLD = 40

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

    # Contact completeness (max 15)
    completeness = 0
    if _is_real_name(lead.name):
        completeness += 5
    if lead.phone:
        completeness += 5
    if lead.email:
        completeness += 5
    if completeness:
        breakdown["completeness"] = completeness

    # Engagement (max 30)
    engagement = 0
    if signals.get("replied_to_outbound"):
        engagement += 10
    if signals.get("replied_within_1h"):
        engagement += 5
    if (signals.get("inbound_count") or 0) >= 3:
        engagement += 10
    channels = set(signals.get("channels_used") or [])
    if len(channels) >= 2:
        engagement += 5
    if engagement:
        breakdown["engagement"] = engagement

    # Drip re-engagement (max 20) — Nth-touch reply scores higher
    drip = 0
    drip_replies = signals.get("drip_replies") or []
    if drip_replies:
        deepest = max(drip_replies)
        if deepest >= 3:
            drip += 15
        elif deepest == 2:
            drip += 10
        else:
            drip += 5
    drip_sent = signals.get("drip_sent_count") or 0
    drip_decay = min(drip_sent - len(drip_replies), 5) if drip_sent > len(drip_replies) else 0
    if drip_decay > 0:
        drip -= drip_decay
        breakdown["drip_decay"] = -drip_decay
    drip = max(drip, -5)
    if drip > 0:
        breakdown["drip_engagement"] = drip

    # Intent (max 35)
    intent = 0
    if signals.get("high_intent"):
        intent += 20
    max_conf = signals.get("max_enrollment_confidence") or 0.0
    if max_conf >= 0.5:
        intent += 10
    intents = set(signals.get("intents") or [])
    if intents & {"pricing", "scheduling"}:
        intent += 5
    if intent:
        breakdown["intent"] = intent

    # Pipeline progress (max 15)
    pipeline = 0
    stage = (lead.pipeline_stage or "").lower()
    if stage == "interested":
        pipeline = 10
    elif stage == "registered":
        pipeline = 15
    elif stage == "contacted":
        pipeline = 5
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
    """Recompute and write back score, band, and timestamp. Caller commits."""
    result = compute_score(lead)
    lead.score = result.score
    lead.score_band = result.band
    lead.score_updated_at = datetime.utcnow()
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
