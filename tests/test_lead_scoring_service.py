"""Unit tests for the pure compute_score function."""

from datetime import datetime, timedelta

from app.domain.services.lead_scoring_service import (
    compute_score,
    record_signal,
)
from app.persistence.models.lead import Lead


def _lead(**kwargs) -> Lead:
    base = dict(
        tenant_id=1,
        name=None,
        email=None,
        phone=None,
        status="new",
        pipeline_stage="new_lead",
        extra_data=None,
        updated_at=datetime.utcnow(),
    )
    base.update(kwargs)
    return Lead(**base)


def test_empty_lead_is_cold():
    result = compute_score(_lead(updated_at=datetime.utcnow() - timedelta(days=60)))
    assert result.band == "cold"
    assert result.score <= 5


def test_dismissed_snaps_to_zero():
    lead = _lead(name="Real Name", email="x@y.com", phone="+15551234567", status="dismissed")
    assert compute_score(lead).score == 0


def test_enrolled_snaps_to_hot():
    lead = _lead(pipeline_stage="enrolled")
    result = compute_score(lead)
    assert result.score == 100
    assert result.band == "hot"


def test_placeholder_name_does_not_count():
    real = compute_score(_lead(name="Jane Doe")).breakdown.get("completeness", 0)
    placeholder = compute_score(_lead(name="Caller +12815551234")).breakdown.get(
        "completeness", 0
    )
    assert real > placeholder


def test_high_intent_pushes_to_warm_or_hot():
    lead = _lead(
        name="Jane",
        phone="+15551234567",
        email="j@x.com",
        pipeline_stage="contacted",
        extra_data={
            "score_signals": {
                "high_intent": True,
                "max_enrollment_confidence": 0.8,
                "intents": ["pricing"],
                "replied_to_outbound": True,
                "inbound_count": 4,
            }
        },
    )
    result = compute_score(lead)
    assert result.band in ("warm", "hot")
    assert result.score >= 70


def test_drip_third_touch_reply_scores_higher_than_first():
    base_signals = lambda touch: {
        "score_signals": {"drip_replies": [touch], "drip_sent_count": touch}
    }
    first = compute_score(_lead(extra_data=base_signals(1))).score
    third = compute_score(_lead(extra_data=base_signals(3))).score
    assert third > first


def test_drip_decay_for_unanswered_touches():
    lead = _lead(
        extra_data={"score_signals": {"drip_sent_count": 4, "drip_replies": []}}
    )
    bd = compute_score(lead).breakdown
    assert bd.get("drip_decay", 0) < 0


def test_record_signal_increments_counters():
    lead = _lead()
    record_signal(lead, inbound_message=True, channel="sms", replied_to_outbound=True)
    record_signal(lead, inbound_message=True, channel="email")
    signals = lead.extra_data["score_signals"]
    assert signals["inbound_count"] == 2
    assert set(signals["channels_used"]) == {"sms", "email"}
    assert signals["replied_to_outbound"] is True


def test_record_signal_dedupes_drip_touches():
    lead = _lead()
    record_signal(lead, drip_reply_touch=2)
    record_signal(lead, drip_reply_touch=2)
    record_signal(lead, drip_reply_touch=3)
    assert sorted(lead.extra_data["score_signals"]["drip_replies"]) == [2, 3]


def test_enrollment_confidence_takes_max():
    lead = _lead()
    record_signal(lead, enrollment_confidence=0.3)
    record_signal(lead, enrollment_confidence=0.7)
    record_signal(lead, enrollment_confidence=0.5)
    assert lead.extra_data["score_signals"]["max_enrollment_confidence"] == 0.7


def test_recency_old_lead_decays():
    fresh = compute_score(_lead(updated_at=datetime.utcnow())).breakdown.get("recency", 0)
    stale = compute_score(
        _lead(updated_at=datetime.utcnow() - timedelta(days=45))
    ).breakdown.get("recency", 0)
    assert fresh > 0 and stale < 0


def test_score_clamped_to_0_100():
    lead = _lead(
        name="J",
        email="j@x.com",
        phone="+15551234567",
        pipeline_stage="registered",
        extra_data={
            "score_signals": {
                "high_intent": True,
                "max_enrollment_confidence": 1.0,
                "intents": ["pricing", "scheduling"],
                "replied_to_outbound": True,
                "replied_within_1h": True,
                "inbound_count": 10,
                "channels_used": ["sms", "email", "chat"],
                "drip_replies": [1, 2, 3],
                "drip_sent_count": 3,
            }
        },
    )
    assert 0 <= compute_score(lead).score <= 100
