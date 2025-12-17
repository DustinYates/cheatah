"""Tests for idempotency behavior."""

import pytest

from app.core.idempotency import generate_idempotency_key
from app.infrastructure.redis import redis_client


@pytest.mark.asyncio
async def test_idempotency_key_generation():
    """Test idempotency key generation."""
    key1 = generate_idempotency_key("POST", "/conversations", {"channel": "web"})
    key2 = generate_idempotency_key("POST", "/conversations", {"channel": "web"})
    
    # Same inputs should generate same key
    assert key1 == key2
    
    # Different inputs should generate different keys
    key3 = generate_idempotency_key("POST", "/conversations", {"channel": "sms"})
    assert key1 != key3


@pytest.mark.asyncio
async def test_idempotency_redis_storage():
    """Test idempotency key storage in Redis."""
    await redis_client.connect()
    
    # Store a test response
    test_response = {
        "body": {"id": 1, "message": "test"},
        "status_code": 200,
        "headers": {},
    }
    
    await redis_client.set_json("idempotency:test_key", test_response, ttl=60)
    
    # Retrieve it
    retrieved = await redis_client.get_json("idempotency:test_key")
    assert retrieved is not None
    assert retrieved["body"]["id"] == 1
    
    # Clean up
    await redis_client.delete("idempotency:test_key")
    await redis_client.disconnect()

