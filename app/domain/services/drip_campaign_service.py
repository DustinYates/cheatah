"""Service for managing drip campaign enrollment, step execution, and response handling."""

import logging
from datetime import datetime, timezone

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

        # Create enrollment
        enrollment = DripEnrollment(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            lead_id=lead_id,
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

        # Schedule first step
        delay_minutes = campaign.trigger_delay_minutes or 10
        task_id = await self._schedule_step(enrollment, delay_minutes)
        if task_id:
            enrollment.next_task_id = task_id
            enrollment.next_step_at = datetime.now(timezone.utc)
            await self.session.commit()

        logger.info(
            f"Enrolled lead {lead_id} in drip campaign {campaign.id} ({campaign_type}), "
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
            enrollment.updated_at = datetime.now(timezone.utc)
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
        if settings.twilio_webhook_url_base:
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.twilio_webhook_url_base}/api/v1/sms{webhook_prefix}/status"

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

        # Update enrollment
        enrollment.current_step = next_step_num
        enrollment.updated_at = datetime.now(timezone.utc)

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
        enrollment.updated_at = datetime.now(timezone.utc)

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
        enrollment.updated_at = datetime.now(timezone.utc)
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
        enrollment.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        logger.info(f"Resuming drip enrollment {enrollment_id} after response timeout")
        return await self.advance_step(enrollment_id)

    # ── Campaign Type Detection ──────────────────────────────────────────

    @staticmethod
    def detect_campaign_type(email_subject: str | None, email_body: str | None) -> str:
        """Detect whether to use kids or adults campaign based on email content."""
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
            enrollment.next_step_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
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
        if settings.twilio_webhook_url_base:
            webhook_prefix = factory.get_webhook_path_prefix(sms_config)
            status_callback_url = f"{settings.twilio_webhook_url_base}/api/v1/sms{webhook_prefix}/status"

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
