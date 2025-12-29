"""Zapier integration service for outbound webhooks and callback handling."""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.redis import redis_client
from app.persistence.models.zapier_request import ZapierRequest
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository
from app.persistence.repositories.zapier_request_repository import ZapierRequestRepository
from app.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ZapierSendResult:
    """Result of sending a webhook to Zapier."""
    success: bool
    correlation_id: str
    error: str | None = None


class ZapierIntegrationService:
    """Service for Zapier webhook integration (outbound and callback handling)."""

    # Redis key prefixes
    PENDING_KEY_PREFIX = "cs:pending:"
    RESPONSE_KEY_PREFIX = "cs:response:"

    # Default timeouts
    DEFAULT_TIMEOUT_SECONDS = 30
    HTTP_TIMEOUT_SECONDS = 10

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config_repo = CustomerServiceConfigRepository(session)
        self.request_repo = ZapierRequestRepository(session)

    async def send_customer_lookup(
        self,
        tenant_id: int,
        phone_number: str,
        conversation_id: int | None = None,
    ) -> ZapierSendResult:
        """Send customer lookup request to Zapier.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number to look up
            conversation_id: Optional conversation for context

        Returns:
            ZapierSendResult with correlation_id for tracking
        """
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.zapier_webhook_url:
            return ZapierSendResult(
                success=False,
                correlation_id="",
                error="Zapier webhook not configured for tenant",
            )

        correlation_id = self._generate_correlation_id()
        callback_url = self._get_callback_url()

        payload = {
            "type": "customer_lookup",
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "phone_number": phone_number,
            "callback_url": callback_url,
        }

        return await self._send_request(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            request_type="customer_lookup",
            payload=payload,
            webhook_url=config.zapier_webhook_url,
            conversation_id=conversation_id,
            phone_number=phone_number,
        )

    async def send_customer_query(
        self,
        tenant_id: int,
        jackrabbit_customer_id: str,
        query: str,
        context: dict | None = None,
        conversation_id: int | None = None,
        phone_number: str | None = None,
    ) -> ZapierSendResult:
        """Send customer query to Jackrabbit via Zapier.

        Args:
            tenant_id: Tenant ID
            jackrabbit_customer_id: Customer ID in Jackrabbit
            query: User's question/request
            context: Additional context (conversation history, etc.)
            conversation_id: Optional conversation ID
            phone_number: Optional phone number

        Returns:
            ZapierSendResult with correlation_id
        """
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.zapier_webhook_url:
            return ZapierSendResult(
                success=False,
                correlation_id="",
                error="Zapier webhook not configured for tenant",
            )

        correlation_id = self._generate_correlation_id()
        callback_url = self._get_callback_url()

        payload = {
            "type": "customer_query",
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "jackrabbit_customer_id": jackrabbit_customer_id,
            "query": query,
            "context": context or {},
            "callback_url": callback_url,
        }

        return await self._send_request(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            request_type="customer_query",
            payload=payload,
            webhook_url=config.zapier_webhook_url,
            conversation_id=conversation_id,
            phone_number=phone_number,
        )

    async def _send_request(
        self,
        tenant_id: int,
        correlation_id: str,
        request_type: str,
        payload: dict,
        webhook_url: str,
        conversation_id: int | None = None,
        phone_number: str | None = None,
    ) -> ZapierSendResult:
        """Send HTTP request to Zapier webhook.

        Args:
            tenant_id: Tenant ID
            correlation_id: Unique request correlation ID
            request_type: Type of request
            payload: Request payload
            webhook_url: Zapier webhook URL
            conversation_id: Optional conversation ID
            phone_number: Optional phone number

        Returns:
            ZapierSendResult
        """
        # Create request record in database
        request = ZapierRequest(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            request_type=request_type,
            request_payload=payload,
            request_sent_at=datetime.utcnow(),
            status="pending",
            conversation_id=conversation_id,
            phone_number=phone_number,
        )
        self.session.add(request)
        await self.session.commit()

        # Store pending status in Redis for fast polling
        await redis_client.set_json(
            f"{self.PENDING_KEY_PREFIX}{correlation_id}",
            {"status": "pending", "tenant_id": tenant_id},
            ttl=300,  # 5 minute TTL
        )

        # Send HTTP request to Zapier
        try:
            async with httpx.AsyncClient(timeout=self.HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

            logger.info(
                f"Sent Zapier {request_type} request",
                extra={
                    "correlation_id": correlation_id,
                    "tenant_id": tenant_id,
                    "status_code": response.status_code,
                },
            )

            return ZapierSendResult(success=True, correlation_id=correlation_id)

        except httpx.TimeoutException as e:
            logger.error(f"Zapier request timeout: {e}")
            await self._mark_request_error(correlation_id, "Request timeout")
            return ZapierSendResult(
                success=False,
                correlation_id=correlation_id,
                error="Request timeout",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Zapier HTTP error: {e.response.status_code}")
            await self._mark_request_error(
                correlation_id, f"HTTP error: {e.response.status_code}"
            )
            return ZapierSendResult(
                success=False,
                correlation_id=correlation_id,
                error=f"HTTP error: {e.response.status_code}",
            )

        except Exception as e:
            logger.exception(f"Zapier request failed: {e}")
            await self._mark_request_error(correlation_id, str(e))
            return ZapierSendResult(
                success=False,
                correlation_id=correlation_id,
                error=str(e),
            )

    async def process_callback(
        self,
        correlation_id: str,
        payload: dict,
        signature: str | None = None,
    ) -> ZapierRequest | None:
        """Process callback from Zapier with response data.

        Args:
            correlation_id: Request correlation ID
            payload: Response payload from Zapier
            signature: HMAC signature for verification (optional)

        Returns:
            Updated ZapierRequest or None if not found
        """
        # Get the original request
        request = await self.request_repo.get_by_correlation_id(correlation_id)
        if not request:
            logger.warning(f"Callback for unknown correlation_id: {correlation_id}")
            return None

        # Verify signature if configured
        if signature:
            config = await self.config_repo.get_by_tenant_id(request.tenant_id)
            if config and config.zapier_callback_secret:
                if not self._verify_callback_signature(
                    payload, signature, config.zapier_callback_secret
                ):
                    logger.warning(
                        f"Invalid signature for callback: {correlation_id}"
                    )
                    return None

        # Determine status from payload
        status = "completed"
        error_message = None
        if payload.get("status") == "error":
            status = "error"
            error_message = payload.get("error")

        # Update request in database
        updated = await self.request_repo.update_with_response(
            correlation_id=correlation_id,
            response_payload=payload,
            status=status,
            error_message=error_message,
        )

        # Store response in Redis for polling
        await redis_client.set_json(
            f"{self.RESPONSE_KEY_PREFIX}{correlation_id}",
            {"status": status, "payload": payload},
            ttl=300,  # 5 minute TTL
        )

        # Delete pending key
        await redis_client.delete(f"{self.PENDING_KEY_PREFIX}{correlation_id}")

        logger.info(
            f"Processed Zapier callback",
            extra={
                "correlation_id": correlation_id,
                "status": status,
                "tenant_id": request.tenant_id,
            },
        )

        return updated

    async def wait_for_response(
        self,
        correlation_id: str,
        timeout_seconds: int | None = None,
        poll_interval: float = 0.5,
    ) -> dict | None:
        """Wait for Zapier callback response (polling Redis).

        Args:
            correlation_id: Request correlation ID
            timeout_seconds: Custom timeout (uses default if not provided)
            poll_interval: Interval between polls in seconds

        Returns:
            Response payload or None if timeout
        """
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if response is available in Redis
            response_data = await redis_client.get_json(
                f"{self.RESPONSE_KEY_PREFIX}{correlation_id}"
            )

            if response_data:
                return response_data.get("payload")

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                # Mark as timeout in database
                await self.request_repo.mark_timeout(correlation_id)
                logger.warning(
                    f"Zapier response timeout after {timeout}s",
                    extra={"correlation_id": correlation_id},
                )
                return None

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    async def _mark_request_error(
        self, correlation_id: str, error_message: str
    ) -> None:
        """Mark a request as failed in database and Redis."""
        request = await self.request_repo.get_by_correlation_id(correlation_id)
        if request:
            request.status = "error"
            request.error_message = error_message
            await self.session.commit()

        # Update Redis
        await redis_client.set_json(
            f"{self.RESPONSE_KEY_PREFIX}{correlation_id}",
            {"status": "error", "error": error_message},
            ttl=300,
        )
        await redis_client.delete(f"{self.PENDING_KEY_PREFIX}{correlation_id}")

    def _generate_correlation_id(self) -> str:
        """Generate unique correlation ID."""
        return f"cs-{uuid.uuid4().hex[:16]}"

    def _get_callback_url(self) -> str:
        """Get the callback URL for Zapier responses."""
        base_url = settings.api_base_url or settings.twilio_webhook_url_base or ""
        return f"{base_url}{settings.api_v1_prefix}/zapier/callback"

    def _verify_callback_signature(
        self,
        payload: dict,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify HMAC signature on callback.

        Args:
            payload: Request payload
            signature: HMAC signature from header
            secret: Shared secret for verification

        Returns:
            True if signature is valid
        """
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)
