"""Unit tests for manual drip-campaign enrollment.

Covers DripCampaignService.enroll_lead_manual (the dashboard-triggered path that
raises a user-facing ValueError per failure reason) and the shared
_create_and_schedule_enrollment helper. All external side effects — DB session,
repositories, Cloud Tasks scheduling, customer lookup — are mocked, so these
tests never touch the real database or send SMS.
"""

import types
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.drip_campaign_service import DripCampaignService
from app.settings import settings


def _lead(**kw):
    # class_code "Starfish" is a real infant-class token infer_audience reads
    # (-> "Child (under 3)" -> kids); matches the actual screenshot lead.
    defaults = dict(
        id=10,
        tenant_id=3,
        phone="+12815551234",
        name="Azim Aslam",
        extra_data={"class_code": "Starfish"},
        custom_tags=[],
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def _campaign(**kw):
    defaults = dict(
        id=1,
        campaign_type="kids",
        is_enabled=True,
        trigger_delay_minutes=60,
        steps=[types.SimpleNamespace(step_number=1, delay_minutes=10)],
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def _enrollment_stub(**kw):
    """A stand-in for the object _create_and_schedule_enrollment returns. Carries a
    truthy next_task_id so enroll_lead_manual's schedule-success check passes."""
    defaults = dict(id=1, campaign_id=1, next_task_id="task-1", next_step_at=object())
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def _fake_session(assign_id=555):
    """An AsyncMock session whose refresh() assigns a PK, like the real DB does."""
    session = AsyncMock()
    session.add = MagicMock()

    async def _refresh(obj):
        obj.id = assign_id

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


def _service(session=None):
    """A service whose repos are mocks; session defaults to a bare AsyncMock
    (unused on validation-only paths)."""
    svc = DripCampaignService(session or AsyncMock())
    svc.lead_repo = MagicMock()
    svc.lead_repo.get_by_id = AsyncMock()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_active_for_lead = AsyncMock(return_value=None)
    svc.enrollment_repo.get_for_campaign_and_lead = AsyncMock(return_value=None)
    svc.campaign_repo = MagicMock()
    svc.campaign_repo.get_by_type = AsyncMock()
    return svc


@pytest.fixture(autouse=True)
def _no_genai():
    """DripCampaignService.__init__ builds a DripMessageService, which eagerly
    constructs a Gemini client (needs GEMINI_API_KEY). We don't exercise messaging
    here, so stub it out for every service construction in this module."""
    with patch("app.domain.services.drip_campaign_service.DripMessageService"):
        yield


@pytest.fixture(autouse=True)
def customer_repo():
    """Patch CustomerRepository (imported lazily inside the service); defaults to
    'no existing customer'. Tests that exercise the customer guard override it."""
    with patch(
        "app.persistence.repositories.customer_repository.CustomerRepository"
    ) as M:
        inst = M.return_value
        inst.get_by_phone = AsyncMock(return_value=None)
        yield inst


# ── Validation branches (each must raise a distinct, user-facing message) ──────

@pytest.mark.asyncio
async def test_lead_not_found():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="Lead not found"):
        await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_no_phone():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead(phone=None))
    with pytest.raises(ValueError, match="no phone number"):
        await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_already_enrolled():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    svc.enrollment_repo.get_active_for_lead = AsyncMock(
        return_value=types.SimpleNamespace(id=99)
    )
    with pytest.raises(ValueError, match="already enrolled"):
        await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_customer_match_names_the_customer(customer_repo):
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    customer_repo.get_by_phone = AsyncMock(
        return_value=types.SimpleNamespace(id=5, name="Jane Doe")
    )
    with pytest.raises(ValueError, match=r"existing customer \(Jane Doe\)"):
        await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_campaign_not_configured():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    svc.campaign_repo.get_by_type = AsyncMock(return_value=None)
    with patch.object(DripCampaignService, "detect_campaign_type", return_value="kids"):
        with pytest.raises(ValueError, match="No 'kids' drip campaign is configured"):
            await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_campaign_disabled():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign(is_enabled=False))
    with patch.object(DripCampaignService, "detect_campaign_type", return_value="kids"):
        with pytest.raises(ValueError, match="disabled"):
            await svc.enroll_lead_manual(3, 10)


@pytest.mark.asyncio
async def test_campaign_no_steps():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign(steps=[]))
    with patch.object(DripCampaignService, "detect_campaign_type", return_value="kids"):
        with pytest.raises(ValueError, match="no steps configured"):
            await svc.enroll_lead_manual(3, 10)


# ── Happy path + campaign-type selection ──────────────────────────────────────

@pytest.mark.asyncio
async def test_happy_path_auto_detects_type_and_builds_context():
    svc = _service()
    lead = _lead()
    svc.lead_repo.get_by_id = AsyncMock(return_value=lead)
    campaign = _campaign()
    svc.campaign_repo.get_by_type = AsyncMock(return_value=campaign)
    sentinel = _enrollment_stub()
    svc._create_and_schedule_enrollment = AsyncMock(return_value=sentinel)

    with patch.object(
        DripCampaignService, "detect_campaign_type", return_value="kids"
    ) as mock_detect:
        result = await svc.enroll_lead_manual(3, 10)  # no override → auto-detect

    assert result is sentinel
    mock_detect.assert_called_once()
    svc.campaign_repo.get_by_type.assert_awaited_once_with(3, "kids")

    passed_campaign, passed_lead, context = svc._create_and_schedule_enrollment.call_args.args
    assert passed_campaign is campaign
    assert passed_lead is lead
    assert context["first_name"] == "Azim"   # first token of lead.name
    assert context["source"] == "manual_enroll"


@pytest.mark.asyncio
async def test_explicit_campaign_type_skips_auto_detect():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead())
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign(campaign_type="adults"))
    svc._create_and_schedule_enrollment = AsyncMock(return_value=_enrollment_stub(campaign_id=2))

    with patch.object(DripCampaignService, "detect_campaign_type") as mock_detect:
        await svc.enroll_lead_manual(3, 10, campaign_type="adults")

    mock_detect.assert_not_called()
    svc.campaign_repo.get_by_type.assert_awaited_once_with(3, "adults")


@pytest.mark.asyncio
async def test_first_name_none_when_lead_unnamed():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead(name=None))
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign())
    svc._create_and_schedule_enrollment = AsyncMock(return_value=_enrollment_stub())
    with patch.object(DripCampaignService, "detect_campaign_type", return_value="kids"):
        await svc.enroll_lead_manual(3, 10)
    _, _, context = svc._create_and_schedule_enrollment.call_args.args
    assert context["first_name"] is None


# ── Shared create + schedule helper ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_schedule_flags_lead_and_schedules_step1():
    session = AsyncMock()
    session.add = MagicMock()

    async def _refresh(obj):
        obj.id = 555  # simulate DB-assigned PK after the first commit

    session.refresh = AsyncMock(side_effect=_refresh)

    svc = DripCampaignService(session)
    svc._schedule_step = AsyncMock(return_value="task-abc")  # no real Cloud Task

    lead = _lead(extra_data={})
    campaign = _campaign()  # step 1 delay = 10

    enrollment = await svc._create_and_schedule_enrollment(
        campaign, lead, {"first_name": "Azim", "source": "manual_enroll"}
    )

    # enrollment created correctly
    assert enrollment.status == "active"
    assert enrollment.current_step == 0
    assert enrollment.tenant_id == lead.tenant_id
    assert enrollment.campaign_id == campaign.id
    assert enrollment.lead_id == lead.id

    # lead flagged + enrollment id recorded (new dict assigned for change detection)
    assert lead.extra_data["drip_enrolled"] is True
    assert 555 in lead.extra_data["drip_enrollment_ids"]

    # scheduled using step 1's own delay, not trigger_delay_minutes
    svc._schedule_step.assert_awaited_once_with(enrollment, 10)

    # three commits: flag, append-id, persist-schedule
    assert session.commit.await_count == 3


@pytest.mark.asyncio
async def test_create_and_schedule_falls_back_to_trigger_delay_without_step1():
    session = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", 1))

    svc = DripCampaignService(session)
    svc._schedule_step = AsyncMock(return_value="task-xyz")

    # No step_number==1 → falls back to trigger_delay_minutes (60)
    campaign = _campaign(steps=[types.SimpleNamespace(step_number=2, delay_minutes=99)])
    await svc._create_and_schedule_enrollment(campaign, _lead(extra_data={}), {})

    svc._schedule_step.assert_awaited_once_with(svc._schedule_step.call_args.args[0], 60)


@pytest.mark.asyncio
async def test_create_appends_to_existing_enrollment_ids():
    """drip_enrollment_ids must be appended to, not replaced, when ids already exist."""
    svc = DripCampaignService(_fake_session(assign_id=555))
    svc._schedule_step = AsyncMock(return_value="task")
    lead = _lead(extra_data={"drip_enrollment_ids": [1]})
    await svc._create_and_schedule_enrollment(_campaign(), lead, {})
    assert lead.extra_data["drip_enrollment_ids"] == [1, 555]


# ── Whitespace name (no crash) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whitespace_only_name_does_not_crash():
    """'   '.split()[0] would IndexError -> 500; first_name must resolve to None."""
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(return_value=_lead(name="   "))
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign())
    svc._create_and_schedule_enrollment = AsyncMock(return_value=_enrollment_stub())
    with patch.object(DripCampaignService, "detect_campaign_type", return_value="kids"):
        await svc.enroll_lead_manual(3, 10)
    _, _, context = svc._create_and_schedule_enrollment.call_args.args
    assert context["first_name"] is None


# ── Auto-detect through the REAL infer_audience (not mocked) ───────────────────

@pytest.mark.asyncio
async def test_auto_detect_adults_via_real_signal():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(
        return_value=_lead(extra_data={"ad_title": "Adult Swim"})
    )
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign(campaign_type="adults"))
    svc._create_and_schedule_enrollment = AsyncMock(return_value=_enrollment_stub(campaign_id=2))
    # detect_campaign_type NOT patched -> exercises real infer_audience -> 'adults'
    await svc.enroll_lead_manual(3, 10)
    svc.campaign_repo.get_by_type.assert_awaited_once_with(3, "adults")


@pytest.mark.asyncio
async def test_auto_detect_kids_via_real_signal():
    svc = _service()
    svc.lead_repo.get_by_id = AsyncMock(
        return_value=_lead(extra_data={"class_code": "Starfish"})
    )
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign())
    svc._create_and_schedule_enrollment = AsyncMock(return_value=_enrollment_stub())
    # real infer_audience: starfish is an infant class token -> 'Child (under 3)' -> kids
    await svc.enroll_lead_manual(3, 10)
    svc.campaign_repo.get_by_type.assert_awaited_once_with(3, "kids")


# ── Re-engagement: reactivate a prior terminal enrollment (no duplicate insert) ─

@pytest.mark.asyncio
async def test_reactivates_prior_completed_enrollment():
    """A completed/cancelled enrollment in the same campaign is reset & rescheduled
    in place — a fresh insert would violate the unique (tenant,campaign,lead) key."""
    svc = _service(_fake_session())
    lead = _lead(extra_data={"drip_enrolled": False, "drip_enrollment_ids": [77]})
    svc.lead_repo.get_by_id = AsyncMock(return_value=lead)
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign())
    prior = types.SimpleNamespace(
        id=77, status="completed", current_step=4, cancelled_reason=None,
        response_category="price", context_data={}, next_task_id=None,
        next_step_at=None, updated_at=None,
    )
    svc.enrollment_repo.get_for_campaign_and_lead = AsyncMock(return_value=prior)

    async def _sched(enr, _delay):
        enr.next_task_id = "task-reactivated"
        return "task-reactivated"

    svc._schedule_step = AsyncMock(side_effect=_sched)

    result = await svc.enroll_lead_manual(3, 10, campaign_type="kids")

    assert result is prior                       # reused, not a new row
    assert prior.status == "active"
    assert prior.current_step == 0
    assert prior.cancelled_reason is None
    assert prior.response_category is None
    assert prior.next_task_id == "task-reactivated"
    assert lead.extra_data["drip_enrolled"] is True
    svc.enrollment_repo.get_for_campaign_and_lead.assert_awaited_once()


# ── Cloud Tasks scheduling failure (don't strand an active enrollment) ─────────

@pytest.mark.asyncio
async def test_schedule_failure_rolls_back_and_raises():
    """If step 1 can't be scheduled, the lead must not be left flagged enrolled and
    the operator must get a retryable error (becomes a 400), not a phantom success."""
    svc = _service(_fake_session())
    lead = _lead(extra_data={})
    svc.lead_repo.get_by_id = AsyncMock(return_value=lead)
    svc.campaign_repo.get_by_type = AsyncMock(return_value=_campaign())
    svc._schedule_step = AsyncMock(return_value=None)  # Cloud Tasks failed

    with pytest.raises(ValueError, match="Couldn't schedule"):
        await svc.enroll_lead_manual(3, 10, campaign_type="kids")

    # rolled back: lead no longer shows as enrolled (so the UI/menu stays correct)
    assert lead.extra_data["drip_enrolled"] is False


# ── Naive-datetime invariant on next_step_at (the worker-killing trap) ─────────

@pytest.mark.asyncio
async def test_schedule_step_raw_writes_naive_future_next_step_at():
    """next_step_at must be naive (TIMESTAMP WITHOUT TIME ZONE) and = now+delay, not
    clobbered to ~now. Aware datetimes here 500 the drip worker."""
    svc = DripCampaignService(AsyncMock())
    enrollment = types.SimpleNamespace(id=1, tenant_id=3, next_step_at=None, next_task_id=None)

    with patch("app.domain.services.drip_campaign_service.CloudTasksClient") as MockCT, \
            patch.object(settings, "cloud_tasks_worker_url", "https://worker.example/process-sms"):
        MockCT.return_value.create_task_async = AsyncMock(return_value="projects/x/tasks/abc")
        task = await svc._schedule_step_raw(enrollment, 600)

    assert task == "projects/x/tasks/abc"
    assert enrollment.next_task_id == "projects/x/tasks/abc"
    # naive: no tzinfo
    assert enrollment.next_step_at.tzinfo is None
    # ~ now + 600s (would fail if clobbered back to ~now)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (enrollment.next_step_at - now_naive).total_seconds()
    assert 540 < delta < 660
