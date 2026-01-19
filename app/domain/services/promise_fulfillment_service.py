"""Service for fulfilling AI promises to send information via SMS."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.promise_detector import DetectedPromise
from app.domain.services.conversation_context_extractor import (
    extract_context_from_messages,
    extract_url_from_ai_response,
)
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.models.lead import Lead
from app.persistence.models.conversation import Message
from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider
from app.infrastructure.redis import redis_client

logger = logging.getLogger(__name__)

# Deduplication TTL in seconds (1 hour)
DEDUP_TTL_SECONDS = 3600


class PromiseFulfillmentService:
    """Service for fulfilling promises made by the AI to send information."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize promise fulfillment service."""
        self.session = session

    async def fulfill_promise(
        self,
        tenant_id: int,
        conversation_id: int,
        promise: DetectedPromise,
        phone: str,
        name: str | None = None,
        messages: list[Message] | None = None,
        ai_response: str | None = None,
    ) -> dict[str, Any]:
        """Fulfill a detected promise by sending SMS with the promised content.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID where promise was made
            promise: The detected promise details
            phone: Customer's phone number
            name: Customer's name (optional, for personalization)
            messages: Conversation messages (for extracting dynamic URL context)
            ai_response: The AI response that contained the promise (for URL extraction)

        Returns:
            Result dictionary with status and details
        """
        logger.info(
            f"Fulfilling promise - tenant_id={tenant_id}, conversation_id={conversation_id}, "
            f"asset_type={promise.asset_type}, phone={phone}"
        )

        # Check for duplicate sends (deduplication by phone number, not conversation)
        # Normalize phone for dedup key
        phone_normalized = "".join(c for c in phone if c.isdigit())[-10:]
        dedup_key = f"promise_sent:{tenant_id}:{phone_normalized}:{promise.asset_type}"

        # Primary dedup: Redis (if enabled)
        if await redis_client.exists(dedup_key):
            logger.info(
                f"Skipping duplicate promise fulfillment (Redis) - key={dedup_key}"
            )
            return {
                "status": "skipped",
                "reason": "already_sent_recently",
            }

        # Fallback dedup: DB-backed check via Lead.extra_data
        # This handles cases where Redis is disabled or unavailable
        try:
            stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.phone.like(f"%{phone_normalized}"),
            ).order_by(Lead.created_at.desc()).limit(1)
            lead_result = await self.session.execute(stmt)
            existing_lead = lead_result.scalar_one_or_none()

            if existing_lead and existing_lead.extra_data:
                extra = existing_lead.extra_data
                sms_sent_assets = extra.get("sms_sent_for_assets", [])
                if promise.asset_type in sms_sent_assets:
                    logger.info(
                        f"Skipping duplicate promise fulfillment (DB) - "
                        f"asset_type={promise.asset_type} already sent to lead_id={existing_lead.id}"
                    )
                    return {
                        "status": "skipped",
                        "reason": "already_sent_to_lead",
                    }
        except Exception as db_check_err:
            logger.warning(f"DB dedup check failed, proceeding: {db_check_err}")

        # Get sendable assets config from tenant prompt config
        sendable_assets = await self._get_sendable_assets(tenant_id)
        if not sendable_assets:
            logger.warning(f"No sendable assets configured for tenant {tenant_id}")
            return {
                "status": "not_configured",
                "error": "No sendable assets configured for tenant",
            }

        # Find the matching asset
        asset_config = sendable_assets.get(promise.asset_type)
        if not asset_config:
            logger.warning(
                f"No asset config for type '{promise.asset_type}' in tenant {tenant_id}"
            )
            return {
                "status": "asset_not_found",
                "error": f"No configuration for asset type: {promise.asset_type}",
            }

        # Check if asset is enabled
        if not asset_config.get("enabled", True):
            logger.info(f"Asset type '{promise.asset_type}' is disabled for tenant {tenant_id}")
            return {
                "status": "disabled",
                "error": f"Asset type '{promise.asset_type}' is disabled",
            }

        # Get SMS template and compose message
        sms_template = asset_config.get("sms_template")
        if not sms_template:
            logger.warning(f"No SMS template for asset type '{promise.asset_type}'")
            return {
                "status": "no_template",
                "error": "No SMS template configured for this asset",
            }

        # Try to get dynamic URL from conversation context
        dynamic_url = None

        # First, try to extract URL directly from AI response (it often includes full URL)
        if ai_response:
            dynamic_url = extract_url_from_ai_response(ai_response)
            if dynamic_url:
                logger.info(f"Using URL extracted from AI response: {dynamic_url}")

        # If no URL in AI response, try to build from conversation context
        if not dynamic_url and messages:
            context = extract_context_from_messages(messages)
            if context.registration_url:
                dynamic_url = context.registration_url
                logger.info(
                    f"Built dynamic URL from context - location={context.location_code}, "
                    f"level={context.level_name}, url={dynamic_url}"
                )

        # Use dynamic URL if available, otherwise fall back to static config
        url_to_send = dynamic_url or asset_config.get("url", "")

        # For registration links, send ONLY the URL (no extra text)
        if dynamic_url and promise.asset_type in ("registration_link", "info"):
            message = url_to_send
            logger.info(f"Sending plain URL only: {message}")
        else:
            # Compose the message using template
            message = self._compose_message(sms_template, asset_config, name, url_to_send)

        # Send SMS
        result = await self._send_sms(tenant_id, phone, message)

        # Mark as sent for deduplication (only if successful)
        if result.get("status") == "sent":
            await redis_client.set(dedup_key, "1", ttl=DEDUP_TTL_SECONDS)
            logger.info(f"Set dedup key with TTL {DEDUP_TTL_SECONDS}s: {dedup_key}")

        # Track fulfillment in lead metadata if lead exists
        await self._track_fulfillment(tenant_id, conversation_id, promise, result, phone)

        return result

    async def _get_sendable_assets(self, tenant_id: int) -> dict[str, Any] | None:
        """Get sendable assets configuration from tenant prompt config.

        Args:
            tenant_id: Tenant ID

        Returns:
            Sendable assets configuration or None
        """
        stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        prompt_config = result.scalar_one_or_none()

        if not prompt_config or not prompt_config.config_json:
            return None

        config = prompt_config.config_json
        if isinstance(config, str):
            config = json.loads(config)

        return config.get("sendable_assets")

    def _compose_message(
        self,
        template: str,
        asset_config: dict[str, Any],
        name: str | None,
        url: str | None = None,
    ) -> str:
        """Compose the SMS message from template.

        Args:
            template: SMS template with placeholders
            asset_config: Asset configuration with URL etc.
            name: Customer's name for personalization
            url: URL to use (if provided, overrides asset_config URL)

        Returns:
            Composed message string
        """
        # Replace placeholders
        message = template
        message = message.replace("{name}", name or "there")
        message = message.replace("{url}", url or asset_config.get("url", ""))

        # Truncate to SMS limit if needed
        if len(message) > 160:
            message = message[:157] + "..."

        return message

    async def _send_sms(
        self,
        tenant_id: int,
        to_phone: str,
        message: str,
    ) -> dict[str, Any]:
        """Send SMS via Telnyx.

        Args:
            tenant_id: Tenant ID
            to_phone: Recipient phone number
            message: SMS message

        Returns:
            Result dictionary
        """
        # Get tenant SMS config
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        if not sms_config:
            return {
                "status": "not_configured",
                "error": "Tenant SMS not configured",
            }

        # Get Telnyx credentials
        api_key = sms_config.telnyx_api_key
        from_number = sms_config.telnyx_phone_number
        messaging_profile_id = sms_config.telnyx_messaging_profile_id

        if not api_key or not from_number:
            return {
                "status": "not_configured",
                "error": "Telnyx SMS not configured for tenant",
            }

        # Format phone number (ensure E.164)
        formatted_phone = to_phone
        if not formatted_phone.startswith("+"):
            # Assume US number
            digits = "".join(c for c in formatted_phone if c.isdigit())
            if len(digits) == 10:
                formatted_phone = f"+1{digits}"
            elif len(digits) == 11 and digits.startswith("1"):
                formatted_phone = f"+{digits}"
            else:
                formatted_phone = f"+{digits}"

        # Send SMS
        try:
            telnyx_provider = TelnyxSmsProvider(
                api_key=api_key,
                messaging_profile_id=messaging_profile_id,
            )

            sms_result = await telnyx_provider.send_sms(
                to=formatted_phone,
                from_=from_number,
                body=message,
            )

            logger.info(
                f"Promise fulfillment SMS sent - tenant_id={tenant_id}, "
                f"to={formatted_phone}, message_id={sms_result.message_id}"
            )

            return {
                "status": "sent",
                "message_id": sms_result.message_id,
                "to": formatted_phone,
                "provider": "telnyx",
            }

        except Exception as e:
            logger.error(f"Failed to send promise fulfillment SMS: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def _track_fulfillment(
        self,
        tenant_id: int,
        conversation_id: int,
        promise: DetectedPromise,
        result: dict[str, Any],
        phone: str | None = None,
    ) -> None:
        """Track promise fulfillment in lead metadata.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            promise: The promise that was fulfilled
            result: The fulfillment result
            phone: Phone number (optional, for fallback lookup)
        """
        try:
            # Find lead for this conversation
            stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.conversation_id == conversation_id,
            )
            lead_result = await self.session.execute(stmt)
            lead = lead_result.scalar_one_or_none()

            # Fallback: Find lead by phone if conversation lookup fails
            if not lead and phone:
                phone_normalized = "".join(c for c in phone if c.isdigit())[-10:]
                stmt = select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone.like(f"%{phone_normalized}"),
                ).order_by(Lead.created_at.desc()).limit(1)
                lead_result = await self.session.execute(stmt)
                lead = lead_result.scalar_one_or_none()

            if lead:
                # Update lead metadata
                extra_data = lead.extra_data or {}
                if isinstance(extra_data, str):
                    extra_data = json.loads(extra_data)

                extra_data["promise_fulfilled"] = {
                    "asset_type": promise.asset_type,
                    "status": result.get("status"),
                    "message_id": result.get("message_id"),
                    "fulfilled_at": datetime.now(timezone.utc).isoformat(),
                }

                # Track sent assets for DB-backed deduplication
                # This is used when Redis is unavailable
                if result.get("status") == "sent":
                    sms_sent_assets = extra_data.get("sms_sent_for_assets", [])
                    if promise.asset_type not in sms_sent_assets:
                        sms_sent_assets.append(promise.asset_type)
                        extra_data["sms_sent_for_assets"] = sms_sent_assets

                lead.extra_data = extra_data
                await self.session.commit()

                logger.info(f"Tracked promise fulfillment in lead {lead.id}, asset_type={promise.asset_type}")

        except Exception as e:
            logger.error(f"Failed to track promise fulfillment: {e}", exc_info=True)
