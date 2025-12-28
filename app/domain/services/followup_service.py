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
    DEFAULT_FOLLOWUP_SOURCES = ["voice_call", "sms", "email"]

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
        # Check if lead has phone number
        if not lead.phone:
            logger.debug(f"Lead {lead.id} has no phone number, skipping follow-up")
            return False

        # Get tenant SMS config
        config = await self._get_sms_config(tenant_id)
        if not config or not config.is_enabled:
            logger.debug(f"SMS not enabled for tenant {tenant_id}")
            return False

        # Verify phone number is configured for the selected provider
        if not self._has_sms_phone_number(config):
            logger.debug(f"No SMS phone number configured for tenant {tenant_id} (provider: {config.provider})")
            return False

        # Check if follow-up is enabled in settings
        followup_enabled = False
        if config.settings:
            followup_enabled = config.settings.get("followup_enabled", False)
        if not followup_enabled:
            logger.debug(f"Follow-up not enabled for tenant {tenant_id}")
            return False

        # Check if source is in allowed sources
        source = lead.extra_data.get("source") if lead.extra_data else None
        allowed_sources = self.DEFAULT_FOLLOWUP_SOURCES
        if config.settings:
            allowed_sources = config.settings.get("followup_sources", self.DEFAULT_FOLLOWUP_SOURCES)
        if source and source not in allowed_sources:
            logger.debug(f"Source {source} not in allowed sources for follow-up")
            return False

        # Check if follow-up already scheduled or sent
        if lead.extra_data:
            if lead.extra_data.get("followup_scheduled") or lead.extra_data.get("followup_sent_at"):
                logger.debug(f"Follow-up already scheduled/sent for lead {lead.id}")
                return False

        # Check if lead already has an active SMS conversation (within last 24 hours)
        existing_conv = await self.conversation_repo.get_by_phone_number(
            tenant_id, lead.phone, channel="sms"
        )
        if existing_conv and existing_conv.updated_at:
            hours_since_update = (datetime.utcnow() - existing_conv.updated_at).total_seconds() / 3600
            if hours_since_update < 24:
                logger.debug(f"Lead {lead.id} has recent SMS conversation, skipping follow-up")
                return False

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

        # Get delay from config
        config = await self._get_sms_config(tenant_id)
        delay_minutes = self.DEFAULT_DELAY_MINUTES
        if config and config.settings:
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
    ) -> str | None:
        """Trigger an immediate follow-up SMS task (no delay).

        Used for manual follow-up triggers from the dashboard.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            Cloud Task name if scheduled, None otherwise
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            logger.warning(f"Lead {lead_id} not found for immediate follow-up")
            return None

        if not lead.phone:
            logger.warning(f"Lead {lead_id} has no phone number")
            return None

        # Check if already sent
        if lead.extra_data and lead.extra_data.get("followup_sent_at"):
            logger.info(f"Follow-up already sent for lead {lead_id}")
            return None

        # Verify SMS is configured
        config = await self._get_sms_config(tenant_id)
        if not config or not config.is_enabled:
            logger.warning(f"SMS not enabled for tenant {tenant_id}")
            return None

        if not self._has_sms_phone_number(config):
            logger.warning(f"No SMS phone number configured for tenant {tenant_id}")
            return None

        # Build worker URL
        worker_base_url = settings.cloud_tasks_worker_url
        if not worker_base_url:
            logger.warning("cloud_tasks_worker_url not configured")
            return None

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
            return task_name

        except Exception as e:
            logger.error(f"Failed to trigger immediate follow-up for lead {lead_id}: {e}", exc_info=True)
            return None

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
