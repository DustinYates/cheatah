"""Unit tests for carrier-level opt-out detection + reconciliation.

Covers the pure detectors (is_opt_out_send_error, is_opt_out_confirmation,
messages_contain_opt_out_confirmation) and reconcile_carrier_opt_out. All DB
access — OptInService, LeadRepository, DripCampaignService — is mocked, so these
tests never touch the real database.
"""

import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.telephony.base import (
    RecipientOptedOutError,
    is_opt_out_send_error,
)
from app.domain.services.opt_out_reconciler import (
    is_opt_out_confirmation,
    messages_contain_opt_out_confirmation,
    reconcile_carrier_opt_out,
)


# ── Pure detectors ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "code,detail,expected",
    [
        ("40300", None, True),                                  # the canonical code
        ("40300", "anything", True),
        ("40001", "Recipient has opted out of messages", True), # by detail
        ("40001", "Destination banned", True),
        ("40001", "Could not unsubscribe handler", True),       # "unsubscrib" marker
        ("40001", "temporary network error", False),            # unrelated failure
        (None, None, False),
        ("", "", False),
    ],
)
def test_is_opt_out_send_error(code, detail, expected):
    assert is_opt_out_send_error(code, detail) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        # Telnyx carrier copy (the exact string the affected customers received)
        ("You have successfully been unsubscribed, you will not receive any more "
         "messages from this number. Reply START to re-subscribe.", True),
        # Our own compliance_handler copy
        ("You have been unsubscribed. You will no longer receive messages. "
         "Reply START to opt back in.", True),
        # unsubscribe word but no re-subscribe cue -> not a confirmation
        ("Can I unsubscribe from one class but keep the other?", False),
        # re-subscribe cue but no unsubscribe word -> not a confirmation
        ("Reply START whenever you're ready to begin!", False),
        ("How much does it cost", False),
        (None, False),
        ("", False),
    ],
)
def test_is_opt_out_confirmation(text, expected):
    assert is_opt_out_confirmation(text) is expected


def test_messages_contain_opt_out_confirmation_only_assistant():
    # Confirmation is OUTBOUND — a user message echoing the words must not trip it.
    user_only = [{"role": "user", "text": "unsubscribe me, reply start"}]
    assert messages_contain_opt_out_confirmation(user_only) is False

    mixed = [
        {"role": "user", "text": "How much does it cost"},
        {"role": "assistant", "text": "You have successfully been unsubscribed. "
                                      "Reply START to re-subscribe."},
    ]
    assert messages_contain_opt_out_confirmation(mixed) is True

    # `content` key (instead of `text`) is also honored
    assert messages_contain_opt_out_confirmation(
        [{"role": "assistant", "content": "Unsubscribed. Reply START to re-subscribe."}]
    ) is True

    assert messages_contain_opt_out_confirmation([]) is False
    assert messages_contain_opt_out_confirmation(
        [{"role": "assistant", "text": "Want me to send class options?"}]
    ) is False


def test_recipient_opted_out_error_carries_context():
    err = RecipientOptedOutError(phone="+15551234567", detail="Destination banned", code="40300")
    assert err.phone == "+15551234567"
    assert err.code == "40300"
    assert "banned" in str(err)


# ── reconcile_carrier_opt_out ────────────────────────────────────────────────

def _patch_collaborators(*, already_opted_out=False, leads=None, cancel_counts=None):
    """Patch the lazily-imported collaborators. Returns (opt_in, drip, ctx-managers).

    already_opted_out: existing opt-in row with is_opted_in=False (idempotency).
    leads: list of lead stubs find_leads_with_conversation_by_email_or_phone returns.
    cancel_counts: per-call return values for cancel_all_for_lead.
    """
    opt_in = MagicMock()
    status = None if already_opted_out is None else types.SimpleNamespace(
        is_opted_in=not already_opted_out
    )
    opt_in.get_opt_in_status = AsyncMock(return_value=status)
    opt_in.opt_out = AsyncMock()

    drip = MagicMock()
    drip.cancel_all_for_lead = AsyncMock(side_effect=cancel_counts or [0])

    lead_repo = MagicMock()
    lead_repo.find_leads_with_conversation_by_email_or_phone = AsyncMock(
        return_value=leads or []
    )

    patches = [
        patch("app.domain.services.opt_in_service.OptInService", return_value=opt_in),
        patch("app.domain.services.drip_campaign_service.DripCampaignService", return_value=drip),
        patch("app.persistence.repositories.lead_repository.LeadRepository", return_value=lead_repo),
    ]
    return opt_in, drip, lead_repo, patches


@pytest.mark.asyncio
async def test_reconcile_opts_out_and_cancels_drips():
    lead = types.SimpleNamespace(id=3201)
    opt_in, drip, lead_repo, patches = _patch_collaborators(
        already_opted_out=False, leads=[lead], cancel_counts=[1]
    )
    with patches[0], patches[1], patches[2]:
        changed = await reconcile_carrier_opt_out(
            AsyncMock(), tenant_id=3, phone_number="+17139356184",
            method="telnyx_carrier", reason="opted_out_telnyx",
        )
    assert changed is True
    opt_in.opt_out.assert_awaited_once_with(3, "+17139356184", method="telnyx_carrier")
    drip.cancel_all_for_lead.assert_awaited_once_with(3, 3201, "opted_out_telnyx")


@pytest.mark.asyncio
async def test_reconcile_idempotent_when_already_opted_out_and_no_active_drips():
    # Already opted out + no active enrollments -> nothing changes, no opt_out write.
    opt_in, drip, lead_repo, patches = _patch_collaborators(
        already_opted_out=True, leads=[types.SimpleNamespace(id=9)], cancel_counts=[0]
    )
    with patches[0], patches[1], patches[2]:
        changed = await reconcile_carrier_opt_out(
            AsyncMock(), tenant_id=3, phone_number="+17139356184",
        )
    assert changed is False
    opt_in.opt_out.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_blank_phone_is_noop():
    changed = await reconcile_carrier_opt_out(AsyncMock(), tenant_id=3, phone_number="")
    assert changed is False


@pytest.mark.asyncio
async def test_reconcile_never_raises_on_collaborator_failure():
    # If opt_out blows up, reconcile must swallow it (it's best-effort sync).
    opt_in, drip, lead_repo, patches = _patch_collaborators(already_opted_out=False)
    opt_in.opt_out = AsyncMock(side_effect=RuntimeError("db down"))
    with patches[0], patches[1], patches[2]:
        changed = await reconcile_carrier_opt_out(
            AsyncMock(), tenant_id=3, phone_number="+17139356184",
        )
    assert changed is False  # exception swallowed, nothing committed
