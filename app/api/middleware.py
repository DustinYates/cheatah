"""Middleware for idempotency, rate limiting, tenant context, and request tracking."""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Callable, Optional

import sentry_sdk
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.idempotency import generate_idempotency_key
from app.core.tenant_context import get_tenant_context, set_tenant_context
from app.infrastructure.redis import redis_client
from app.settings import settings

logger = logging.getLogger(__name__)

# Context variable for request ID (for distributed tracing)
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_current_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return _request_id_var.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware for request context tracking and Sentry enrichment.

    - Generates unique request IDs for correlation
    - Adds tenant context to Sentry
    - Logs request timing for performance monitoring
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with context tracking."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        _request_id_var.set(request_id)

        # Set tenant context from X-Tenant-Id header EARLY
        # This must happen BEFORE any database operations (which trigger RLS setup)
        # The deps.py layer will still validate that only global admins can use this header
        x_tenant_id = request.headers.get("X-Tenant-Id")
        if x_tenant_id:
            try:
                set_tenant_context(int(x_tenant_id))
            except (ValueError, TypeError):
                pass  # Invalid header value, deps.py will handle validation

        # Get tenant ID from context (now includes header-based context)
        tenant_id = get_tenant_context()

        # Set Sentry context for this request
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("request_id", request_id)
            if tenant_id:
                scope.set_tag("tenant_id", str(tenant_id))
                scope.set_user({"tenant_id": tenant_id})

        # Track request timing
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as e:
            # Ensure errors are captured with context
            sentry_sdk.capture_exception(e)
            raise
        finally:
            # Log request completion with timing
            duration_ms = (time.perf_counter() - start_time) * 1000
            path = str(request.url.path)

            # Skip logging for health checks and static files
            if not any(skip in path for skip in ["/health", "/static", "/assets"]):
                log_data = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code if "response" in locals() else 500,
                    "duration_ms": round(duration_ms, 2),
                }
                if tenant_id:
                    log_data["tenant_id"] = tenant_id

                logger.info(f"Request completed", extra=log_data)

        # Add request ID to response headers for client correlation
        response.headers["X-Request-ID"] = request_id
        return response


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant rate limiting middleware.

    Limits requests per tenant to prevent any single tenant from
    exhausting system resources.

    Rate limits are configurable per tier:
    - free: 100 requests/minute
    - basic: 500 requests/minute
    - pro: 2000 requests/minute
    - enterprise: 10000 requests/minute
    """

    TIER_LIMITS = {
        "free": 100,
        "basic": 500,
        "pro": 2000,
        "enterprise": 10000,
        None: 500,  # Default for unknown tiers
    }

    WINDOW_SECONDS = 60

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request with rate limit check.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response or 429 if rate limited
        """
        # Skip rate limiting if Redis is disabled
        if not settings.redis_enabled:
            return await call_next(request)

        # Skip rate limiting for webhooks and health checks
        path = str(request.url.path)
        if any(skip in path for skip in ["/sms/", "/voice/", "/health", "/docs", "/openapi"]):
            return await call_next(request)

        # Extract tenant ID from various sources
        tenant_id = await self._get_tenant_id(request)

        if tenant_id is None:
            # No tenant context, skip rate limiting
            return await call_next(request)

        # Get rate limit for this tenant (could be enhanced to fetch tier from DB)
        rate_limit = self.TIER_LIMITS.get(None)  # Default limit

        # Check rate limit
        is_allowed, remaining, reset_time = await self._check_rate_limit(
            tenant_id, rate_limit
        )

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for tenant {tenant_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after": reset_time,
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time),
                },
            )

        # Process request and add rate limit headers to response
        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    async def _get_tenant_id(self, request: Request) -> int | None:
        """Extract tenant ID from request.

        Checks X-Tenant-Id header first, then falls back to
        parsing JWT token (if available).
        """
        # Check header first (for admin impersonation)
        tenant_header = request.headers.get("X-Tenant-Id")
        if tenant_header:
            try:
                return int(tenant_header)
            except (ValueError, TypeError):
                pass

        # Could add JWT parsing here if needed, but the dependency
        # layer handles this more reliably
        return None

    async def _check_rate_limit(
        self, tenant_id: int, limit: int
    ) -> tuple[bool, int, int]:
        """Check if request is within rate limit.

        Uses Redis sliding window counter.

        Args:
            tenant_id: The tenant ID
            limit: Maximum requests per window

        Returns:
            Tuple of (is_allowed, remaining, reset_time_seconds)
        """
        await redis_client.connect()

        key = f"ratelimit:tenant:{tenant_id}"
        now = int(time.time())
        window_start = now - self.WINDOW_SECONDS

        # Use Redis pipeline for atomic operations
        if redis_client._client is None:
            # Redis not connected, skip rate limiting
            return True, 999, self.WINDOW_SECONDS
        pipe = redis_client._client.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current entries in window
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {str(now): now})
        # Set expiry on the key
        pipe.expire(key, self.WINDOW_SECONDS * 2)

        results = await pipe.execute()
        current_count = results[1]

        remaining = max(0, limit - current_count - 1)
        reset_time = self.WINDOW_SECONDS

        is_allowed = current_count < limit

        return is_allowed, remaining, reset_time


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling idempotency keys."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request with idempotency check.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response (cached if idempotent, or new)
        """
        # Skip idempotency if Redis is disabled
        if not settings.redis_enabled:
            return await call_next(request)

        # Only check idempotency for POST, PUT, PATCH, DELETE
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        # Skip idempotency for webhook endpoints (SMS, Voice) - they return XML
        path = str(request.url.path)
        if "/sms/" in path or "/voice/" in path:
            return await call_next(request)

        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")
        
        if not idempotency_key:
            # Generate key from request if not provided
            body = await request.body()
            try:
                body_dict = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_dict = {}
            idempotency_key = generate_idempotency_key(
                request.method, str(request.url.path), body_dict
            )
        
        # Check if we've seen this key before
        await redis_client.connect()
        cached_response = await redis_client.get_json(f"idempotency:{idempotency_key}")
        
        if cached_response:
            # Return cached response
            return JSONResponse(
                content=cached_response["body"],
                status_code=cached_response["status_code"],
                headers=cached_response.get("headers", {}),
            )
        
        # Process request
        response = await call_next(request)
        
        # Cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            # Read response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Parse response if JSON
            try:
                body_dict = json.loads(response_body.decode())
            except json.JSONDecodeError:
                body_dict = response_body.decode()
            
            # Cache response (exclude Content-Length as it will be recalculated)
            headers_to_cache = {
                k: v for k, v in response.headers.items()
                if k.lower() != "content-length"
            }
            await redis_client.set_json(
                f"idempotency:{idempotency_key}",
                {
                    "body": body_dict,
                    "status_code": response.status_code,
                    "headers": headers_to_cache,
                },
                ttl=settings.idempotency_ttl_seconds,
            )

            # Return new response with body (exclude Content-Length - JSONResponse recalculates it)
            return JSONResponse(
                content=body_dict,
                status_code=response.status_code,
                headers=headers_to_cache,
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Add security headers to response.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response with security headers added
        """
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking (SAMEORIGIN allows chat widget iframe embedding)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Enable HSTS (1 year, include subdomains)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Prevent XSS attacks (legacy header, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy - send origin only
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response

