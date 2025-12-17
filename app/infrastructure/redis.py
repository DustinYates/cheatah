"""Redis client wrapper for caching and idempotency."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper for async operations."""

    def __init__(self) -> None:
        """Initialize Redis client."""
        self._client: aioredis.Redis | None = None
        self._enabled: bool = settings.redis_enabled

    async def connect(self) -> None:
        """Connect to Redis."""
        if not self._enabled:
            logger.info("Redis disabled - skipping connection")
            return
        if self._client is None:
            try:
                self._client = await aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Continuing without Redis.")
                self._enabled = False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None

    async def get(self, key: str) -> str | None:
        """Get value from Redis.

        Args:
            key: Redis key

        Returns:
            Value or None if not found
        """
        if not self._enabled or self._client is None:
            return None
        return await self._client.get(key)

    async def set(
        self, key: str, value: str, ttl: int | None = None
    ) -> bool:
        """Set value in Redis.

        Args:
            key: Redis key
            value: Value to set
            ttl: Optional time-to-live in seconds

        Returns:
            True if successful
        """
        if not self._enabled or self._client is None:
            return True  # Pretend success when disabled
        if ttl:
            return await self._client.setex(key, ttl, value)
        return await self._client.set(key, value)

    async def delete(self, key: str) -> int:
        """Delete key from Redis.

        Args:
            key: Redis key

        Returns:
            Number of keys deleted
        """
        if not self._enabled or self._client is None:
            return 0
        return await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis.

        Args:
            key: Redis key

        Returns:
            True if key exists
        """
        if not self._enabled or self._client is None:
            return False
        return await self._client.exists(key) > 0

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get JSON value from Redis.

        Args:
            key: Redis key

        Returns:
            Parsed JSON dict or None
        """
        value = await self.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set_json(
        self, key: str, value: dict[str, Any], ttl: int | None = None
    ) -> bool:
        """Set JSON value in Redis.

        Args:
            key: Redis key
            value: Dictionary to store
            ttl: Optional time-to-live in seconds

        Returns:
            True if successful
        """
        return await self.set(key, json.dumps(value), ttl)


# Global Redis client instance
redis_client = RedisClient()

