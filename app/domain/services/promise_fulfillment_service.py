"""Service for fulfilling AI promises to send information via SMS."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.dnc_service import DncService
from app.domain.services.promise_detector import DetectedPromise
from app.domain.services.conversation_context_extractor import (
    extract_context_from_messages,
    extract_url_from_ai_response,
)
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.models.lead import Lead
from app.persistence.models.conversation import Message
from app.persistence.models.sent_asset import SentAsset
from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider
from app.infrastructure.redis import redis_client
from app.settings import settings
from app.core.phone import normalize_phone_for_dedup

logger = logging.getLogger(__name__)

# Deduplication TTL in seconds (1 hour)
DEDUP_TTL_SECONDS = 3600

# Test phone numbers that bypass dedup (for testing purposes)
# These numbers can receive multiple SMS within the dedup window
# WARNING: Keep this empty in production to prevent duplicate SMS
TEST_PHONE_WHITELIST: set[str] = set()


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

        # Check Do Not Contact list - skip if blocked
        dnc_service = DncService(self.session)
        if await dnc_service.is_blocked(tenant_id, phone=phone):
            logger.info(f"DNC block - skipping promise fulfillment for {phone}")
            return {"status": "skipped", "reason": "do_not_contact"}

        # Check for duplicate sends (deduplication by phone number, not conversation)
        # Normalize phone for dedup key - use shared function for consistency
        phone_normalized = normalize_phone_for_dedup(phone)
        dedup_key = f"promise_sent:{tenant_id}:{phone_normalized}:{promise.asset_type}"

        # Skip dedup if disabled via environment (for testing)
        dedup_disabled = settings.sms_dedup_disabled
        if dedup_disabled:
            logger.info(f"SMS dedup disabled via settings - bypassing all dedup for {phone_normalized}")

        # Skip dedup for test phone numbers (allows repeated testing)
        is_test_phone = phone_normalized in TEST_PHONE_WHITELIST
        if is_test_phone:
            logger.info(f"Test phone whitelist - bypassing dedup for {phone_normalized}")

        # Primary dedup: Redis with atomic setnx (set-if-not-exists)
        # This acquires a "lock" atomically to prevent race conditions when
        # multiple messages trigger fulfillment concurrently
        # If Redis is down, fall through to DB-only dedup (still protected)
        dedup_acquired = dedup_disabled or is_test_phone  # Bypass if disabled or test phone
        if not dedup_acquired:
            try:
                dedup_acquired = await redis_client.setnx(dedup_key, "1", ttl=DEDUP_TTL_SECONDS)
            except Exception as redis_err:
                logger.warning(f"Redis dedup setnx failed, falling back to DB-only: {redis_err}")
                dedup_acquired = True  # Proceed to DB check as fallback

        if not dedup_acquired:
            # MONITORING: Log duplicate detection with structured data for alerting
            logger.warning(
                "[DUPLICATE_BLOCKED] Registration link duplicate prevented by Redis",
                extra={
                    "event_type": "duplicate_send_blocked",
                    "dedup_layer": "redis",
                    "tenant_id": tenant_id,
                    "phone_normalized": phone_normalized,
                    "asset_type": promise.asset_type,
                    "conversation_id": conversation_id,
                },
            )
            return {
                "status": "skipped",
                "reason": "already_sent_recently",
            }

        # Fallback dedup: DB-backed check via sent_assets table
        # Uses INSERT ... ON CONFLICT DO NOTHING for atomic deduplication
        # This handles cases where Redis is disabled or unavailable
        # Skip if dedup is disabled or for test phone numbers
        #
        # RESEND POLICY: Allow resends after 30 days by deleting old records
        # This ensures customers can receive the asset again after a cooling period
        RESEND_COOLDOWN_DAYS = 30
        if not dedup_disabled and not is_test_phone:
            try:
                from sqlalchemy import delete

                # First, delete any old records for this phone+asset that are past the cooldown
                # This allows resends after 30 days
                cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=RESEND_COOLDOWN_DAYS)
                delete_old = delete(SentAsset).where(
                    SentAsset.tenant_id == tenant_id,
                    SentAsset.phone_normalized == phone_normalized,
                    SentAsset.asset_type == promise.asset_type,
                    SentAsset.sent_at < cooldown_cutoff,
                )
                delete_result = await self.session.execute(delete_old)
                if delete_result.rowcount > 0:
                    logger.info(
                        f"Deleted {delete_result.rowcount} old sent_asset records (>30 days) for "
                        f"phone={phone_normalized}, asset={promise.asset_type}"
                    )

                # Now try to insert - will fail if there's a recent send
                stmt = pg_insert(SentAsset).values(
                    tenant_id=tenant_id,
                    phone_normalized=phone_normalized,
                    asset_type=promise.asset_type,
                    conversation_id=conversation_id,
                    sent_at=datetime.now(timezone.utc),
                ).on_conflict_do_nothing(
                    constraint="uq_sent_assets_tenant_phone_asset"
                ).returning(SentAsset.id)

                result = await self.session.execute(stmt)
                await self.session.commit()
                inserted_id = result.scalar_one_or_none()

                if inserted_id is None:
                    # Conflict occurred - asset was already sent recently (within 30 days)
                    # MONITORING: Log duplicate detection with structured data for alerting
                    # This indicates a race condition was caught by the DB layer
                    logger.warning(
                        "[DUPLICATE_BLOCKED] Registration link duplicate prevented by DB (sent within 30 days)",
                        extra={
                            "event_type": "duplicate_send_blocked",
                            "dedup_layer": "database",
                            "tenant_id": tenant_id,
                            "phone_normalized": phone_normalized,
                            "asset_type": promise.asset_type,
                            "conversation_id": conversation_id,
                            "race_condition_caught": True,
                        },
                    )
                    # Note: Keep Redis key set since this is a genuine duplicate
                    return {
                        "status": "skipped",
                        "reason": "already_sent_to_lead",
                    }
                logger.info(f"DB dedup record created: sent_asset_id={inserted_id}")
            except Exception as db_check_err:
                logger.warning(f"DB dedup check failed, proceeding with caution: {db_check_err}")

        # Helper to release dedup locks on recoverable errors
        async def release_dedup_and_return(result: dict) -> dict:
            await redis_client.delete(dedup_key)
            # Also delete the DB dedup record
            try:
                await self.session.execute(
                    SentAsset.__table__.delete().where(
                        SentAsset.tenant_id == tenant_id,
                        SentAsset.phone_normalized == phone_normalized,
                        SentAsset.asset_type == promise.asset_type,
                    )
                )
                await self.session.commit()
            except Exception as e:
                logger.warning(f"Failed to release DB dedup record: {e}")
            logger.info(f"Released dedup locks for recoverable error: {dedup_key}")
            return result

        # Get sendable assets config from tenant prompt config
        sendable_assets = await self._get_sendable_assets(tenant_id)
        if not sendable_assets:
            logger.warning(f"No sendable assets configured for tenant {tenant_id}")
            return await release_dedup_and_return({
                "status": "not_configured",
                "error": "No sendable assets configured for tenant",
            })

        # Find the matching asset
        asset_config = sendable_assets.get(promise.asset_type)
        if not asset_config:
            logger.warning(
                f"No asset config for type '{promise.asset_type}' in tenant {tenant_id}"
            )
            return await release_dedup_and_return({
                "status": "asset_not_found",
                "error": f"No configuration for asset type: {promise.asset_type}",
            })

        # Check if asset is enabled
        if not asset_config.get("enabled", True):
            logger.info(f"Asset type '{promise.asset_type}' is disabled for tenant {tenant_id}")
            return await release_dedup_and_return({
                "status": "disabled",
                "error": f"Asset type '{promise.asset_type}' is disabled",
            })

        # Get SMS template and compose message
        sms_template = asset_config.get("sms_template")
        if not sms_template:
            logger.warning(f"No SMS template for asset type '{promise.asset_type}'")
            return await release_dedup_and_return({
                "status": "no_template",
                "error": "No SMS template configured for this asset",
            })

        # Try to get dynamic URL from conversation context
        dynamic_url = None

        # First, try to extract URL directly from AI response (it often includes full URL)
        if ai_response:
            dynamic_url = extract_url_from_ai_response(ai_response)
            if dynamic_url:
                logger.info(f"Using URL extracted from AI response: {dynamic_url}")

        # If no URL in AI response, try to build from conversation context (messages)
        if not dynamic_url and messages:
            context = extract_context_from_messages(messages)
            if context.registration_url:
                dynamic_url = context.registration_url
                logger.info(
                    f"Built dynamic URL from messages - location={context.location_code}, "
                    f"level={context.level_name}, url={dynamic_url}"
                )

        # If still no URL, try to extract location/level from ai_response text and build URL
        if not dynamic_url and ai_response:
            dynamic_url = self._build_url_from_text(ai_response)
            if dynamic_url:
                logger.info(f"Built dynamic URL from ai_response text: {dynamic_url}")

        # Use dynamic URL if available, otherwise fall back to static config
        url_to_send = dynamic_url or asset_config.get("url", "")
        if dynamic_url:
            logger.info(f"Using dynamic URL: {url_to_send}")
        else:
            # Check if fallback URL has location parameter - if not, skip sending
            # to avoid sending incomplete registration links
            if "?loc=" not in url_to_send and promise.asset_type == "registration_link":
                logger.warning(
                    f"No dynamic URL found and fallback URL missing location parameter. "
                    f"Skipping SMS to avoid incomplete link. fallback={url_to_send}"
                )
                return await release_dedup_and_return({
                    "status": "skipped",
                    "reason": "no_location_in_url",
                    "error": "Could not determine location for registration link",
                })
            logger.warning(f"No dynamic URL found, using fallback: {url_to_send}")

        # Always use the template to compose the message (provides better context)
        message = self._compose_message(sms_template, asset_config, name, url_to_send)
        logger.info(f"Composed SMS using template - length={len(message)}")

        # Send SMS
        result = await self._send_sms(tenant_id, phone, message)

        # If send failed, release dedup locks so retries are possible
        if result.get("status") != "sent":
            await redis_client.delete(dedup_key)
            # Also delete the DB dedup record
            try:
                await self.session.execute(
                    select(SentAsset).where(
                        SentAsset.tenant_id == tenant_id,
                        SentAsset.phone_normalized == phone_normalized,
                        SentAsset.asset_type == promise.asset_type,
                    ).with_for_update()
                )
                await self.session.execute(
                    SentAsset.__table__.delete().where(
                        SentAsset.tenant_id == tenant_id,
                        SentAsset.phone_normalized == phone_normalized,
                        SentAsset.asset_type == promise.asset_type,
                    )
                )
                await self.session.commit()
                logger.info(f"Released DB dedup record after failed send: {phone_normalized}/{promise.asset_type}")
            except Exception as e:
                logger.warning(f"Failed to release DB dedup record: {e}")
            logger.info(f"Released dedup key after failed send: {dedup_key}")
        else:
            # Update the sent_asset record with the message_id for audit trail
            try:
                stmt = (
                    SentAsset.__table__.update()
                    .where(
                        SentAsset.tenant_id == tenant_id,
                        SentAsset.phone_normalized == phone_normalized,
                        SentAsset.asset_type == promise.asset_type,
                    )
                    .values(message_id=result.get("message_id"))
                )
                await self.session.execute(stmt)
                await self.session.commit()
            except Exception as e:
                logger.warning(f"Failed to update sent_asset message_id: {e}")

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

    def _build_url_from_text(self, text: str) -> str | None:
        """Build registration URL by extracting location and level from text.

        Args:
            text: Text to search for location and level mentions

        Returns:
            Built registration URL or None if not enough context
        """
        from app.utils.registration_url_builder import build_registration_url

        # Log input for debugging
        logger.info(f"_build_url_from_text input (first 500 chars): {text[:500] if text else 'EMPTY'}")

        if not text:
            logger.info("_build_url_from_text: No text provided")
            return None

        text_lower = text.lower()

        # Location mappings - order matters (longer matches first)
        location_patterns = [
            ("la fitness langham creek", "LALANG"),
            ("langham creek", "LALANG"),
            ("langham", "LALANG"),
            ("la fitness cypress", "LAFCypress"),
            ("cypress", "LAFCypress"),
            ("24 hour fitness spring", "24Spring"),
            ("24 hour fitness in spring", "24Spring"),
            ("24 hr fitness in spring", "24Spring"),
            ("24 hour spring", "24Spring"),
            ("24 hr spring", "24Spring"),
            ("spring", "24Spring"),
        ]

        # Level mappings - order matters (longer matches first)
        # Includes both English and Spanish variants
        level_patterns = [
            # English patterns
            ("young adult level 3", "Young Adult 3"),
            ("young adult level 2", "Young Adult 2"),
            ("young adult level 1", "Young Adult 1"),
            ("young adult 3", "Young Adult 3"),
            ("young adult 2", "Young Adult 2"),
            ("young adult 1", "Young Adult 1"),
            ("adult level 3", "Adult Level 3"),
            ("adult level 2", "Adult Level 2"),
            ("adult level 1", "Adult Level 1"),
            ("adult 3", "Adult Level 3"),
            ("adult 2", "Adult Level 2"),
            ("adult 1", "Adult Level 1"),
            # Spanish patterns - "Adulto Nivel X" or "Nivel Adulto X"
            ("adulto nivel 3", "Adult Level 3"),
            ("adulto nivel 2", "Adult Level 2"),
            ("adulto nivel 1", "Adult Level 1"),
            ("nivel adulto 3", "Adult Level 3"),
            ("nivel adulto 2", "Adult Level 2"),
            ("nivel adulto 1", "Adult Level 1"),
            ("joven adulto 3", "Young Adult 3"),
            ("joven adulto 2", "Young Adult 2"),
            ("joven adulto 1", "Young Adult 1"),
            ("adulto joven 3", "Young Adult 3"),
            ("adulto joven 2", "Young Adult 2"),
            ("adulto joven 1", "Young Adult 1"),
            # Spanish level names (tiburón, tortuga, etc.)
            ("tiburón 2", "Shark 2"),
            ("tiburon 2", "Shark 2"),
            ("tiburón 1", "Shark 1"),
            ("tiburon 1", "Shark 1"),
            ("tortuga 2", "Turtle 2"),
            ("tortuga 1", "Turtle 1"),
            ("caballito de mar", "Seahorse"),
            ("estrella de mar", "Starfish"),
            ("renacuajo", "Tadpole"),
            ("pececillo", "Minnow"),
            ("delfín", "Dolphin"),
            ("delfin", "Dolphin"),
            ("barracuda", "Barracuda"),
            # English patterns continued
            ("shark 2", "Shark 2"),
            ("shark 1", "Shark 1"),
            ("turtle 2", "Turtle 2"),
            ("turtle 1", "Turtle 1"),
            ("tadpole", "Tadpole"),
            ("swimboree", "Swimboree"),
            ("seahorse", "Seahorse"),
            ("starfish", "Starfish"),
            ("minnow", "Minnow"),
            ("dolphin", "Dolphin"),
            ("barracuda", "Barracuda"),
        ]

        # Find location
        location_code = None
        for pattern, code in location_patterns:
            if pattern in text_lower:
                location_code = code
                logger.info(f"Found location '{pattern}' -> {code}")
                break

        # Find level
        level_name = None
        for pattern, name in level_patterns:
            if pattern in text_lower:
                level_name = name
                logger.info(f"Found level '{pattern}' -> {name}")
                break

        # Build URL if we have at least location
        if location_code:
            try:
                url = build_registration_url(location_code, level_name)
                logger.info(f"Built URL: location={location_code}, level={level_name}, url={url}")
                return url
            except Exception as e:
                logger.warning(f"Failed to build URL: {e}")

        logger.info(f"Could not build URL - location={location_code}, level={level_name}")
        return None

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
        # [SMS-DEBUG] Log input parameters for debugging transfer issues
        logger.info(
            f"[SMS-DEBUG] _send_sms called - tenant_id={tenant_id}, "
            f"to_phone={to_phone}, message_length={len(message)}"
        )

        # Get tenant SMS config
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        sms_config = result.scalar_one_or_none()

        if not sms_config:
            logger.warning(
                f"[SMS-DEBUG] No SMS config found for tenant {tenant_id}"
            )
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

        # [SMS-DEBUG] Log formatted phone and from number before send
        logger.info(
            f"[SMS-DEBUG] Attempting SMS send - tenant_id={tenant_id}, "
            f"from={from_number}, to={formatted_phone}, has_profile={bool(messaging_profile_id)}"
        )

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
            logger.error(
                f"[SMS-DEBUG] Failed to send promise fulfillment SMS - "
                f"tenant_id={tenant_id}, to={formatted_phone}, error={e}",
                exc_info=True
            )
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
