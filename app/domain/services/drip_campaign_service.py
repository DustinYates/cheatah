"""Service for managing drip campaign enrollment, step execution, and response handling."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.conversation_service import ConversationService
from app.domain.services.dnc_service import DncService
from app.domain.services.drip_message_service import DripMessageService
from app.domain.services.opt_in_service import OptInService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.telephony.base import RecipientOptedOutError
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.models.drip_campaign import DripCampaign, DripCampaignStep, DripEnrollment
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.drip_campaign_repository import (
    DripCampaignRepository,
    DripEnrollmentRepository,
)
from app.persistence.repositories.lead_repository import LeadRepository
from app.settings import settings

logger = logging.getLogger(__name__)


def _naive_utcnow() -> datetime:
    """Naive UTC 'now' for the TIMESTAMP WITHOUT TIME ZONE columns on drip_enrollments.

    updated_at / next_step_at are naive. Writing an aware datetime.now(timezone.utc)
    to them — via ORM attribute assignment OR Core update() — makes asyncpg raise
    "can't subtract offset-naive and offset-aware datetimes" and 500s the worker.
    For updated_at the model's onupdate=datetime.utcnow only saves us when the column
    is NOT explicitly assigned; these methods assign it explicitly, so we must hand it
    a naive value ourselves. next_step_at has no onupdate at all.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DripCampaignService:
    """Manages drip campaign enrollment, step advancement, and response handling."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.campaign_repo = DripCampaignRepository(session)
        self.enrollment_repo = DripEnrollmentRepository(session)
        self.lead_repo = LeadRepository(session)
        self.message_service = DripMessageService()

    # ── Enrollment ───────────────────────────────────────────────────────

    async def enroll_lead(
        self,
        tenant_id: int,
        lead_id: int,
        campaign_type: str,
        context_data: dict | None = None,
    ) -> DripEnrollment | None:
        """Enroll a lead in a drip campaign.

        Returns None if no matching campaign, campaign disabled, or already enrolled.
        """
        campaign = await self.campaign_repo.get_by_type(tenant_id, campaign_type)
        if not campaign:
            logger.debug(f"No {campaign_type} campaign found for tenant {tenant_id}")
            return None

        if not campaign.is_enabled:
            logger.debug(f"Campaign {campaign.id} ({campaign_type}) is disabled for tenant {tenant_id}")
            return None

        if not campaign.steps:
            logger.warning(f"Campaign {campaign.id} has no steps configured")
            return None

        # Check not already enrolled
        existing = await self.enrollment_repo.get_active_for_lead(tenant_id, lead_id)
        if existing:
            logger.info(f"Lead {lead_id} already enrolled in drip (enrollment {existing.id})")
            return None

        # Verify lead has a phone number
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead or not lead.phone:
            logger.warning(f"Lead {lead_id} has no phone number, cannot enroll in drip")
            return None

        # Skip drip for phone numbers that belong to existing customers
        from app.persistence.repositories.customer_repository import CustomerRepository
        customer = await CustomerRepository(self.session).get_by_phone(tenant_id, lead.phone)
        if customer:
            logger.info(
                f"Lead {lead_id} phone {lead.phone} matches existing customer "
                f"{customer.id} ({customer.name}), skipping drip enrollment"
            )
            return None

        return await self._create_and_schedule_enrollment(campaign, lead, context_data)

    async def enroll_lead_manual(
        self,
        tenant_id: int,
        lead_id: int,
        campaign_type: str | None = None,
    ) -> DripEnrollment:
        """Manually enroll a lead in a drip campaign (from the dashboard UI).

        Unlike enroll_lead (the automatic path, which silently returns None on any
        skip condition), this raises ValueError with a user-facing message per failure
        so the UI can show exactly why an enrollment did not happen. campaign_type is
        auto-detected from the lead's audience tag when not provided.
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            raise ValueError("Lead not found.")
        if not lead.phone:
            raise ValueError(
                "This lead has no phone number — add one before enrolling in an SMS drip."
            )

        existing = await self.enrollment_repo.get_active_for_lead(tenant_id, lead_id)
        if existing:
            raise ValueError("This lead is already enrolled in an active drip campaign.")

        # Respect the existing-customer guard (auto-path skips silently; we report it).
        from app.persistence.repositories.customer_repository import CustomerRepository
        customer = await CustomerRepository(self.session).get_by_phone(tenant_id, lead.phone)
        if customer:
            raise ValueError(
                f"Not enrolled — this phone matches an existing customer ({customer.name})."
            )

        ctype = campaign_type or self.detect_campaign_type(
            lead_extra_data=lead.extra_data,
            custom_tags=list(lead.custom_tags or []),
        )
        campaign = await self.campaign_repo.get_by_type(tenant_id, ctype)
        if not campaign:
            raise ValueError(f"No '{ctype}' drip campaign is configured for this tenant.")
        if not campaign.is_enabled:
            raise ValueError(
                f"The '{ctype}' drip campaign is disabled — enable it in Campaign Settings first."
            )
        if not campaign.steps:
            raise ValueError(f"The '{ctype}' drip campaign has no steps configured.")

        # split() on a whitespace-only name raises IndexError; guard with strip().
        first_name = lead.name.split()[0] if (lead.name and lead.name.strip()) else None
        context_data = {"first_name": first_name, "source": "manual_enroll"}

        # If the lead previously finished/cancelled THIS campaign, reuse that row
        # (re-engagement). A fresh insert with the same (tenant, campaign, lead)
        # would violate uq_drip_enrollment_tenant_campaign_lead and 500. An ACTIVE
        # row in this campaign was already caught by the get_active_for_lead guard
        # above, so any row found here is terminal (completed/cancelled).
        prior = await self.enrollment_repo.get_for_campaign_and_lead(
            tenant_id, campaign.id, lead_id
        )
        if prior is not None:
            enrollment = await self._reactivate_enrollment(prior, campaign, lead, context_data)
        else:
            enrollment = await self._create_and_schedule_enrollment(campaign, lead, context_data)

        # Don't advertise a phantom success: if Cloud Tasks scheduling failed, the
        # enrollment would sit 'active' with no task to ever fire it. Roll it back to
        # a recoverable terminal state and surface a retryable error (becomes a 400).
        if not enrollment.next_task_id:
            await self._mark_schedule_failed(enrollment, lead)
            raise ValueError(
                "Couldn't schedule the first message right now — please try again in a moment."
            )
        return enrollment

    async def _create_and_schedule_enrollment(
        self,
        campaign: DripCampaign,
        lead,
        context_data: dict | None,
    ) -> DripEnrollment:
        """Create the enrollment row, flag the lead, and schedule step 1.

        Shared by both enroll_lead (automatic) and enroll_lead_manual so the
        carefully-fixed create/commit/schedule sequence lives in one place.
        Assumes all eligibility checks (campaign enabled, has steps, lead has
        phone, not already enrolled) have already passed.
        """
        enrollment = DripEnrollment(
            tenant_id=lead.tenant_id,
            campaign_id=campaign.id,
            lead_id=lead.id,
            status="active",
            current_step=0,
            context_data=context_data or {},
        )
        self.session.add(enrollment)

        # Mark lead as drip enrolled (use dict() to trigger SQLAlchemy change detection)
        extra_data = dict(lead.extra_data or {})
        extra_data["drip_enrolled"] = True
        if "drip_enrollment_ids" not in extra_data:
            extra_data["drip_enrollment_ids"] = []
        lead.extra_data = extra_data
        await self.session.commit()
        await self.session.refresh(enrollment)

        # Update the enrollment IDs list now that we have the ID
        extra_data = dict(lead.extra_data or {})
        extra_data.setdefault("drip_enrollment_ids", []).append(enrollment.id)
        lead.extra_data = extra_data
        await self.session.commit()

        delay_minutes = await self._schedule_first_step(enrollment, campaign)
        logger.info(
            f"Enrolled lead {lead.id} in drip campaign {campaign.id} ({campaign.campaign_type}), "
            f"enrollment={enrollment.id}, first step in {delay_minutes} min"
        )
        return enrollment

    async def _reactivate_enrollment(
        self,
        enrollment: DripEnrollment,
        campaign: DripCampaign,
        lead,
        context_data: dict | None,
    ) -> DripEnrollment:
        """Reset a previously completed/cancelled enrollment to active and reschedule
        step 1 — re-engages a lead without inserting a duplicate row (forbidden by the
        unique (tenant, campaign, lead) constraint)."""
        enrollment.status = "active"
        enrollment.current_step = 0
        enrollment.cancelled_reason = None
        enrollment.response_category = None
        enrollment.context_data = context_data or {}
        enrollment.next_task_id = None
        enrollment.next_step_at = None
        enrollment.updated_at = _naive_utcnow()

        extra_data = dict(lead.extra_data or {})
        extra_data["drip_enrolled"] = True
        ids = extra_data.setdefault("drip_enrollment_ids", [])
        if enrollment.id not in ids:
            ids.append(enrollment.id)
        lead.extra_data = extra_data
        await self.session.commit()

        delay_minutes = await self._schedule_first_step(enrollment, campaign)
        logger.info(
            f"Reactivated drip enrollment {enrollment.id} for lead {lead.id} in campaign "
            f"{campaign.id} ({campaign.campaign_type}), first step in {delay_minutes} min"
        )
        return enrollment

    async def _schedule_first_step(self, enrollment: DripEnrollment, campaign: DripCampaign) -> int:
        """Schedule step 1 and persist the schedule; returns the delay used.

        Step 1's own delay_minutes is the single source of truth for the
        after-enrollment wait; trigger_delay_minutes is only a fallback when step 1
        has no delay. _schedule_step sets next_task_id/next_step_at (= now + delay) on
        the enrollment on success; we just persist them. Re-assigning next_step_at
        here would clobber it with 'now' and mislabel the dashboard's next-send time.
        """
        first_step = next((s for s in campaign.steps if s.step_number == 1), None)
        delay_minutes = (
            first_step.delay_minutes
            if first_step and first_step.delay_minutes is not None
            else (campaign.trigger_delay_minutes or 10)
        )
        task_id = await self._schedule_step(enrollment, delay_minutes)
        if task_id:
            await self.session.commit()
        return delay_minutes

    async def _mark_schedule_failed(self, enrollment: DripEnrollment, lead) -> None:
        """Roll an enrollment back to a recoverable terminal state when its first step
        couldn't be scheduled, so it isn't left 'active' with nothing to fire it. A
        later retry will reactivate this same row."""
        enrollment.status = "cancelled"
        enrollment.cancelled_reason = "schedule_failed"
        enrollment.next_task_id = None
        enrollment.next_step_at = None
        enrollment.updated_at = _naive_utcnow()
        extra_data = dict(lead.extra_data or {})
        extra_data["drip_enrolled"] = False
        lead.extra_data = extra_data
        await self.session.commit()

    # ── Step Advancement ─────────────────────────────────────────────────

    async def advance_step(self, enrollment_id: int) -> dict:
        """Execute the next step of a drip sequence.

        Called by drip_worker when a Cloud Task fires.

        Returns dict with status info.
        """
        enrollment = await self.enrollment_repo.get_by_id(None, enrollment_id)
        if not enrollment:
            return {"status": "skipped", "reason": "enrollment_not_found"}

        if enrollment.status != "active":
            logger.info(f"Enrollment {enrollment_id} is {enrollment.status}, skipping step")
            return {"status": "skipped", "reason": f"status_{enrollment.status}"}

        tenant_id = enrollment.tenant_id
        next_step_num = enrollment.current_step + 1

        # Load campaign with steps
        campaign = await self.campaign_repo.get_with_steps(tenant_id, enrollment.campaign_id)
        if not campaign:
            return {"status": "skipped", "reason": "campaign_not_found"}

        # Find the step
        step = next((s for s in campaign.steps if s.step_number == next_step_num), None)
        if not step:
            # No more steps — mark completed
            enrollment.status = "completed"
            enrollment.updated_at = _naive_utcnow()
            await self.session.commit()
            logger.info(f"Enrollment {enrollment_id} completed (no step {next_step_num})")
            return {"status": "completed"}

        # Load lead
        lead = await self.lead_repo.get_by_id(tenant_id, enrollment.lead_id)
        if not lead or not lead.phone:
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = "no_phone"
            await self.session.commit()
            return {"status": "skipped", "reason": "no_phone"}

        # Get SMS config for quiet hours / provider
        factory = TelephonyProviderFactory(self.session)
        sms_config = await factory.get_config(tenant_id)
        if not sms_config or not sms_config.is_enabled:
            return {"status": "skipped", "reason": "sms_not_enabled"}

        # Quiet hours check
        from app.workers.followup_worker import _is_quiet_hours, _seconds_until_quiet_hours_end
        tz_name = sms_config.timezone or "UTC"
        if _is_quiet_hours(tz_name):
            delay_seconds = _seconds_until_quiet_hours_end(tz_name)
            logger.info(f"Quiet hours for enrollment {enrollment_id}, deferring {delay_seconds}s")
            await self._schedule_step_raw(enrollment, delay_seconds)
            return {"status": "deferred", "reason": "quiet_hours", "seconds": delay_seconds}

        # DNC check
        dnc_service = DncService(self.session)
        if await dnc_service.is_blocked(tenant_id, phone=lead.phone):
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = "dnc"
            await self.session.commit()
            return {"status": "skipped", "reason": "dnc"}

        # Opt-in check (auto opt-in for email source with implied consent)
        opt_in_service = OptInService(self.session)
        is_opted_in = await opt_in_service.is_opted_in(tenant_id, lead.phone)
        if not is_opted_in:
            source = lead.extra_data.get("source") if lead.extra_data else None
            if source in ("voice_call", "email"):
                await opt_in_service.opt_in(
                    tenant_id, lead.phone, method=f"implied_{source}_drip"
                )
            else:
                enrollment.status = "cancelled"
                enrollment.cancelled_reason = "not_opted_in"
                await self.session.commit()
                return {"status": "skipped", "reason": "not_opted_in"}

        # Build message
        context = dict(enrollment.context_data or {})
        # Add lead name to context if available
        if lead.name and "first_name" not in context:
            context["first_name"] = lead.name.split()[0] if lead.name else ""

        if step.check_availability:
            message = await self.message_service.render_with_availability(
                step.message_template, context, tenant_id, step.fallback_template
            )
        else:
            message = self.message_service.render_template(step.message_template, context)

        if not message:
            logger.error(f"Empty message for enrollment {enrollment_id} step {next_step_num}")
            return {"status": "error", "reason": "empty_message"}

        # Get SMS provider and phone
        from_phone = factory.get_sms_phone_number(sms_config)
        if not from_phone:
            return {"status": "skipped", "reason": "no_from_phone"}

        sms_provider = await factory.get_sms_provider(tenant_id)
        if not sms_provider:
            return {"status": "skipped", "reason": "no_sms_provider"}

        # Build status callback URL
        status_callback_url = None
        if settings.api_base_url:
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.api_base_url}/api/v1/sms{webhook_prefix}/status"

        # Atomically claim this step before sending. Prevents duplicate SMS when
        # Cloud Tasks retries a task whose previous attempt sent the SMS but
        # didn't return 2xx in time. Only the worker whose UPDATE matches the
        # current step value proceeds to send.
        # NOTE: do NOT pass updated_at here. The column is TIMESTAMP WITHOUT TIME
        # ZONE (naive); binding an aware datetime.now(timezone.utc) through a Core
        # update() bypasses the model's onupdate=datetime.utcnow and makes asyncpg
        # raise "can't subtract offset-naive and offset-aware datetimes", which
        # threw on every drip step and stalled all enrollments. Omitting the column
        # lets the model's onupdate populate it with a naive UTC value.
        claim_stmt = (
            update(DripEnrollment)
            .where(
                DripEnrollment.id == enrollment_id,
                DripEnrollment.current_step == next_step_num - 1,
                DripEnrollment.status == "active",
            )
            .values(current_step=next_step_num)
        )
        claim_result = await self.session.execute(claim_stmt)
        await self.session.commit()
        if claim_result.rowcount == 0:
            logger.warning(
                f"Drip step {next_step_num} for enrollment {enrollment_id} "
                f"already claimed by another worker, skipping send"
            )
            return {"status": "skipped", "reason": "already_claimed"}
        await self.session.refresh(enrollment)

        # Send SMS
        try:
            send_result = await sms_provider.send_sms(
                to=lead.phone,
                from_=from_phone,
                body=message,
                status_callback=status_callback_url,
            )
        except RecipientOptedOutError:
            # Telnyx/carrier suppressed this number (opted out) without ever
            # delivering us an inbound STOP. Sync our state instead of leaving
            # the enrollment ACTIVE and re-attempting on every future step.
            from app.domain.services.opt_out_reconciler import (
                reconcile_carrier_opt_out,
            )
            logger.info(
                f"Enrollment {enrollment_id}: recipient {lead.phone} opted out "
                f"at carrier on step {next_step_num} — cancelling + syncing opt-out"
            )
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = "opted_out_telnyx"
            enrollment.next_task_id = None
            enrollment.next_step_at = None
            await self.session.commit()
            await reconcile_carrier_opt_out(
                self.session, tenant_id, lead.phone,
                method="telnyx_blocked", reason="opted_out_telnyx",
            )
            return {"status": "skipped", "reason": "opted_out"}

        # Store in conversation
        conversation_service = ConversationService(self.session)
        # Create or reuse conversation
        conv_external_id = f"drip-{enrollment.id}"
        conversation = await conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="sms",
            external_id=conv_external_id,
        )
        # Link the conversation to the lead so it surfaces in the Lead Activity
        # Timeline. The timeline endpoint loads conversations via
        # lead.conversation_id OR lead.contact_id; without either link the
        # message row is orphaned and only the lead.notes audit line is visible.
        from app.persistence.repositories.conversation_repository import ConversationRepository
        conv_repo = ConversationRepository(self.session)
        conv = await conv_repo.get_by_id(tenant_id, conversation.id)
        if conv:
            conv.phone_number = lead.phone
            if lead.contact_id and not conv.contact_id:
                conv.contact_id = lead.contact_id
            if not lead.conversation_id:
                lead.conversation_id = conv.id
            await self.session.commit()

        await conversation_service.add_message(
            tenant_id, conversation.id, "assistant", message
        )

        # current_step + updated_at were bumped by the CAS above; only manage
        # downstream fields (next task scheduling, completion state) here.
        enrollment.updated_at = _naive_utcnow()

        # Schedule next step if there are more
        next_next_step = next(
            (s for s in campaign.steps if s.step_number == next_step_num + 1), None
        )
        if next_next_step:
            task_id = await self._schedule_step(enrollment, next_next_step.delay_minutes)
            enrollment.next_task_id = task_id
        else:
            # Last step — mark completed
            enrollment.status = "completed"
            enrollment.next_task_id = None
            enrollment.next_step_at = None

        await self.session.commit()

        logger.info(
            f"Drip step {next_step_num} sent for enrollment {enrollment_id}, "
            f"message_id={send_result.message_id}"
        )
        return {
            "status": "success",
            "step": next_step_num,
            "message_id": send_result.message_id,
            "conversation_id": conversation.id,
        }

    # ── Response Handling ────────────────────────────────────────────────

    async def handle_response(
        self, tenant_id: int, lead_id: int, message_text: str
    ) -> dict:
        """Handle an inbound SMS from a drip-enrolled lead.

        Classifies the response and sends the appropriate scripted reply.

        Returns dict with:
          - handled: True if drip system handled it, False if normal AI should take over
          - reply: The response message sent (if any)
          - category: The classified category
        """
        enrollment = await self.enrollment_repo.get_active_for_lead(tenant_id, lead_id)
        if not enrollment:
            return {"handled": False, "reason": "no_active_enrollment"}

        # Load campaign for response templates
        campaign = await self.campaign_repo.get_with_steps(tenant_id, enrollment.campaign_id)
        if not campaign or not campaign.response_templates:
            return {"handled": False, "reason": "no_response_templates"}

        response_templates = campaign.response_templates

        # Classify the response
        category = self.message_service.classify_response(message_text, response_templates)
        if category == "other":
            # Try LLM classification
            category = await self.message_service.classify_response_with_llm(
                message_text, response_templates
            )

        enrollment.response_category = category
        enrollment.updated_at = _naive_utcnow()

        template_data = response_templates.get(category, {})
        action = template_data.get("action")

        # Handle actions
        if action == "cancel_drip" or category == "not_interested":
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = "not_interested"
            await self.session.commit()
            return {"handled": False, "reason": "not_interested_let_ai_handle"}

        if action == "send_registration_link" or category == "yes_link":
            # Send registration link and mark completed
            reply = await self._send_registration_link(tenant_id, enrollment)
            enrollment.status = "completed"
            await self.session.commit()
            if reply:
                return {"handled": True, "reply": reply, "category": category}
            return {"handled": False, "reason": "link_send_failed"}

        # Category match (price, spouse, schedule, sibling) — send scripted reply
        reply_template = template_data.get("reply", "")
        if not reply_template:
            # No reply template — let AI handle
            enrollment.status = "responded"
            await self.session.commit()
            return {"handled": False, "reason": "no_reply_template", "category": category}

        # Render and send the reply
        context = dict(enrollment.context_data or {})
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if lead and lead.name:
            context.setdefault("first_name", lead.name.split()[0])
            context.setdefault("child_name", "your child")

        reply = self.message_service.render_template(reply_template, context)

        # Send SMS
        sent = await self._send_sms(tenant_id, lead_id, reply)
        if not sent:
            return {"handled": False, "reason": "sms_send_failed"}

        # Transition to responded state
        enrollment.status = "responded"
        await self.session.commit()

        # Schedule resume check — if no further response in 24h, resume drip
        await self._schedule_resume_check(enrollment, delay_minutes=1440)

        logger.info(
            f"Drip response handled for enrollment {enrollment.id}: "
            f"category={category}, reply sent"
        )
        return {"handled": True, "reply": reply, "category": category}

    # ── State Transitions ────────────────────────────────────────────────

    async def cancel_enrollment(self, enrollment_id: int, reason: str) -> bool:
        """Cancel a specific enrollment."""
        enrollment = await self.enrollment_repo.get_by_id(None, enrollment_id)
        if not enrollment or enrollment.status in ("completed", "cancelled"):
            return False

        enrollment.status = "cancelled"
        enrollment.cancelled_reason = reason
        enrollment.updated_at = _naive_utcnow()
        await self.session.commit()
        logger.info(f"Cancelled drip enrollment {enrollment_id}: {reason}")
        return True

    async def cancel_all_for_lead(self, tenant_id: int, lead_id: int, reason: str) -> int:
        """Cancel all active enrollments for a lead."""
        count = await self.enrollment_repo.cancel_all_for_lead(tenant_id, lead_id, reason)
        if count > 0:
            # Update lead extra_data
            lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
            if lead:
                extra_data = dict(lead.extra_data or {})
                extra_data["drip_enrolled"] = False
                lead.extra_data = extra_data
                await self.session.commit()
            logger.info(f"Cancelled {count} drip enrollments for lead {lead_id}: {reason}")
        return count

    async def resume_if_still_responded(self, enrollment_id: int) -> dict:
        """Resume drip if enrollment is still in 'responded' status (no further reply).

        Called by drip_worker on a resume_check schedule.
        """
        enrollment = await self.enrollment_repo.get_by_id(None, enrollment_id)
        if not enrollment:
            return {"status": "skipped", "reason": "not_found"}

        if enrollment.status != "responded":
            return {"status": "skipped", "reason": f"status_{enrollment.status}"}

        # Resume to active and advance to next step
        enrollment.status = "active"
        enrollment.updated_at = _naive_utcnow()
        await self.session.commit()

        logger.info(f"Resuming drip enrollment {enrollment_id} after response timeout")
        return await self.advance_step(enrollment_id)

    # ── Campaign Type Detection ──────────────────────────────────────────

    @staticmethod
    def detect_campaign_type(
        email_subject: str | None = None,
        email_body: str | None = None,
        *,
        lead_extra_data: dict | None = None,
        custom_tags: list[str] | None = None,
    ) -> str:
        """Pick the kids vs adults campaign for a lead.

        Prefers the audience derived from the lead's tags/extra_data (the
        same logic that drives the UI tag pill). Falls back to email text
        keywords, then defaults to 'kids'.
        """
        from app.domain.services.lead_tagger import infer_audience

        audience = infer_audience(lead_extra_data)
        if audience == "Adult":
            return "adults"
        if audience in ("Child", "Child (under 3)"):
            return "kids"

        if custom_tags:
            tag_text = " ".join(t for t in custom_tags if isinstance(t, str)).lower()
            if "adult" in tag_text:
                return "adults"
            if any(kw in tag_text for kw in ("child", "kid", "under 3")):
                return "kids"

        text = f"{email_subject or ''} {email_body or ''}".lower()
        adult_keywords = ["adult", "young adult", "grown up", "18+", "over 18"]
        if any(kw in text for kw in adult_keywords):
            return "adults"
        return "kids"  # Default

    # ── Private Helpers ──────────────────────────────────────────────────

    async def _schedule_step(self, enrollment: DripEnrollment, delay_minutes: int) -> str | None:
        """Schedule the next drip step via Cloud Tasks."""
        return await self._schedule_step_raw(enrollment, delay_minutes * 60)

    async def _schedule_step_raw(self, enrollment: DripEnrollment, delay_seconds: int) -> str | None:
        """Schedule a drip step with raw seconds delay."""
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            logger.error("cloud_tasks_worker_url not configured")
            return None

        if worker_base_url.endswith("/process-sms"):
            worker_base_url = worker_base_url[:-12]
        task_url = f"{worker_base_url.rstrip('/')}/drip-step"

        try:
            cloud_tasks = CloudTasksClient()
            task_name = await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": enrollment.tenant_id,
                    "enrollment_id": enrollment.id,
                    "type": "advance",
                },
                url=task_url,
                delay_seconds=delay_seconds,
            )

            from datetime import timedelta
            enrollment.next_step_at = _naive_utcnow() + timedelta(seconds=delay_seconds)
            enrollment.next_task_id = task_name
            return task_name
        except Exception as e:
            logger.error(f"Failed to schedule drip step for enrollment {enrollment.id}: {e}")
            return None

    async def _schedule_resume_check(self, enrollment: DripEnrollment, delay_minutes: int) -> str | None:
        """Schedule a resume check for a responded enrollment."""
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            return None

        if worker_base_url.endswith("/process-sms"):
            worker_base_url = worker_base_url[:-12]
        task_url = f"{worker_base_url.rstrip('/')}/drip-step"

        try:
            cloud_tasks = CloudTasksClient()
            return await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": enrollment.tenant_id,
                    "enrollment_id": enrollment.id,
                    "type": "resume_check",
                },
                url=task_url,
                delay_seconds=delay_minutes * 60,
            )
        except Exception as e:
            logger.error(f"Failed to schedule resume check for enrollment {enrollment.id}: {e}")
            return None

    async def _send_sms(self, tenant_id: int, lead_id: int, message: str) -> bool:
        """Send an SMS to a lead. Returns True on success."""
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead or not lead.phone:
            return False

        factory = TelephonyProviderFactory(self.session)
        sms_config = await factory.get_config(tenant_id)
        if not sms_config or not sms_config.is_enabled:
            return False

        from_phone = factory.get_sms_phone_number(sms_config)
        sms_provider = await factory.get_sms_provider(tenant_id)
        if not from_phone or not sms_provider:
            return False

        status_callback_url = None
        if settings.api_base_url:
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.api_base_url}/api/v1/sms{webhook_prefix}/status"

        try:
            await sms_provider.send_sms(
                to=lead.phone,
                from_=from_phone,
                body=message,
                status_callback=status_callback_url,
            )

            # Store in conversation
            conversation_service = ConversationService(self.session)
            conv_external_id = f"drip-{lead_id}"
            conversation = await conversation_service.create_conversation(
                tenant_id=tenant_id, channel="sms", external_id=conv_external_id
            )
            # Link the conversation to the lead so the message surfaces in the
            # Lead Activity Timeline (loads convs via lead.conversation_id OR
            # lead.contact_id). Without this the message row is orphaned.
            from app.persistence.repositories.conversation_repository import ConversationRepository
            conv_repo = ConversationRepository(self.session)
            conv = await conv_repo.get_by_id(tenant_id, conversation.id)
            if conv:
                conv.phone_number = lead.phone
                if lead.contact_id and not conv.contact_id:
                    conv.contact_id = lead.contact_id
                if not lead.conversation_id:
                    lead.conversation_id = conversation.id
                await self.session.commit()
            await conversation_service.add_message(
                tenant_id, conversation.id, "assistant", message
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send drip SMS to lead {lead_id}: {e}")
            return False

    async def _send_registration_link(self, tenant_id: int, enrollment: DripEnrollment) -> str | None:
        """Send a registration link to a drip-enrolled lead. Returns reply message or None."""
        lead = await self.lead_repo.get_by_id(tenant_id, enrollment.lead_id)
        if not lead or not lead.phone:
            return None

        context = enrollment.context_data or {}
        registration_url = context.get("registration_url")

        if not registration_url:
            # Try to build one from context
            location_code = context.get("location_code")
            type_code = context.get("level")
            if location_code:
                try:
                    from app.utils.registration_url_builder import build_registration_url
                    registration_url = build_registration_url(
                        location_code, type_code, tenant_id=tenant_id
                    )
                except Exception as e:
                    logger.error(f"Failed to build registration URL: {e}")

        if registration_url:
            reply = f"Here's the link to complete your registration: {registration_url}"
        else:
            reply = "I'd love to help you complete your registration! Please visit our website or give us a call."

        sent = await self._send_sms(tenant_id, enrollment.lead_id, reply)
        return reply if sent else None
