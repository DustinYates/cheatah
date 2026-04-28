"""Service for managing drip campaign enrollment, step execution, and response handling."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _seconds_until_send_window(tz_name: str, start_hhmm: str, end_hhmm: str) -> int:
    """Return 0 if `now` (in tz_name) is inside [start, end), else seconds to wait
    until the next window opens. Both bounds are HH:MM strings in the same tz.
    """
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    try:
        sh, sm = int(start_hhmm[:2]), int(start_hhmm[3:])
        eh, em = int(end_hhmm[:2]), int(end_hhmm[3:])
    except (ValueError, IndexError):
        sh, sm, eh, em = 8, 0, 21, 0
    now = datetime.now(tz)
    start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if start_today <= now < end_today:
        return 0
    target = start_today if now < start_today else start_today + timedelta(days=1)
    return max(60, int((target - now).total_seconds()))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.conversation_service import ConversationService
from app.domain.services.dnc_service import DncService
from app.domain.services.drip_message_service import DripMessageService
from app.domain.services.opt_in_service import OptInService
from app.infrastructure.cloud_tasks import CloudTasksClient
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
        """Enroll a lead in a drip campaign by legacy type ('kids'/'adults').

        Returns None if no matching campaign, campaign disabled, or already
        enrolled. Prefer enroll_lead_auto for new code paths.
        """
        campaign = await self.campaign_repo.get_by_type(tenant_id, campaign_type)
        if not campaign:
            logger.debug(f"No {campaign_type} campaign found for tenant {tenant_id}")
            return None

        return await self._enroll_in_campaign(
            tenant_id=tenant_id,
            lead_id=lead_id,
            campaign=campaign,
            context_data=context_data,
        )

    async def _enroll_in_campaign(
        self,
        tenant_id: int,
        lead_id: int,
        campaign: DripCampaign,
        context_data: dict | None = None,
    ) -> DripEnrollment | None:
        """Shared enrollment logic. Caller has already picked the campaign."""
        if not campaign.is_enabled:
            logger.debug(f"Campaign {campaign.id} ({campaign.name}) is disabled for tenant {tenant_id}")
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

        enrollment = DripEnrollment(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            lead_id=lead_id,
            status="active",
            current_step=0,
            context_data=context_data or {},
        )
        self.session.add(enrollment)

        extra_data = dict(lead.extra_data or {})
        extra_data["drip_enrolled"] = True
        if "drip_enrollment_ids" not in extra_data:
            extra_data["drip_enrollment_ids"] = []
        lead.extra_data = extra_data
        await self.session.commit()
        await self.session.refresh(enrollment)

        extra_data = dict(lead.extra_data or {})
        extra_data.setdefault("drip_enrollment_ids", []).append(enrollment.id)
        lead.extra_data = extra_data
        await self.session.commit()

        delay_minutes = campaign.trigger_delay_minutes or 10
        task_id = await self._schedule_step(enrollment, delay_minutes)
        if task_id:
            enrollment.next_task_id = task_id
            enrollment.next_step_at = datetime.utcnow()
            await self.session.commit()

        logger.info(
            f"Enrolled lead {lead_id} in drip campaign {campaign.id} ({campaign.name}), "
            f"enrollment={enrollment.id}, first step in {delay_minutes} min"
        )
        return enrollment

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
            enrollment.updated_at = datetime.utcnow()
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

        # If the lead has already become enrolled (via Jackrabbit customer match
        # or a manual stage move), halt the drip — we never message enrolled
        # leads. Customer-match short-circuit below covers the live-data path;
        # this catches leads whose pipeline_stage was set to "enrolled" by any
        # other means.
        if lead.pipeline_stage == "enrolled":
            enrollment.status = "completed"
            enrollment.cancelled_reason = "already_enrolled"
            enrollment.next_task_id = None
            enrollment.next_step_at = None
            enrollment.updated_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Drip enrollment {enrollment_id}: lead {lead.id} already "
                f"pipeline_stage=enrolled — drip halted, no SMS sent."
            )
            return {"status": "completed", "reason": "already_enrolled"}

        # Pipeline-impact gate: tenants without pipelines (or who don't want
        # drips touching stages) can opt out via tenant_business_profiles.
        # When off, the drip behaves as a plain N-message linear sequence —
        # no customer-match divert, no missed-terminal, no stage updates.
        affects_pipeline = await self._tenant_drip_affects_pipeline(tenant_id)

        # Resolve tenant timezone up front so note timestamps render in local
        # time even on branches that exit before sms_config is required.
        factory = TelephonyProviderFactory(self.session)
        sms_config = await factory.get_config(tenant_id)
        tz_name = (sms_config.timezone if sms_config else None) or "UTC"

        # Customer-match check: if the lead has become a Jackrabbit customer at
        # any point during the drip, silently complete the enrollment and pin
        # the lead to "enrolled" — no SMS is sent. If no match AND this is the
        # final step, mark the lead "missed" and don't send anything.
        if affects_pipeline:
            # Trigger a live Jackrabbit lookup so we catch leads who registered
            # between drip steps. The customers table is populated only by
            # Zapier callbacks (no scheduled sync), so without this a fresh
            # enrollment looks like a non-customer until something else queries
            # them. lookup_by_phone is a fast no-op for tenants without Zapier
            # configured (returns "not enabled" without hitting the network).
            if lead.phone:
                try:
                    from app.domain.services.customer_lookup_service import CustomerLookupService
                    await CustomerLookupService(self.session).lookup_by_phone(
                        tenant_id=tenant_id,
                        phone_number=lead.phone,
                        use_cache=True,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Pre-drip Jackrabbit lookup failed for lead {lead.id} "
                        f"(enrollment {enrollment_id}): {exc} — falling back to "
                        f"local customers table only.",
                        exc_info=True,
                    )

            from app.persistence.repositories.customer_repository import CustomerRepository
            customer_match = await CustomerRepository(self.session).get_by_phone(tenant_id, lead.phone)
        else:
            customer_match = None
        last_step = max(campaign.steps, key=lambda s: s.step_number)
        is_last_step = step.step_number == last_step.step_number

        if customer_match:
            try:
                await self._set_pipeline_stage_if_exists(tenant_id, lead, "enrolled")
                self._append_drip_note(
                    lead,
                    "drip campaign ended — lead became a customer (silent enroll)",
                    tz_name=tz_name,
                )
            except Exception as e:
                logger.error(
                    f"Failed to mark lead {lead.id} enrolled for enrollment {enrollment_id}: {e}",
                    exc_info=True,
                )
            enrollment.status = "completed"
            enrollment.cancelled_reason = "customer_enrolled"
            enrollment.next_task_id = None
            enrollment.next_step_at = None
            enrollment.current_step = next_step_num
            enrollment.updated_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Drip enrollment {enrollment_id}: customer match — lead {lead.id} "
                f"silently marked enrolled, enrollment completed (no SMS sent)."
            )
            return {"status": "completed", "reason": "enrolled"}

        if affects_pipeline and is_last_step:
            # No message — final step reached without conversion.
            try:
                await self._set_pipeline_stage_if_exists(tenant_id, lead, "missed")
                self._append_drip_note(
                    lead,
                    "drip campaign ended — lead missed (no enrollment)",
                    tz_name=tz_name,
                )
            except Exception as e:
                logger.error(
                    f"Failed to mark lead {lead.id} missed for enrollment {enrollment_id}: {e}",
                    exc_info=True,
                )
            enrollment.status = "completed"
            enrollment.cancelled_reason = "missed_no_conversion"
            enrollment.next_task_id = None
            enrollment.next_step_at = None
            enrollment.current_step = next_step_num
            enrollment.updated_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Drip enrollment {enrollment_id}: final step reached without "
                f"customer match — lead {lead.id} marked missed, enrollment completed."
            )
            return {"status": "completed", "reason": "missed"}

        # SMS config required from here down (already loaded at top for tz)
        if not sms_config or not sms_config.is_enabled:
            return {"status": "skipped", "reason": "sms_not_enabled"}

        # Send-window check (per-campaign)
        window_start = campaign.send_window_start or "08:00"
        window_end = campaign.send_window_end or "21:00"
        defer_seconds = _seconds_until_send_window(tz_name, window_start, window_end)
        if defer_seconds > 0:
            logger.info(
                f"Outside send window {window_start}-{window_end} ({tz_name}) "
                f"for enrollment {enrollment_id}, deferring {defer_seconds}s"
            )
            await self._schedule_step_raw(enrollment, defer_seconds)
            return {"status": "deferred", "reason": "send_window", "seconds": defer_seconds}

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

        # Empty template → use a generic follow-up so the drip never locks up.
        # Step 1 gets a softer first-touch line; later steps get a circle-back.
        if not message:
            default_template = (
                "Hi {{first_name}}! Just following up on your interest. "
                "Happy to answer any questions whenever works for you."
                if next_step_num == 1
                else "Hi {{first_name}}, circling back to see if you have any questions. Reply anytime!"
            )
            message = self.message_service.render_template(default_template, context)
            logger.info(
                f"Empty message_template for enrollment {enrollment_id} step "
                f"{next_step_num} — using default fallback."
            )

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

        # Send SMS
        send_result = await sms_provider.send_sms(
            to=lead.phone,
            from_=from_phone,
            body=message,
            status_callback=status_callback_url,
        )

        # Store in conversation
        conversation_service = ConversationService(self.session)
        # Create or reuse conversation
        conv_external_id = f"drip-{enrollment.id}"
        conversation = await conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="sms",
            external_id=conv_external_id,
        )
        # Set phone on conversation
        from app.persistence.repositories.conversation_repository import ConversationRepository
        conv_repo = ConversationRepository(self.session)
        conv = await conv_repo.get_by_id(tenant_id, conversation.id)
        if conv:
            conv.phone_number = lead.phone
            await self.session.commit()

        await conversation_service.add_message(
            tenant_id, conversation.id, "assistant", message
        )

        # Normal drip step: append note. Advance pipeline stage by +1 only if
        # the tenant allows drip-driven pipeline changes.
        try:
            if affects_pipeline:
                await self._record_drip_send_on_lead(
                    tenant_id=tenant_id,
                    lead=lead,
                    step_number=next_step_num,
                    message=message,
                    tz_name=tz_name,
                )
            else:
                self._append_drip_note(
                    lead,
                    f"drip campaign step {next_step_num}: {message}",
                    tz_name=tz_name,
                )
        except Exception as e:
            logger.error(
                f"Failed to record drip note/pipeline-advance for lead {lead.id} "
                f"enrollment {enrollment_id}: {e}",
                exc_info=True,
            )

        enrollment.current_step = next_step_num
        enrollment.updated_at = datetime.utcnow()

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
        enrollment.updated_at = datetime.utcnow()

        # Score signal: a reply at touch N where N is enrollment.current_step
        # (the step that was last sent before this response).
        try:
            from app.domain.services.lead_scoring_service import (
                record_signal as _record_score_signal,
                recompute_and_persist as _recompute_score,
            )
            lead_for_score = await self.lead_repo.get_by_id(tenant_id, lead_id)
            if lead_for_score and enrollment.current_step:
                _record_score_signal(
                    lead_for_score,
                    drip_reply_touch=enrollment.current_step,
                    replied_to_outbound=True,
                    channel="sms",
                )
                await _recompute_score(self.session, lead_for_score)
        except Exception as e:
            logger.error(f"Failed to record drip-reply score signal for lead {lead_id}: {e}")

        template_data = response_templates.get(category, {})
        action = template_data.get("action")

        # Hard-cancel only on explicit cancel_drip action (e.g., STOP keyword
        # routed through this path). "not_interested" is a soft signal —
        # treat it like other soft replies (pause + resume) per product
        # policy: keep dripping unless they tell us to stop, sign up, or
        # exhaust the configured steps.
        if action == "cancel_drip":
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = "stop_keyword"
            await self.session.commit()
            return {"handled": False, "reason": "stop_keyword_let_ai_handle"}

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
        enrollment.updated_at = datetime.utcnow()
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
        enrollment.updated_at = datetime.utcnow()
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

    # ── Tag-based Campaign Routing ───────────────────────────────────────

    @staticmethod
    def _build_lead_tag_set(lead) -> set[str]:
        """Build the lowercased set of tags for matching against a campaign's tag_filter.

        Includes:
          - auto-derived tags (audience, ZIP, location, class, source/UTM)
          - operator-set custom_tags
          - the lead's pipeline_stage rendered as a friendly label
            (e.g. "lost_opportunity" → "lost opportunity"), so a campaign
            with tag_filter=["Lost Opportunity"] matches leads in that
            pipeline stage without needing a duplicate manual tag.
          - the lead's status string, similarly rendered
        """
        from app.domain.services.lead_tagger import derive_tags

        tags: set[str] = set()
        for t in derive_tags(lead.extra_data, lead.custom_tags):
            value = t.get("value")
            if isinstance(value, str) and value.strip():
                tags.add(value.strip().lower())

        for slug in (getattr(lead, "pipeline_stage", None), getattr(lead, "status", None)):
            if isinstance(slug, str) and slug.strip():
                normalized = slug.strip().lower()
                tags.add(normalized)
                tags.add(normalized.replace("_", " "))
                tags.add(normalized.replace("-", " "))

        return tags

    @staticmethod
    def _audience_filter_matches(audience_filter: str | None, audience: str | None) -> bool:
        """Check if a campaign's audience_filter accepts a lead's inferred audience.

        Allowed values:
          - None / "" / "any": match any audience (or no audience)
          - "adult": matches "Adult"
          - "child": matches "Child" or "Child (under 3)"
          - "under_3": matches only "Child (under 3)"
        """
        if not audience_filter or audience_filter == "any":
            return True

        audience = audience or ""
        if audience_filter == "adult":
            return audience == "Adult"
        if audience_filter == "child":
            return audience in ("Child", "Child (under 3)")
        if audience_filter == "under_3":
            return audience == "Child (under 3)"
        return False

    async def pick_campaign_for_lead(self, tenant_id: int, lead) -> DripCampaign | None:
        """Pick the best-matching enabled drip campaign for a lead.

        Iterates all enabled campaigns sorted by priority (lower wins),
        returns the first whose audience_filter and tag_filter both match.
        Falls back to the legacy kids/adults campaign_type lookup so
        existing tenants keep working without configuring new fields.
        """
        from app.domain.services.lead_tagger import infer_audience

        audience = infer_audience(lead.extra_data if lead else None)
        lead_tags = self._build_lead_tag_set(lead) if lead else set()

        all_campaigns = await self.campaign_repo.list_with_steps(tenant_id)
        candidates = sorted(
            (c for c in all_campaigns if c.is_enabled and c.steps),
            key=lambda c: (c.priority or 100, c.id),
        )

        for campaign in candidates:
            if not self._audience_filter_matches(campaign.audience_filter, audience):
                continue

            tag_filter = campaign.tag_filter or []
            if tag_filter:
                required = {str(t).strip().lower() for t in tag_filter if t}
                if not required.issubset(lead_tags):
                    continue

            return campaign

        # Legacy fallback: campaigns predating the filter columns
        legacy_type = self.detect_campaign_type(
            lead_extra_data=lead.extra_data if lead else None,
            custom_tags=lead.custom_tags if lead else None,
        )
        legacy = await self.campaign_repo.get_by_type(tenant_id, legacy_type)
        if legacy and legacy.is_enabled and legacy.steps:
            return legacy
        return None

    async def enroll_lead_auto(
        self,
        tenant_id: int,
        lead_id: int,
        context_data: dict | None = None,
    ) -> DripEnrollment | None:
        """Pick the best-matching campaign for a lead and enroll them.

        Returns None if no campaign matches, lead is ineligible, or already
        enrolled.
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            return None

        campaign = await self.pick_campaign_for_lead(tenant_id, lead)
        if not campaign:
            logger.debug(f"No matching drip campaign for lead {lead_id}")
            return None

        return await self._enroll_in_campaign(
            tenant_id=tenant_id,
            lead_id=lead_id,
            campaign=campaign,
            context_data=context_data,
        )

    async def maybe_auto_enroll(
        self,
        tenant_id: int,
        lead_id: int,
        source: str,
        extra_context: dict | None = None,
    ) -> DripEnrollment | None:
        """Enroll lead in a drip if the tenant has auto_enroll_new_leads turned on.

        Gated by tenant_business_profiles.auto_enroll_new_leads (default false).
        Idempotent — short-circuits if lead is already enrolled. Errors are
        swallowed so lead creation is never blocked.
        """
        from app.persistence.models.tenant import TenantBusinessProfile

        try:
            result = await self.session.execute(
                select(TenantBusinessProfile.auto_enroll_new_leads).where(
                    TenantBusinessProfile.tenant_id == tenant_id
                )
            )
            flag = result.scalar_one_or_none()
            if not flag:
                return None

            context = {"source": source}
            if extra_context:
                context.update(extra_context)

            return await self.enroll_lead_auto(
                tenant_id=tenant_id,
                lead_id=lead_id,
                context_data=context,
            )
        except Exception as e:
            logger.error(
                f"maybe_auto_enroll failed for tenant={tenant_id} lead={lead_id} "
                f"source={source}: {e}",
                exc_info=True,
            )
            return None

    # ── Private Helpers ──────────────────────────────────────────────────

    async def _tenant_drip_affects_pipeline(self, tenant_id: int) -> bool:
        """Read the per-tenant flag controlling whether drips mutate pipeline_stage.

        Defaults to True on read errors / missing rows so behavior matches the
        pre-flag baseline.
        """
        from app.persistence.models.tenant import TenantBusinessProfile

        try:
            result = await self.session.execute(
                select(TenantBusinessProfile.drip_affects_pipeline).where(
                    TenantBusinessProfile.tenant_id == tenant_id
                )
            )
            value = result.scalar_one_or_none()
            return True if value is None else bool(value)
        except Exception as e:
            logger.warning(
                f"Could not read drip_affects_pipeline for tenant {tenant_id}: {e}; "
                f"defaulting to True"
            )
            return True

    def _append_drip_note(self, lead, body: str, tz_name: str = "UTC") -> None:
        """Append a timestamped note line to lead.notes (rendered in tz_name)."""
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %I:%M %p %Z")
        new_line = f"{timestamp} - {body}"
        existing = (lead.notes or "").rstrip()
        lead.notes = f"{existing}\n{new_line}" if existing else new_line

    async def _set_pipeline_stage_if_exists(
        self, tenant_id: int, lead, stage_key: str
    ) -> bool:
        """Set lead.pipeline_stage to a specific key only if that stage exists.

        Returns True if set, False if the tenant doesn't have that stage configured.
        """
        from app.persistence.models.tenant_pipeline_stage import TenantPipelineStage

        result = await self.session.execute(
            select(TenantPipelineStage.key).where(
                TenantPipelineStage.tenant_id == tenant_id,
                TenantPipelineStage.key == stage_key,
            )
        )
        if result.scalar_one_or_none() is None:
            logger.warning(
                f"Tenant {tenant_id} has no pipeline stage '{stage_key}' — "
                f"leaving lead {lead.id} stage unchanged."
            )
            return False
        old = lead.pipeline_stage
        lead.pipeline_stage = stage_key
        logger.info(f"Drip set lead {lead.id} pipeline_stage: {old} → {stage_key}")
        return True

    async def _record_drip_send_on_lead(
        self,
        tenant_id: int,
        lead,
        step_number: int,
        message: str,
        tz_name: str = "UTC",
    ) -> None:
        """Append a timestamped note + advance the lead's pipeline stage.

        Note format: "YYYY-MM-DD HH:MM - drip campaign step N: <message>"
        Pipeline advance: moves to next stage by position; no-op if already at
        the final stage or if no stages are configured.
        """
        from app.domain.services.lead_scoring_service import (
            record_signal as _record_score_signal,
            recompute_and_persist as _recompute_score,
        )
        from app.persistence.models.tenant_pipeline_stage import TenantPipelineStage

        # 0. Record drip-send signal so scoring can decay if unanswered.
        _record_score_signal(lead, drip_sent=True)

        # 1. Append note (preserve existing) in tenant-local time.
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %I:%M %p %Z")
        new_line = f"{timestamp} - drip campaign step {step_number}: {message}"
        existing = (lead.notes or "").rstrip()
        lead.notes = f"{existing}\n{new_line}" if existing else new_line

        await _recompute_score(self.session, lead)

        # 2. Advance pipeline stage.
        stages_result = await self.session.execute(
            select(TenantPipelineStage)
            .where(TenantPipelineStage.tenant_id == tenant_id)
            .order_by(TenantPipelineStage.position)
        )
        stages = list(stages_result.scalars().all())
        if not stages:
            return

        keys = [s.key for s in stages]
        current = lead.pipeline_stage
        if current in keys:
            idx = keys.index(current)
            if idx < len(keys) - 1:
                next_key = keys[idx + 1]
                # Outcome stages are externally determined (enrolled = Jackrabbit
                # customer match; missed = drip-final fallback). Auto-advance
                # must never land on them — hold the lead's current stage.
                if next_key in {"enrolled", "missed"}:
                    logger.info(
                        f"Drip skipped advance for lead {lead.id}: next stage "
                        f"'{next_key}' is outcome-only — staying at {current!r}"
                    )
                else:
                    lead.pipeline_stage = next_key
                    logger.info(
                        f"Drip advanced lead {lead.id} pipeline_stage: "
                        f"{current} → {lead.pipeline_stage}"
                    )
        else:
            # Lead has unknown/null stage — drop them on the first stage,
            # unless that first stage is itself an outcome (misconfig safety).
            first_key = keys[0]
            if first_key in {"enrolled", "missed"}:
                logger.warning(
                    f"Drip refused to set lead {lead.id} stage to outcome key "
                    f"'{first_key}' (pipeline misconfigured); leaving as {current!r}"
                )
            else:
                lead.pipeline_stage = first_key
                logger.info(f"Drip set lead {lead.id} pipeline_stage to {first_key} (was {current!r})")

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
            enrollment.next_step_at = datetime.utcnow() + timedelta(seconds=delay_seconds)

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
