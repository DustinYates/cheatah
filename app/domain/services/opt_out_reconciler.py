"""Reconcile carrier/Telnyx-level SMS opt-outs into application state.

Telnyx (and carriers) handle STOP/unsubscribe at the messaging-profile level for
10DLC compliance: they send the opt-out confirmation and suppress the number
WITHOUT delivering an inbound STOP webhook to us. Our normal opt-out path
(`compliance_handler` on inbound SMS) therefore never runs, leaving the phone
marked opted-in, absent from the do-not-contact list, and still ACTIVE in drip
campaigns — while Telnyx silently blocks every further send.

This module gives every place that can *observe* a carrier opt-out — an ingested
"unsubscribed" confirmation, a blocked outbound send, or a `message.failed`
delivery webhook — one idempotent, exception-safe entry point to bring our
state back in sync.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Cues that an outbound message is an unsubscribe *confirmation*. We require an
# unsubscribe word AND a re-subscribe/START cue together so that a normal
# sentence merely mentioning "unsubscribe" doesn't trip the detector. Matches
# both Telnyx's carrier copy ("You have successfully been unsubscribed ... Reply
# START to re-subscribe") and our own compliance_handler copy.
_RESUBSCRIBE_CUES = (
    "reply start",
    "re-subscribe",
    "resubscribe",
    "opt back in",
)


def is_opt_out_confirmation(text: str | None) -> bool:
    """True if `text` looks like an SMS unsubscribe confirmation."""
    if not text:
        return False
    t = text.lower()
    if "unsubscrib" not in t:
        return False
    return any(cue in t for cue in _RESUBSCRIBE_CUES)


def messages_contain_opt_out_confirmation(messages: list[dict]) -> bool:
    """True if any outbound (assistant) message is an unsubscribe confirmation.

    `messages` is the raw list returned by the Telnyx conversation API (each a
    dict with `role` and `text`/`content`). Only assistant/outbound turns are
    considered — the confirmation is sent *from* our number.
    """
    for msg in messages or []:
        if msg.get("role") != "assistant":
            continue
        if is_opt_out_confirmation(msg.get("text") or msg.get("content")):
            return True
    return False


async def reconcile_carrier_opt_out(
    session: AsyncSession,
    tenant_id: int,
    phone_number: str,
    *,
    method: str = "telnyx_carrier",
    reason: str = "opted_out_telnyx",
) -> bool:
    """Record a carrier-level SMS opt-out and cancel active drips for a phone.

    Idempotent and exception-safe: safe to call from multiple detection points
    and never raises into the caller. Returns True if any state changed.
    """
    if not phone_number:
        return False

    # Lazy imports avoid an import cycle (drip service -> this module -> drip
    # service) and mirror the pattern used elsewhere in the codebase.
    from app.domain.services.drip_campaign_service import DripCampaignService
    from app.domain.services.opt_in_service import OptInService
    from app.persistence.repositories.lead_repository import LeadRepository

    changed = False
    try:
        opt_in_service = OptInService(session)
        status = await opt_in_service.get_opt_in_status(tenant_id, phone_number)
        if status is None or status.is_opted_in:
            await opt_in_service.opt_out(tenant_id, phone_number, method=method)
            changed = True
            logger.info(
                f"[OPT-OUT-SYNC] Recorded carrier opt-out "
                f"tenant_id={tenant_id} phone={phone_number} method={method}"
            )

        # Cancel any active drip enrollments tied to this phone so the dashboard
        # stops showing the lead as ACTIVE and we stop attempting sends Telnyx
        # will only reject.
        lead_repo = LeadRepository(session)
        leads = await lead_repo.find_leads_with_conversation_by_email_or_phone(
            tenant_id, phone=phone_number
        )
        drip_service = DripCampaignService(session)
        for lead in leads:
            count = await drip_service.cancel_all_for_lead(tenant_id, lead.id, reason)
            if count:
                changed = True
                logger.info(
                    f"[OPT-OUT-SYNC] Cancelled {count} drip enrollment(s) for "
                    f"lead {lead.id} ({reason})"
                )
    except Exception as e:
        logger.error(
            f"[OPT-OUT-SYNC] Failed to reconcile opt-out tenant_id={tenant_id} "
            f"phone={phone_number}: {e}",
            exc_info=True,
        )
    return changed
