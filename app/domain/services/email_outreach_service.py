"""Email outreach service for AI-generated cold outreach campaigns."""

import logging
import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.dnc_service import DncService
from app.domain.services.prompt_service import PromptService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.sendgrid_client import SendGridClient
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.email_campaign import EmailCampaign, EmailCampaignRecipient
from app.persistence.repositories.email_campaign_repository import (
    EmailCampaignRepository,
    EmailCampaignRecipientRepository,
)
from app.persistence.repositories.email_repository import TenantEmailConfigRepository
from app.settings import settings

logger = logging.getLogger(__name__)


class EmailOutreachService:
    """Service for generating and sending AI-powered cold outreach emails."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.campaign_repo = EmailCampaignRepository(session)
        self.recipient_repo = EmailCampaignRecipientRepository(session)
        self.prompt_service = PromptService(session)
        self.dnc_service = DncService(session)
        self.email_config_repo = TenantEmailConfigRepository(session)

    async def generate_email(
        self,
        tenant_id: int,
        recipient: EmailCampaignRecipient,
        campaign: EmailCampaign,
    ) -> tuple[str, str]:
        """Generate a personalized email using the tenant's AI voice.

        Args:
            tenant_id: Tenant ID
            recipient: The recipient to generate for
            campaign: The campaign config

        Returns:
            Tuple of (subject, html_body)
        """
        system_prompt = await self.prompt_service.compose_prompt_email_outreach(tenant_id)
        if not system_prompt:
            raise ValueError(f"No prompt config found for tenant {tenant_id}")

        user_prompt = self._build_generation_prompt(recipient, campaign)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        orchestrator = LLMOrchestrator()
        raw_response = await orchestrator.generate(full_prompt)

        subject, body = self._parse_email_response(raw_response, campaign)
        return subject, body

    async def preview_email(
        self,
        tenant_id: int,
        recipient: EmailCampaignRecipient,
        campaign: EmailCampaign,
    ) -> dict:
        """Generate a preview email without sending.

        Returns:
            Dict with subject, body, recipient info
        """
        subject, body = await self.generate_email(tenant_id, recipient, campaign)
        body_with_footer = self._append_compliance_footer(body, campaign)
        return {
            "subject": subject,
            "body": body_with_footer,
            "recipient_email": recipient.email,
            "recipient_name": recipient.name,
        }

    async def send_single(
        self,
        tenant_id: int,
        recipient: EmailCampaignRecipient,
        campaign: EmailCampaign,
    ) -> bool:
        """Generate and send a single outreach email.

        Returns:
            True if sent successfully, False otherwise
        """
        # DNC check
        if await self.dnc_service.is_blocked(tenant_id, email=recipient.email):
            recipient.status = "skipped"
            recipient.error_message = "Email on Do Not Contact list"
            await self.session.commit()
            logger.info(f"Skipped DNC-blocked recipient {recipient.email}")
            return False

        try:
            recipient.status = "generating"
            await self.session.commit()

            subject, body = await self.generate_email(tenant_id, recipient, campaign)
            html_body = self._append_compliance_footer(body, campaign)

            # Get SendGrid client with tenant credentials
            sendgrid = await self._get_sendgrid_client(tenant_id, campaign)

            result = await sendgrid.send_email(
                to_email=recipient.email,
                subject=subject,
                html_content=html_body,
                from_email=campaign.from_email,
                reply_to=campaign.reply_to,
            )

            recipient.status = "sent"
            recipient.generated_subject = subject
            recipient.generated_body = html_body
            recipient.sendgrid_message_id = result.get("message_id")
            recipient.sent_at = datetime.utcnow()
            await self.session.commit()

            logger.info(f"Sent outreach email to {recipient.email} for campaign {campaign.id}")
            return True

        except Exception as e:
            recipient.status = "failed"
            recipient.error_message = str(e)[:500]
            await self.session.commit()
            logger.error(f"Failed to send outreach email to {recipient.email}: {e}")
            return False

    async def send_batch(self, campaign_id: int) -> dict:
        """Send the next batch of emails for a campaign.

        Called by the Cloud Tasks worker. Returns stats dict.
        """
        campaign = await self.campaign_repo.get_by_id(None, campaign_id)
        if not campaign:
            return {"status": "error", "message": "Campaign not found"}

        if campaign.status not in ("scheduled", "sending"):
            return {"status": "skipped", "message": f"Campaign status is {campaign.status}"}

        # Mark as sending
        if campaign.status == "scheduled":
            campaign.status = "sending"
            await self.session.commit()

        # Get next batch
        recipients = await self.recipient_repo.get_pending_batch(
            campaign_id, campaign.batch_size
        )

        if not recipients:
            campaign.status = "completed"
            await self.session.commit()
            logger.info(f"Campaign {campaign_id} completed — no more pending recipients")
            return {"status": "completed", "sent": 0, "failed": 0, "remaining": 0}

        sent = 0
        failed = 0
        for recipient in recipients:
            success = await self.send_single(campaign.tenant_id, recipient, campaign)
            if success:
                sent += 1
            else:
                failed += 1

        # Update campaign counters
        await self.campaign_repo.increment_counters(campaign_id, sent=sent, failed=failed)

        # Check remaining
        status_counts = await self.recipient_repo.count_by_status(campaign_id)
        remaining = status_counts.get("pending", 0)

        if remaining > 0:
            # Schedule next batch
            await self._schedule_next_batch(campaign)
            logger.info(
                f"Campaign {campaign_id}: batch done (sent={sent}, failed={failed}), "
                f"{remaining} remaining — next batch in {campaign.batch_delay_seconds}s"
            )
        else:
            campaign.status = "completed"
            await self.session.commit()
            logger.info(f"Campaign {campaign_id} completed (sent={sent}, failed={failed})")

        return {
            "status": "batch_sent",
            "sent": sent,
            "failed": failed,
            "remaining": remaining,
        }

    async def trigger_campaign(self, campaign: EmailCampaign) -> str | None:
        """Trigger a campaign to start sending. Schedules the first batch via Cloud Tasks.

        Returns:
            Cloud Task name, or None if scheduling failed
        """
        # Update recipient count
        status_counts = await self.recipient_repo.count_by_status(campaign.id)
        total = sum(status_counts.values())
        campaign.total_recipients = total
        campaign.status = "scheduled"
        if not campaign.send_at:
            campaign.send_at = datetime.utcnow()
        await self.session.commit()

        return await self._schedule_next_batch(campaign, delay_seconds=0)

    async def pause_campaign(self, campaign: EmailCampaign) -> bool:
        """Pause a sending campaign."""
        if campaign.status not in ("scheduled", "sending"):
            return False
        campaign.status = "paused"
        await self.session.commit()
        logger.info(f"Campaign {campaign.id} paused")
        return True

    # ── Private helpers ──────────────────────────────────────────

    def _build_generation_prompt(
        self, recipient: EmailCampaignRecipient, campaign: EmailCampaign
    ) -> str:
        """Build the user-facing prompt for email generation."""
        parts = [
            "Generate a cold outreach email with the following details:",
            f"Subject line suggestion: {campaign.subject_template}",
        ]
        if recipient.name:
            parts.append(f"Recipient name: {recipient.name}")
        if recipient.company:
            parts.append(f"Recipient company: {recipient.company}")
        if recipient.role:
            parts.append(f"Recipient role: {recipient.role}")
        if campaign.email_prompt_instructions:
            parts.append(f"Special instructions: {campaign.email_prompt_instructions}")
        if recipient.personalization_data:
            for key, value in recipient.personalization_data.items():
                parts.append(f"{key}: {value}")
        parts.append(
            "\nRespond with ONLY:\nSUBJECT: <subject line>\nBODY:\n<html email body>"
        )
        return "\n".join(parts)

    def _parse_email_response(
        self, raw_response: str, campaign: EmailCampaign
    ) -> tuple[str, str]:
        """Parse LLM response into subject and body.

        Expected format:
            SUBJECT: <subject>
            BODY:
            <html body>
        """
        subject = campaign.subject_template
        body = raw_response

        # Try to extract SUBJECT:
        subject_match = re.search(r"SUBJECT:\s*(.+?)(?:\n|$)", raw_response, re.IGNORECASE)
        if subject_match:
            subject = subject_match.group(1).strip()

        # Try to extract BODY:
        body_match = re.search(r"BODY:\s*\n(.*)", raw_response, re.IGNORECASE | re.DOTALL)
        if body_match:
            body = body_match.group(1).strip()

        # Clean up — remove markdown code fences if LLM wrapped HTML in them
        body = re.sub(r"^```html?\s*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body)

        return subject, body

    def _append_compliance_footer(self, html_body: str, campaign: EmailCampaign) -> str:
        """Append CAN-SPAM compliant footer to email body."""
        footer = (
            '<br><br>'
            '<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">'
            '<p style="font-size:12px;color:#888;line-height:1.4;">'
            f'{campaign.physical_address}<br>'
            f'<a href="{campaign.unsubscribe_url}" style="color:#888;">Unsubscribe</a>'
            '</p>'
        )
        # Insert before closing </body> if present
        if "</body>" in html_body.lower():
            idx = html_body.lower().index("</body>")
            return html_body[:idx] + footer + html_body[idx:]
        return html_body + footer

    async def _get_sendgrid_client(
        self, tenant_id: int, campaign: EmailCampaign
    ) -> SendGridClient:
        """Get SendGrid client with tenant-specific or global credentials."""
        email_config = await self.email_config_repo.get_by_tenant_id(tenant_id)
        if email_config and email_config.sendgrid_api_key:
            return SendGridClient(
                api_key=email_config.sendgrid_api_key,
                from_email=campaign.from_email or email_config.sendgrid_from_email,
            )
        # Fall back to global
        return SendGridClient(from_email=campaign.from_email)

    async def _schedule_next_batch(
        self, campaign: EmailCampaign, delay_seconds: int | None = None
    ) -> str | None:
        """Schedule the next batch send via Cloud Tasks."""
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            logger.error("cloud_tasks_worker_url not configured — cannot schedule batch")
            return None

        if worker_base_url.endswith("/process-sms"):
            worker_base_url = worker_base_url[:-12]
        task_url = f"{worker_base_url.rstrip('/')}/email-outreach"

        if delay_seconds is None:
            delay_seconds = campaign.batch_delay_seconds

        try:
            cloud_tasks = CloudTasksClient()
            task_name = await cloud_tasks.create_task_async(
                payload={
                    "campaign_id": campaign.id,
                    "type": "send_batch",
                },
                url=task_url,
                delay_seconds=delay_seconds,
            )
            logger.info(f"Scheduled next batch for campaign {campaign.id} in {delay_seconds}s")
            return task_name
        except Exception as e:
            logger.error(f"Failed to schedule batch for campaign {campaign.id}: {e}")
            return None
