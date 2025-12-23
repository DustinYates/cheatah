"""Voice configuration service for tenant voice settings."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_voice_config import (
    DEFAULT_ESCALATION_RULES,
    DEFAULT_NOTIFICATION_METHODS,
    TenantVoiceConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class VoiceConfigData:
    """Voice configuration data transfer object."""
    is_enabled: bool = False
    handoff_mode: str = "take_message"
    live_transfer_number: str | None = None
    escalation_rules: dict | None = None
    default_greeting: str | None = None
    disclosure_line: str | None = None
    notification_methods: list[str] | None = None
    notification_recipients: list[dict] | None = None
    after_hours_message: str | None = None


class VoiceConfigService:
    """Service for managing tenant voice configuration."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize voice config service.
        
        Args:
            session: Database session
        """
        self.session = session

    async def get_voice_config(self, tenant_id: int) -> TenantVoiceConfig | None:
        """Get voice configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TenantVoiceConfig or None if not configured
        """
        stmt = select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_voice_config(self, tenant_id: int) -> TenantVoiceConfig:
        """Get or create voice configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TenantVoiceConfig (existing or newly created with defaults)
        """
        config = await self.get_voice_config(tenant_id)
        
        if not config:
            config = TenantVoiceConfig(
                tenant_id=tenant_id,
                is_enabled=False,
                handoff_mode="take_message",
                escalation_rules=DEFAULT_ESCALATION_RULES,
                notification_methods=DEFAULT_NOTIFICATION_METHODS,
            )
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
            logger.info(f"Created default voice config for tenant {tenant_id}")
        
        return config

    async def update_voice_config(
        self,
        tenant_id: int,
        config_data: VoiceConfigData,
    ) -> TenantVoiceConfig:
        """Update voice configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            config_data: Configuration data to update
            
        Returns:
            Updated TenantVoiceConfig
        """
        config = await self.get_or_create_voice_config(tenant_id)
        
        # Update fields if provided
        if config_data.is_enabled is not None:
            config.is_enabled = config_data.is_enabled
        if config_data.handoff_mode is not None:
            config.handoff_mode = config_data.handoff_mode
        if config_data.live_transfer_number is not None:
            config.live_transfer_number = config_data.live_transfer_number
        if config_data.escalation_rules is not None:
            config.escalation_rules = config_data.escalation_rules
        if config_data.default_greeting is not None:
            config.default_greeting = config_data.default_greeting
        if config_data.disclosure_line is not None:
            config.disclosure_line = config_data.disclosure_line
        if config_data.notification_methods is not None:
            config.notification_methods = config_data.notification_methods
        if config_data.notification_recipients is not None:
            config.notification_recipients = config_data.notification_recipients
        if config_data.after_hours_message is not None:
            config.after_hours_message = config_data.after_hours_message
        
        await self.session.commit()
        await self.session.refresh(config)
        
        logger.info(f"Updated voice config for tenant {tenant_id}")
        return config

    async def get_handoff_config(self, tenant_id: int) -> dict[str, Any]:
        """Get handoff configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with handoff settings
        """
        config = await self.get_voice_config(tenant_id)
        
        if not config:
            return {
                "mode": "take_message",
                "transfer_number": None,
                "enabled": False,
            }
        
        return {
            "mode": config.handoff_mode,
            "transfer_number": config.live_transfer_number,
            "enabled": config.is_enabled,
        }

    async def get_escalation_rules(self, tenant_id: int) -> dict[str, Any]:
        """Get escalation rules for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with escalation rules
        """
        config = await self.get_voice_config(tenant_id)
        
        if not config or not config.escalation_rules:
            return DEFAULT_ESCALATION_RULES.copy()
        
        return config.escalation_rules

    async def get_notification_config(self, tenant_id: int) -> dict[str, Any]:
        """Get notification configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with notification settings
        """
        config = await self.get_voice_config(tenant_id)
        
        if not config:
            return {
                "methods": DEFAULT_NOTIFICATION_METHODS,
                "recipients": [],
            }
        
        return {
            "methods": config.notification_methods or DEFAULT_NOTIFICATION_METHODS,
            "recipients": config.notification_recipients or [],
        }

    async def get_greeting_and_disclosure(self, tenant_id: int) -> dict[str, str]:
        """Get greeting and disclosure text for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with greeting and disclosure text
        """
        config = await self.get_voice_config(tenant_id)
        
        default_greeting = (
            "Hello! Thank you for calling. I'm an AI assistant and I'm here to help you. "
            "How can I assist you today?"
        )
        default_disclosure = "This call may be recorded for quality and training purposes."
        default_after_hours = (
            "Thank you for calling. We're currently outside our business hours. "
            "Please leave a message after the tone, and we'll get back to you as soon as possible."
        )
        
        if not config:
            return {
                "greeting": default_greeting,
                "disclosure": default_disclosure,
                "after_hours_message": default_after_hours,
            }
        
        return {
            "greeting": config.default_greeting or default_greeting,
            "disclosure": config.disclosure_line or default_disclosure,
            "after_hours_message": config.after_hours_message or default_after_hours,
        }

