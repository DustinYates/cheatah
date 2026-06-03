"""Unit tests for the follow-up worker's lease / send / store ordering.

These lock in the fix for the "sent-but-empty" orphan bug, and the dupe-text-safe
failure handling. The invariants:

  * followup_sent_at is written ONLY after the SMS actually goes out
    (`_mark_followup_sent`), never up front.
  * A Telnyx rejection (HTTPStatusError = not delivered) releases the in-progress
    lease and re-raises, so the Cloud Tasks retry can re-send — no dupe risk.
  * An AMBIGUOUS send failure (timeout/connection drop = maybe delivered) does NOT
    retry: it marks sent and returns, so the customer is never double-texted.
  * A message-store failure AFTER a successful send is best-effort: the task still
    succeeds and the lead is never re-contacted.
  * Losing the atomic claim (rowcount 0) skips without sending.

All DB access and providers are mocked, so these never touch the real database.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.workers import followup_worker as fw
from app.workers.followup_worker import FollowUpTaskPayload

PAYLOAD = FollowUpTaskPayload(tenant_id=1, lead_id=42, phone_number="+15551234567")


def _build_env(*, send_return=None, send_raises=None, add_message_raises=None,
               claim_rowcount=1):
    """Wire up the full mock environment for process_followup_task.

    Returns (ExitStack of active patches, dict of the mocks worth asserting on).
    The caller uses the stack as a context manager.
    """
    lead = MagicMock()
    lead.id = 42
    lead.phone = "+15551234567"
    lead.name = "Test Lead"
    lead.extra_data = {"source": "email"}
    lead.conversation_id = None

    db = AsyncMock()
    claim_result = MagicMock()
    claim_result.rowcount = claim_rowcount
    db.execute = AsyncMock(return_value=claim_result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    lead_repo = MagicMock()
    lead_repo.get_by_id = AsyncMock(return_value=lead)

    sms_config = MagicMock()
    sms_config.is_enabled = True
    sms_config.provider = "telnyx"

    factory = MagicMock()
    factory.get_config = AsyncMock(return_value=sms_config)
    factory.get_sms_phone_number = MagicMock(return_value="+15559990000")
    factory.get_webhook_path_prefix = MagicMock(return_value="/telnyx")
    sms_provider = MagicMock()
    if send_raises is not None:
        sms_provider.send_sms = AsyncMock(side_effect=send_raises)
    else:
        sms_provider.send_sms = AsyncMock(return_value=send_return)
    factory.get_sms_provider = AsyncMock(return_value=sms_provider)

    dnc = MagicMock()
    dnc.is_blocked = AsyncMock(return_value=False)
    optin = MagicMock()
    optin.is_opted_in = AsyncMock(return_value=True)

    conversation = MagicMock()
    conversation.id = 777
    conv_service = MagicMock()
    conv_service.create_conversation = AsyncMock(return_value=conversation)
    conv_service.add_message = AsyncMock(side_effect=add_message_raises)

    conv_repo = MagicMock()
    conv_repo.get_by_id = AsyncMock(return_value=None)  # skip phone-update branch

    fu_msg_service = MagicMock()
    fu_msg_service.compose_followup_message = AsyncMock(return_value="hi there")

    mark_sent = AsyncMock()
    release_lease = AsyncMock()

    stack = ExitStack()
    p = stack.enter_context
    p(patch.object(fw, "LeadRepository", return_value=lead_repo))
    p(patch.object(fw, "TelephonyProviderFactory", return_value=factory))
    p(patch.object(fw, "DncService", return_value=dnc))
    p(patch.object(fw, "OptInService", return_value=optin))
    p(patch.object(fw, "ConversationService", return_value=conv_service))
    p(patch.object(fw, "FollowUpMessageService", return_value=fu_msg_service))
    p(patch(
        "app.persistence.repositories.conversation_repository.ConversationRepository",
        return_value=conv_repo,
    ))
    p(patch.object(fw, "_check_quiet_hours_and_defer", AsyncMock(return_value=None)))
    p(patch.object(fw, "_mark_followup_sent", mark_sent))
    p(patch.object(fw, "_release_followup_lease", release_lease))

    mocks = dict(
        db=db, lead=lead, send_sms=sms_provider.send_sms,
        add_message=conv_service.add_message,
        mark_sent=mark_sent, release_lease=release_lease,
    )
    return stack, mocks


def _ok_send_result():
    r = MagicMock()
    r.message_id = "msg-1"
    r.provider = "telnyx"
    return r


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError as send_sms raises on a Telnyx error response."""
    req = httpx.Request("POST", "https://api.telnyx.com/v2/messages")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=req, response=resp)


async def test_telnyx_rejection_releases_lease_and_retries():
    """A Telnyx error response = not delivered, so release the lease and propagate
    (→ Cloud Tasks retry can re-send). Must NOT mark the lead as sent."""
    stack, m = _build_env(send_raises=_http_status_error(500))
    with stack:
        with pytest.raises(HTTPException):
            await fw.process_followup_task(MagicMock(), PAYLOAD, m["db"])

    m["release_lease"].assert_awaited_once()
    m["mark_sent"].assert_not_awaited()
    m["add_message"].assert_not_awaited()


async def test_ambiguous_send_marks_sent_and_does_not_retry():
    """A timeout/connection error might mean the SMS WAS delivered. To avoid a
    duplicate text, mark sent and return success (no raise → no Cloud Tasks retry),
    and do not release the lease."""
    stack, m = _build_env(send_raises=httpx.ReadTimeout("timed out"))
    with stack:
        result = await fw.process_followup_task(MagicMock(), PAYLOAD, m["db"])

    assert result["status"] == "uncertain"
    m["mark_sent"].assert_awaited_once()
    m["release_lease"].assert_not_awaited()
    m["add_message"].assert_not_awaited()


async def test_store_failure_after_send_is_best_effort():
    """If the SMS sent but storing the message fails, the task still succeeds,
    the lead is marked sent (never resent), and the lease is not released."""
    stack, m = _build_env(
        send_return=_ok_send_result(),
        add_message_raises=RuntimeError("DB write failed"),
    )
    with stack:
        result = await fw.process_followup_task(MagicMock(), PAYLOAD, m["db"])

    assert result["status"] == "success"
    m["mark_sent"].assert_awaited_once()
    m["add_message"].assert_awaited_once()
    m["release_lease"].assert_not_awaited()


async def test_happy_path_marks_sent_then_stores():
    """On full success: send → mark sent → store, no lease release."""
    stack, m = _build_env(send_return=_ok_send_result())
    with stack:
        result = await fw.process_followup_task(MagicMock(), PAYLOAD, m["db"])

    assert result["status"] == "success"
    assert result["conversation_id"] == 777
    m["send_sms"].assert_awaited_once()
    m["mark_sent"].assert_awaited_once()
    m["add_message"].assert_awaited_once()
    m["release_lease"].assert_not_awaited()


async def test_lost_claim_skips_without_sending():
    """If the atomic claim matched no row (another worker won, or already sent),
    skip without sending or marking."""
    stack, m = _build_env(send_return=_ok_send_result(), claim_rowcount=0)
    with stack:
        result = await fw.process_followup_task(MagicMock(), PAYLOAD, m["db"])

    assert result["status"] == "skipped"
    assert result["reason"] == "already_claimed"
    m["send_sms"].assert_not_awaited()
    m["mark_sent"].assert_not_awaited()
