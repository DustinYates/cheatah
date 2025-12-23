"""Voice configuration service for tenant voice settings."""

import logging
import time
from dataclasses import dataclass
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_voice_config import (
    DEFAULT_ESCALATION_RULES,
    DEFAULT_NOTIFICATION_METHODS,
    TenantVoiceConfig,
)

logger = logging.getLogger(__name__)


class VoiceConfigCache:
    """In-memory cache for voice configurations with short TTL.
    
    Reduces database queries for frequently accessed voice configs
    during active calls. Uses a shorter TTL than prompt cache since
    voice settings may need to be updated more frequently.
    """
    
    # Cache structure: {cache_key: (config_dict, timestamp)}
    _cache: ClassVar[dict[str, tuple[dict, float]]] = {}
    _ttl_seconds: ClassVar[int] = 60  # 1 minute cache TTL for voice configs
    
    @classmethod
    def get(cls, key: str) -> dict | None:
        """Get cached config if not expired."""
        if key in cls._cache:
            config, timestamp = cls._cache[key]
            if time.time() - timestamp < cls._ttl_seconds:
                return config
            # Expired - remove from cache
            del cls._cache[key]
        return None
    
    @classmethod
    def set(cls, key: str, config: dict) -> None:
        """Cache a config with current timestamp."""
        cls._cache[key] = (config, time.time())
    
    @classmethod
    def invalidate(cls, tenant_id: int | None = None) -> None:
        """Invalidate cache entries for a tenant, or all if tenant_id is None."""
        if tenant_id is None:
            cls._cache.clear()
        else:
            # Remove all keys containing this tenant_id
            keys_to_remove = [k for k in cls._cache if f"tenant:{tenant_id}" in k]
            for key in keys_to_remove:
                del cls._cache[key]


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
        
        # Invalidate cache for this tenant
        VoiceConfigCache.invalidate(tenant_id)
        
        logger.info(f"Updated voice config for tenant {tenant_id}")
        return config

    async def get_handoff_config(self, tenant_id: int) -> dict[str, Any]:
        """Get handoff configuration for a tenant.
        
        Uses caching to reduce database queries during active calls.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with handoff settings
        """
        # Check cache first
        cache_key = f"handoff:tenant:{tenant_id}"
        cached = VoiceConfigCache.get(cache_key)
        if cached is not None:
            return cached
        
        config = await self.get_voice_config(tenant_id)
        
        if not config:
            result = {
                "mode": "take_message",
                "transfer_number": None,
                "enabled": False,
            }
        else:
            result = {
                "mode": config.handoff_mode,
                "transfer_number": config.live_transfer_number,
                "enabled": config.is_enabled,
            }
        
        # Cache the result
        VoiceConfigCache.set(cache_key, result)
        return result

    async def get_escalation_rules(self, tenant_id: int) -> dict[str, Any]:
        """Get escalation rules for a tenant.
        
        Uses caching to reduce database queries during active calls.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with escalation rules
        """
        # Check cache first
        cache_key = f"escalation:tenant:{tenant_id}"
        cached = VoiceConfigCache.get(cache_key)
        if cached is not None:
            return cached
        
        config = await self.get_voice_config(tenant_id)
        
        if not config or not config.escalation_rules:
            result = DEFAULT_ESCALATION_RULES.copy()
        else:
            result = config.escalation_rules
        
        # Cache the result
        VoiceConfigCache.set(cache_key, result)
        return result

    async def get_notification_config(self, tenant_id: int) -> dict[str, Any]:
        """Get notification configuration for a tenant.
        
        Uses caching to reduce database queries during active calls.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with notification settings
        """
        # Check cache first
        cache_key = f"notification:tenant:{tenant_id}"
        cached = VoiceConfigCache.get(cache_key)
        if cached is not None:
            return cached
        
        config = await self.get_voice_config(tenant_id)
        
        if not config:
            result = {
                "methods": DEFAULT_NOTIFICATION_METHODS,
                "recipients": [],
            }
        else:
            result = {
                "methods": config.notification_methods or DEFAULT_NOTIFICATION_METHODS,
                "recipients": config.notification_recipients or [],
            }
        
        # Cache the result
        VoiceConfigCache.set(cache_key, result)
        return result

    async def get_greeting_and_disclosure(self, tenant_id: int) -> dict[str, str]:
        """Get greeting and disclosure text for a tenant.
        
        Uses caching to reduce database queries during active calls.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with greeting and disclosure text
        """
        # Check cache first
        cache_key = f"greeting:tenant:{tenant_id}"
        cached = VoiceConfigCache.get(cache_key)
        if cached is not None:
            return cached
        
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
            result = {
                "greeting": default_greeting,
                "disclosure": default_disclosure,
                "after_hours_message": default_after_hours,
            }
        else:
            result = {
                "greeting": config.default_greeting or default_greeting,
                "disclosure": config.disclosure_line or default_disclosure,
                "after_hours_message": config.after_hours_message or default_after_hours,
            }
        
        # Cache the result
        VoiceConfigCache.set(cache_key, result)
        return result

