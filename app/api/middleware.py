"""Middleware for idempotency and tenant context."""

import json
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.idempotency import generate_idempotency_key
from app.infrastructure.redis import redis_client
from app.settings import settings


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
            
            # Cache response
            await redis_client.set_json(
                f"idempotency:{idempotency_key}",
                {
                    "body": body_dict,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                },
                ttl=settings.idempotency_ttl_seconds,
            )
            
            # Return new response with body
            return JSONResponse(
                content=body_dict,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        
        return response

