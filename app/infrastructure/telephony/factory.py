"""Telephony provider factory."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.telephony.base import SmsProviderProtocol, VoiceProviderProtocol
from app.infrastructure.telephony.twilio_provider import TwilioSmsProvider, TwilioVoiceProvider
from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider, TelnyxVoiceProvider
from app.persistence.models.tenant_sms_config import TenantSmsConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TelephonyProviderFactory:
    """Factory for creating telephony provider instances based on tenant configuration."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize factory with database session.

        Args:
            session: Database session for fetching tenant config
        """
        self.session = session
        self._config_cache: dict[int, TenantSmsConfig | None] = {}

    async def get_sms_provider(self, tenant_id: int) -> SmsProviderProtocol | None:
        """Get SMS provider for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            SMS provider instance or None if not configured/enabled
        """
        config = await self._get_config(tenant_id)
        if not config or not config.is_enabled:
            return None

        if config.provider == "telnyx":
            if not config.telnyx_api_key:
                logger.warning(f"Tenant {tenant_id} has Telnyx provider but no API key")
                return None
            return TelnyxSmsProvider(
                api_key=config.telnyx_api_key,
                messaging_profile_id=config.telnyx_messaging_profile_id,
            )
        else:  # Default to Twilio
            if not config.twilio_account_sid or not config.twilio_auth_token:
                logger.warning(f"Tenant {tenant_id} has Twilio provider but missing credentials")
                return None
            return TwilioSmsProvider(
                account_sid=config.twilio_account_sid,
                auth_token=config.twilio_auth_token,
            )

    async def get_voice_provider(self, tenant_id: int) -> VoiceProviderProtocol | None:
        """Get Voice provider for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Voice provider instance or None if not configured/enabled
        """
        config = await self._get_config(tenant_id)
        if not config or not config.voice_enabled:
            return None

        if config.provider == "telnyx":
            if not config.telnyx_api_key:
                logger.warning(f"Tenant {tenant_id} has Telnyx provider but no API key")
                return None
            return TelnyxVoiceProvider(
                api_key=config.telnyx_api_key,
                connection_id=config.telnyx_connection_id,
            )
        else:  # Default to Twilio
            if not config.twilio_account_sid or not config.twilio_auth_token:
                logger.warning(f"Tenant {tenant_id} has Twilio provider but missing credentials")
                return None
            return TwilioVoiceProvider(
                account_sid=config.twilio_account_sid,
                auth_token=config.twilio_auth_token,
            )

    async def get_config(self, tenant_id: int) -> TenantSmsConfig | None:
        """Get telephony config for tenant (public method).

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant telephony config or None if not found
        """
        return await self._get_config(tenant_id)

    async def _get_config(self, tenant_id: int) -> TenantSmsConfig | None:
        """Fetch telephony config from database (with caching).

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant telephony config or None if not found
        """
        # Check cache first
        if tenant_id in self._config_cache:
            return self._config_cache[tenant_id]

        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        config = result.scalar_one_or_none()

        # Cache the result
        self._config_cache[tenant_id] = config
        return config

    def get_sms_phone_number(self, config: TenantSmsConfig) -> str | None:
        """Get SMS phone number based on provider.

        Args:
            config: Tenant telephony config

        Returns:
            SMS phone number or None
        """
        if config.provider == "telnyx":
            return config.telnyx_phone_number
        return config.twilio_phone_number

    def get_voice_phone_number(self, config: TenantSmsConfig) -> str | None:
        """Get voice phone number based on provider.

        Args:
            config: Tenant telephony config

        Returns:
            Voice phone number or None
        """
        return config.voice_phone_number

    def get_webhook_path_prefix(self, config: TenantSmsConfig) -> str:
        """Get webhook URL path prefix based on provider.

        Args:
            config: Tenant telephony config

        Returns:
            Path prefix for webhooks (e.g., '/telnyx' or '')
        """
        if config.provider == "telnyx":
            return "/telnyx"
        return ""

    def clear_cache(self, tenant_id: int | None = None) -> None:
        """Clear config cache.

        Args:
            tenant_id: Specific tenant to clear, or None to clear all
        """
        if tenant_id is not None:
            self._config_cache.pop(tenant_id, None)
        else:
            self._config_cache.clear()


async def get_tenant_by_phone_number(
    session: AsyncSession,
    phone_number: str,
    provider: str = "twilio",
) -> int | None:
    """Look up tenant ID by phone number.

    Args:
        session: Database session
        phone_number: Phone number to look up
        provider: Provider type ('twilio' or 'telnyx')

    Returns:
        Tenant ID or None if not found
    """
    if provider == "telnyx":
        stmt = select(TenantSmsConfig.tenant_id).where(
            TenantSmsConfig.telnyx_phone_number == phone_number
        )
    else:
        stmt = select(TenantSmsConfig.tenant_id).where(
            TenantSmsConfig.twilio_phone_number == phone_number
        )

    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def get_tenant_by_voice_phone_number(
    session: AsyncSession,
    phone_number: str,
) -> int | None:
    """Look up tenant ID by voice phone number.

    Args:
        session: Database session
        phone_number: Voice phone number to look up

    Returns:
        Tenant ID or None if not found
    """
    stmt = select(TenantSmsConfig.tenant_id).where(
        TenantSmsConfig.voice_phone_number == phone_number
    )

    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row
