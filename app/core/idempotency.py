"""Idempotency key handling utilities."""

import hashlib
import json
from typing import Any


def generate_idempotency_key(method: str, path: str, body: dict[str, Any] | None = None) -> str:
    """Generate an idempotency key from request details.

    Args:
        method: HTTP method
        path: Request path
        body: Optional request body

    Returns:
        Idempotency key string
    """
    key_parts = [method, path]
    if body:
        # Sort keys for consistent hashing
        body_str = json.dumps(body, sort_keys=True)
        key_parts.append(body_str)
    
    key_string = "|".join(key_parts)
    return hashlib.sha256(key_string.encode()).hexdigest()

