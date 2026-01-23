"""Rate limiting infrastructure for public endpoints.

Supports both Redis-based (distributed) and in-memory (single instance) rate limiting.
Uses sliding window counter algorithm for accurate rate limiting.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request, status

from app.infrastructure.redis import redis_client
from app.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests: int  # Number of requests allowed
    window_seconds: int  # Time window in seconds
    key_prefix: str = "ratelimit"  # Redis key prefix


# Default rate limit configurations for different endpoint types
RATE_LIMITS = {
    # Chat endpoint - most expensive (LLM calls)
    "chat": RateLimitConfig(requests=30, window_seconds=60, key_prefix="rl:chat"),
    # Widget settings - lightweight but should be limited
    "widget_public": RateLimitConfig(requests=60, window_seconds=60, key_prefix="rl:widget"),
    # Widget events - batched, limit per visitor
    "widget_events": RateLimitConfig(requests=120, window_seconds=60, key_prefix="rl:events"),
    # Auth endpoints - stricter to prevent brute force
    "auth": RateLimitConfig(requests=10, window_seconds=60, key_prefix="rl:auth"),
    # General API - default fallback
    "default": RateLimitConfig(requests=100, window_seconds=60, key_prefix="rl:api"),
}


class InMemoryRateLimiter:
    """In-memory rate limiter for development/single instance deployments."""

    def __init__(self) -> None:
        # Structure: {key: [(timestamp, count), ...]}
        self._windows: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_rate_limited(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> tuple[bool, int, int]:
        """Check if request should be rate limited.

        Args:
            key: Unique identifier (IP, tenant_id, etc.)
            config: Rate limit configuration

        Returns:
            Tuple of (is_limited, remaining_requests, reset_time_seconds)
        """
        async with self._lock:
            now = time.time()
            window_start = now - config.window_seconds
            full_key = f"{config.key_prefix}:{key}"

            # Clean old entries and count requests in current window
            self._windows[full_key] = [
                (ts, count)
                for ts, count in self._windows[full_key]
                if ts > window_start
            ]

            total_requests = sum(count for _, count in self._windows[full_key])

            if total_requests >= config.requests:
                # Calculate reset time (oldest entry expiration)
                if self._windows[full_key]:
                    oldest_ts = min(ts for ts, _ in self._windows[full_key])
                    reset_seconds = int(oldest_ts + config.window_seconds - now)
                else:
                    reset_seconds = config.window_seconds
                return True, 0, max(1, reset_seconds)

            # Add new request
            self._windows[full_key].append((now, 1))
            remaining = config.requests - total_requests - 1

            return False, remaining, config.window_seconds


class RedisRateLimiter:
    """Redis-based rate limiter for distributed deployments."""

    async def is_rate_limited(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> tuple[bool, int, int]:
        """Check if request should be rate limited using Redis.

        Uses sliding window counter algorithm with Redis sorted sets.

        Args:
            key: Unique identifier (IP, tenant_id, etc.)
            config: Rate limit configuration

        Returns:
            Tuple of (is_limited, remaining_requests, reset_time_seconds)
        """
        full_key = f"{config.key_prefix}:{key}"
        now = time.time()
        window_start = now - config.window_seconds

        try:
            # Use Redis pipeline for atomic operations
            client = redis_client._client
            if client is None:
                # Fall back to allowing request if Redis unavailable
                return False, config.requests, config.window_seconds

            # Remove old entries and count current window
            pipe = client.pipeline()
            pipe.zremrangebyscore(full_key, 0, window_start)
            pipe.zcard(full_key)
            pipe.zadd(full_key, {str(now): now})
            pipe.expire(full_key, config.window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]

            if current_count >= config.requests:
                # Get oldest timestamp to calculate reset
                oldest = await client.zrange(full_key, 0, 0, withscores=True)
                if oldest:
                    reset_seconds = int(oldest[0][1] + config.window_seconds - now)
                else:
                    reset_seconds = config.window_seconds
                return True, 0, max(1, reset_seconds)

            remaining = config.requests - current_count - 1
            return False, remaining, config.window_seconds

        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}")
            # Fail open - allow request if Redis fails
            return False, config.requests, config.window_seconds


# Global rate limiter instances
_in_memory_limiter = InMemoryRateLimiter()
_redis_limiter = RedisRateLimiter()


async def check_rate_limit(
    key: str,
    config: RateLimitConfig,
) -> tuple[bool, int, int]:
    """Check rate limit using appropriate backend.

    Args:
        key: Unique identifier for rate limiting
        config: Rate limit configuration

    Returns:
        Tuple of (is_limited, remaining_requests, reset_time_seconds)
    """
    if settings.redis_enabled and redis_client._client is not None:
        return await _redis_limiter.is_rate_limited(key, config)
    return await _in_memory_limiter.is_rate_limited(key, config)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies.

    Args:
        request: FastAPI request

    Returns:
        Client IP address
    """
    # Check for forwarded headers (common with proxies/load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client
    return request.client.host if request.client else "unknown"


def rate_limit(
    config_name: str = "default",
    key_func: Callable[[Request], str] | None = None,
):
    """FastAPI dependency for rate limiting.

    Args:
        config_name: Name of rate limit config from RATE_LIMITS
        key_func: Optional function to extract rate limit key from request.
                  Defaults to using client IP.

    Returns:
        FastAPI dependency function

    Usage:
        @router.post("/chat")
        async def chat(
            request: Request,
            _: None = Depends(rate_limit("chat")),
        ):
            ...
    """
    config = RATE_LIMITS.get(config_name, RATE_LIMITS["default"])

    async def rate_limit_dependency(request: Request) -> None:
        # Get rate limit key
        if key_func:
            key = key_func(request)
        else:
            key = get_client_ip(request)

        is_limited, remaining, reset_seconds = await check_rate_limit(key, config)

        # Add rate limit headers
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = reset_seconds

        if is_limited:
            logger.warning(
                f"Rate limit exceeded for {key} on {request.url.path} "
                f"(limit: {config.requests}/{config.window_seconds}s)"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {reset_seconds} seconds.",
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Limit": str(config.requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + reset_seconds),
                },
            )

    return rate_limit_dependency
