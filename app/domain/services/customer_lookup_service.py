"""Customer lookup service for Jackrabbit customer identification via Zapier."""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.zapier_integration_service import ZapierIntegrationService
from app.infrastructure.redis import redis_client
from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository
from app.persistence.repositories.jackrabbit_customer_repository import JackrabbitCustomerRepository
from app.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CustomerLookupResult:
    """Result of customer lookup."""
    found: bool
    jackrabbit_customer: JackrabbitCustomer | None = None
    from_cache: bool = False
    lookup_time_ms: float = 0.0
    error: str | None = None


class CustomerLookupService:
    """Service for looking up customers in Jackrabbit via Zapier."""

    # Redis cache key prefix
    CACHE_KEY_PREFIX = "cs:lookup:"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.zapier_service = ZapierIntegrationService(session)
        self.customer_repo = JackrabbitCustomerRepository(session)
        self.config_repo = CustomerServiceConfigRepository(session)

    async def lookup_by_phone(
        self,
        tenant_id: int,
        phone_number: str,
        use_cache: bool = True,
        conversation_id: int | None = None,
    ) -> CustomerLookupResult:
        """Look up customer by phone number.

        First checks local cache, then queries Jackrabbit via Zapier if not found.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number to look up (E.164 format preferred)
            use_cache: Whether to check cache first
            conversation_id: Optional conversation context

        Returns:
            CustomerLookupResult with customer data or not-found status
        """
        start_time = time.time()
        normalized_phone = self._normalize_phone(phone_number)

        # Check cache first
        if use_cache:
            cached_customer = await self._check_cache(tenant_id, normalized_phone)
            if cached_customer:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.debug(
                    f"Customer found in cache",
                    extra={
                        "tenant_id": tenant_id,
                        "phone": normalized_phone,
                        "jackrabbit_id": cached_customer.jackrabbit_id,
                        "lookup_time_ms": elapsed_ms,
                    },
                )
                return CustomerLookupResult(
                    found=True,
                    jackrabbit_customer=cached_customer,
                    from_cache=True,
                    lookup_time_ms=elapsed_ms,
                )

        # Get tenant config for timeout settings
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.is_enabled:
            elapsed_ms = (time.time() - start_time) * 1000
            return CustomerLookupResult(
                found=False,
                error="Customer service not enabled for tenant",
                lookup_time_ms=elapsed_ms,
            )

        # Send lookup request to Zapier
        result = await self.zapier_service.send_customer_lookup(
            tenant_id=tenant_id,
            phone_number=normalized_phone,
            conversation_id=conversation_id,
        )

        if not result.success:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"Zapier lookup request failed",
                extra={
                    "tenant_id": tenant_id,
                    "phone": normalized_phone,
                    "error": result.error,
                },
            )
            return CustomerLookupResult(
                found=False,
                error=result.error,
                lookup_time_ms=elapsed_ms,
            )

        # Wait for response
        timeout = config.customer_lookup_timeout_seconds or settings.zapier_default_callback_timeout
        response = await self.zapier_service.wait_for_response(
            correlation_id=result.correlation_id,
            timeout_seconds=timeout,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        if not response:
            logger.warning(
                f"Customer lookup timeout",
                extra={
                    "tenant_id": tenant_id,
                    "phone": normalized_phone,
                    "timeout_seconds": timeout,
                },
            )
            return CustomerLookupResult(
                found=False,
                error="lookup_timeout",
                lookup_time_ms=elapsed_ms,
            )

        # Check if customer was found
        data = response.get("data", {})
        if not data.get("found"):
            logger.info(
                f"Customer not found in Jackrabbit",
                extra={
                    "tenant_id": tenant_id,
                    "phone": normalized_phone,
                    "lookup_time_ms": elapsed_ms,
                },
            )
            return CustomerLookupResult(
                found=False,
                lookup_time_ms=elapsed_ms,
            )

        # Customer found - update cache
        customer = await self._update_cache(
            tenant_id=tenant_id,
            jackrabbit_id=data.get("jackrabbit_id"),
            phone_number=normalized_phone,
            email=data.get("email"),
            name=data.get("name"),
            customer_data=data.get("customer_data", {}),
        )

        logger.info(
            f"Customer found via Zapier lookup",
            extra={
                "tenant_id": tenant_id,
                "phone": normalized_phone,
                "jackrabbit_id": customer.jackrabbit_id,
                "lookup_time_ms": elapsed_ms,
            },
        )

        return CustomerLookupResult(
            found=True,
            jackrabbit_customer=customer,
            from_cache=False,
            lookup_time_ms=elapsed_ms,
        )

    async def _check_cache(
        self,
        tenant_id: int,
        phone_number: str,
    ) -> JackrabbitCustomer | None:
        """Check for customer in cache (Redis + database).

        Args:
            tenant_id: Tenant ID
            phone_number: Normalized phone number

        Returns:
            Cached customer or None
        """
        # Check Redis first for faster lookup
        cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{phone_number}"
        redis_data = await redis_client.get_json(cache_key)

        if redis_data:
            # Customer ID is in Redis, fetch full record from DB
            customer = await self.customer_repo.get_by_jackrabbit_id(
                tenant_id, redis_data.get("jackrabbit_id")
            )
            if customer:
                # Check if cache is still valid
                if customer.cache_expires_at and customer.cache_expires_at < datetime.utcnow():
                    # Cache expired, invalidate
                    await redis_client.delete(cache_key)
                    return None
                return customer

        # Fall back to database lookup
        customer = await self.customer_repo.get_by_phone(tenant_id, phone_number)
        if customer:
            # Check expiration
            if customer.cache_expires_at and customer.cache_expires_at < datetime.utcnow():
                return None

            # Store in Redis for faster subsequent lookups
            await redis_client.set_json(
                cache_key,
                {"jackrabbit_id": customer.jackrabbit_id},
                ttl=settings.customer_service_cache_ttl_seconds,
            )
            return customer

        return None

    async def _update_cache(
        self,
        tenant_id: int,
        jackrabbit_id: str,
        phone_number: str,
        email: str | None = None,
        name: str | None = None,
        customer_data: dict | None = None,
    ) -> JackrabbitCustomer:
        """Update customer cache with data from Jackrabbit.

        Args:
            tenant_id: Tenant ID
            jackrabbit_id: Jackrabbit customer ID
            phone_number: Phone number
            email: Optional email
            name: Optional customer name
            customer_data: Full Jackrabbit record

        Returns:
            Created or updated customer record
        """
        cache_ttl = settings.customer_service_cache_ttl_seconds
        cache_expires_at = datetime.utcnow() + timedelta(seconds=cache_ttl)

        # Upsert in database
        customer = await self.customer_repo.upsert(
            tenant_id=tenant_id,
            jackrabbit_id=jackrabbit_id,
            phone_number=phone_number,
            email=email,
            name=name,
            customer_data=customer_data,
            cache_expires_at=cache_expires_at,
        )

        # Update Redis cache
        cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{phone_number}"
        await redis_client.set_json(
            cache_key,
            {"jackrabbit_id": jackrabbit_id},
            ttl=cache_ttl,
        )

        return customer

    async def invalidate_cache(
        self,
        tenant_id: int,
        phone_number: str | None = None,
        jackrabbit_id: str | None = None,
    ) -> None:
        """Invalidate cached customer data.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone to invalidate (optional)
            jackrabbit_id: Jackrabbit ID to invalidate (optional)
        """
        if phone_number:
            normalized = self._normalize_phone(phone_number)
            cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{normalized}"
            await redis_client.delete(cache_key)
            await self.customer_repo.invalidate_by_phone(tenant_id, normalized)

        if jackrabbit_id:
            # Get customer to find phone for Redis key
            customer = await self.customer_repo.get_by_jackrabbit_id(
                tenant_id, jackrabbit_id
            )
            if customer:
                cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{customer.phone_number}"
                await redis_client.delete(cache_key)
            await self.customer_repo.invalidate_by_jackrabbit_id(tenant_id, jackrabbit_id)

        logger.info(
            f"Cache invalidated",
            extra={
                "tenant_id": tenant_id,
                "phone_number": phone_number,
                "jackrabbit_id": jackrabbit_id,
            },
        )

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to E.164 format.

        Args:
            phone: Input phone number

        Returns:
            Normalized phone number
        """
        # Remove all non-digit characters except leading +
        if phone.startswith("+"):
            cleaned = "+" + re.sub(r"[^\d]", "", phone[1:])
        else:
            cleaned = re.sub(r"[^\d]", "", phone)

        # If it's a 10-digit US number without country code, add +1
        if len(cleaned) == 10:
            cleaned = "+1" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("1"):
            cleaned = "+" + cleaned
        elif not cleaned.startswith("+"):
            cleaned = "+" + cleaned

        return cleaned
