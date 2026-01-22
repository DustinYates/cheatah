"""Follow-up service for scheduling and managing SMS follow-up conversations."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.cloud_tasks import CloudTasksClient
from app.persistence.models.lead import Lead
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.lead_repository import LeadRepository
from app.settings import settings

logger = logging.getLogger(__name__)


class FollowUpService:
    """Service for managing SMS follow-up scheduling and execution."""

    # Default follow-up delay in minutes
    DEFAULT_DELAY_MINUTES = 5

    # Sources that trigger follow-up
    DEFAULT_FOLLOWUP_SOURCES = ["voice_call", "sms", "email", "chatbot"]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize follow-up service."""
        self.session = session
        self.lead_repo = LeadRepository(session)
        self.conversation_repo = ConversationRepository(session)

    async def should_schedule_followup(
        self,
        tenant_id: int,
        lead: Lead,
    ) -> bool:
        """Determine if a follow-up should be scheduled for this lead.

        Args:
            tenant_id: Tenant ID
            lead: Lead to evaluate

        Returns:
            True if follow-up should be scheduled
        """
        print(f"[FOLLOWUP_SHOULD] Checking lead {lead.id}, phone={lead.phone}", flush=True)

        # Check if lead has phone number
        if not lead.phone:
            print(f"[FOLLOWUP_SHOULD] Lead {lead.id} has no phone number, skipping", flush=True)
            logger.debug(f"Lead {lead.id} has no phone number, skipping follow-up")
            return False

        # Get tenant SMS config
        config = await self._get_sms_config(tenant_id)
        print(f"[FOLLOWUP_SHOULD] SMS config: enabled={config.is_enabled if config else None}, provider={config.provider if config else None}", flush=True)
        if not config or not config.is_enabled:
            print(f"[FOLLOWUP_SHOULD] SMS not enabled for tenant {tenant_id}", flush=True)
            logger.debug(f"SMS not enabled for tenant {tenant_id}")
            return False

        # Verify phone number is configured for the selected provider
        has_phone = self._has_sms_phone_number(config)
        print(f"[FOLLOWUP_SHOULD] Has SMS phone configured: {has_phone}", flush=True)
        if not has_phone:
            print(f"[FOLLOWUP_SHOULD] No SMS phone number configured for tenant {tenant_id} (provider: {config.provider})", flush=True)
            logger.debug(f"No SMS phone number configured for tenant {tenant_id} (provider: {config.provider})")
            return False

        # Check if follow-up is enabled in settings
        followup_enabled = False
        if config.settings:
            followup_enabled = config.settings.get("followup_enabled", False)
        print(f"[FOLLOWUP_SHOULD] Follow-up enabled in settings: {followup_enabled}", flush=True)
        if not followup_enabled:
            print(f"[FOLLOWUP_SHOULD] Follow-up not enabled for tenant {tenant_id}", flush=True)
            logger.debug(f"Follow-up not enabled for tenant {tenant_id}")
            return False

        # Check if source is in allowed sources
        source = lead.extra_data.get("source") if lead.extra_data else None
        allowed_sources = self.DEFAULT_FOLLOWUP_SOURCES
        if config.settings:
            allowed_sources = config.settings.get("followup_sources", self.DEFAULT_FOLLOWUP_SOURCES)
        print(f"[FOLLOWUP_SHOULD] Source: {source}, allowed: {allowed_sources}", flush=True)
        if source and source not in allowed_sources:
            print(f"[FOLLOWUP_SHOULD] Source {source} not in allowed sources", flush=True)
            logger.debug(f"Source {source} not in allowed sources for follow-up")
            return False

        # Check if follow-up already scheduled or sent
        if lead.extra_data:
            already_scheduled = lead.extra_data.get("followup_scheduled")
            already_sent = lead.extra_data.get("followup_sent_at")
            print(f"[FOLLOWUP_SHOULD] Already scheduled: {already_scheduled}, sent: {already_sent}", flush=True)
            if already_scheduled or already_sent:
                print(f"[FOLLOWUP_SHOULD] Follow-up already scheduled/sent for lead {lead.id}", flush=True)
                logger.debug(f"Follow-up already scheduled/sent for lead {lead.id}")
                return False

        print(f"[FOLLOWUP_SHOULD] All checks passed! Scheduling follow-up for lead {lead.id}", flush=True)
        return True

    async def schedule_followup(
        self,
        tenant_id: int,
        lead_id: int,
    ) -> str | None:
        """Schedule a follow-up SMS task.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            Cloud Task name if scheduled, None otherwise
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            logger.warning(f"Lead {lead_id} not found for follow-up scheduling")
            return None

        if not await self.should_schedule_followup(tenant_id, lead):
            return None

        # Get delay from config (check for subject-specific delay first)
        config = await self._get_sms_config(tenant_id)
        delay_minutes = self.DEFAULT_DELAY_MINUTES
        if config and config.settings:
            # Check for subject-specific delay based on email subject
            email_subject = lead.extra_data.get("email_subject", "") if lead.extra_data else ""
            subject_templates = config.settings.get("followup_subject_templates", {})

            subject_specific_delay = None
            if email_subject and subject_templates:
                for prefix, template_data in subject_templates.items():
                    if email_subject.lower().startswith(prefix.lower()):
                        # Support both old format (string) and new format (dict with message/delay)
                        if isinstance(template_data, dict):
                            subject_specific_delay = template_data.get("delay_minutes")
                        break

            if subject_specific_delay is not None:
                delay_minutes = subject_specific_delay
                logger.info(f"Using subject-specific delay of {delay_minutes} minutes for lead {lead_id}")
            else:
                # Fall back to global delay setting
                delay_minutes = config.settings.get("followup_delay_minutes", self.DEFAULT_DELAY_MINUTES)

        # Build worker URL
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            logger.warning("cloud_tasks_worker_url not configured, cannot schedule follow-up")
            return None

        # Remove /process-sms suffix if present and add /followup
        if worker_base_url.endswith("/process-sms"):
            worker_base_url = worker_base_url[:-12]  # Remove /process-sms
        task_url = f"{worker_base_url.rstrip('/')}/followup"

        # Schedule Cloud Task
        try:
            cloud_tasks = CloudTasksClient()
            task_name = await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": tenant_id,
                    "lead_id": lead_id,
                    "phone_number": lead.phone,
                },
                url=task_url,
                delay_seconds=delay_minutes * 60,
            )

            # Update lead extra_data
            extra_data = lead.extra_data or {}
            extra_data["followup_scheduled"] = True
            extra_data["followup_task_id"] = task_name
            extra_data["followup_scheduled_at"] = datetime.now(timezone.utc).isoformat()
            lead.extra_data = extra_data
            await self.session.commit()

            logger.info(f"Scheduled follow-up for lead {lead_id} in {delay_minutes} minutes: {task_name}")
            return task_name

        except Exception as e:
            logger.error(f"Failed to schedule follow-up task for lead {lead_id}: {e}", exc_info=True)
            return None

    async def trigger_immediate_followup(
        self,
        tenant_id: int,
        lead_id: int,
    ) -> tuple[str | None, str | None]:
        """Trigger an immediate follow-up SMS task (no delay).

        Used for manual follow-up triggers from the dashboard.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            Tuple of (task_name, error_message). If successful, error_message is None.
            If failed, task_name is None and error_message describes the issue.
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            logger.warning(f"Lead {lead_id} not found for immediate follow-up")
            return None, "Lead not found"

        if not lead.phone:
            logger.warning(f"Lead {lead_id} has no phone number")
            return None, "Lead has no phone number"

        # Check if already sent
        if lead.extra_data and lead.extra_data.get("followup_sent_at"):
            logger.info(f"Follow-up already sent for lead {lead_id}")
            return None, "Follow-up already sent"

        # Verify SMS is configured
        config = await self._get_sms_config(tenant_id)
        if not config:
            logger.warning(f"No SMS configuration found for tenant {tenant_id}")
            return None, "SMS not configured. Go to Settings > SMS to configure."

        if not config.is_enabled:
            logger.warning(f"SMS not enabled for tenant {tenant_id}")
            return None, "SMS is disabled. Enable it in Settings > SMS."

        if not self._has_sms_phone_number(config):
            provider = config.provider or "twilio"
            logger.warning(f"No SMS phone number configured for tenant {tenant_id} (provider: {provider})")
            return None, f"No {provider.title()} phone number assigned. Contact support to assign a number."

        # Build worker URL
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            logger.warning("cloud_tasks_worker_url not configured")
            return None, "Server misconfiguration: worker URL not set. Contact support."

        if worker_base_url.endswith("/process-sms"):
            worker_base_url = worker_base_url[:-12]
        task_url = f"{worker_base_url.rstrip('/')}/followup"

        # Schedule immediate task (0 delay)
        try:
            cloud_tasks = CloudTasksClient()
            task_name = await cloud_tasks.create_task_async(
                payload={
                    "tenant_id": tenant_id,
                    "lead_id": lead_id,
                    "phone_number": lead.phone,
                },
                url=task_url,
                delay_seconds=0,  # Immediate execution
            )

            # Update lead extra_data
            extra_data = lead.extra_data or {}
            extra_data["followup_scheduled"] = True
            extra_data["followup_task_id"] = task_name
            extra_data["followup_scheduled_at"] = datetime.now(timezone.utc).isoformat()
            extra_data["followup_triggered_manually"] = True
            lead.extra_data = extra_data
            await self.session.commit()

            logger.info(f"Triggered immediate follow-up for lead {lead_id}: {task_name}")
            return task_name, None

        except Exception as e:
            logger.error(f"Failed to trigger immediate follow-up for lead {lead_id}: {e}", exc_info=True)
            return None, f"Failed to schedule task: {str(e)}"

    async def _get_sms_config(self, tenant_id: int) -> TenantSmsConfig | None:
        """Get tenant SMS configuration."""
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _has_sms_phone_number(self, config: TenantSmsConfig) -> bool:
        """Check if the tenant has an SMS phone number configured for their provider.

        Args:
            config: Tenant SMS configuration

        Returns:
            True if a phone number is configured for the active provider
        """
        if config.provider == "telnyx":
            return bool(config.telnyx_phone_number)
        # Default to Twilio
        return bool(config.twilio_phone_number)
