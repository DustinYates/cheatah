"""Tests for tenant isolation."""

import pytest
import uuid

from app.persistence.models.conversation import Conversation
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.tenant_repository import TenantRepository


@pytest.mark.asyncio
async def test_tenant_isolation_in_queries(db_session):
    """Test that queries are properly isolated by tenant_id."""
    tenant_repo = TenantRepository(db_session)

    # Create two tenants with unique subdomains
    unique_id = uuid.uuid4().hex[:8]
    tenant1 = await tenant_repo.create(None, name="Tenant 1", subdomain=f"tenant1-{unique_id}")
    tenant2 = await tenant_repo.create(None, name="Tenant 2", subdomain=f"tenant2-{unique_id}")
    
    # Create conversations for each tenant
    conv_repo = ConversationRepository(db_session)
    conv1 = await conv_repo.create(tenant1.id, channel="web")
    conv2 = await conv_repo.create(tenant2.id, channel="web")
    
    # Verify tenant1 can only see their conversation
    tenant1_convs = await conv_repo.list(tenant1.id)
    assert len(tenant1_convs) == 1
    assert tenant1_convs[0].id == conv1.id
    
    # Verify tenant2 can only see their conversation
    tenant2_convs = await conv_repo.list(tenant2.id)
    assert len(tenant2_convs) == 1
    assert tenant2_convs[0].id == conv2.id
    
    # Verify tenant1 cannot access tenant2's conversation
    conv2_from_tenant1 = await conv_repo.get_by_id(tenant1.id, conv2.id)
    assert conv2_from_tenant1 is None

