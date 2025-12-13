"""Tests for conversation persistence."""

import pytest

from app.domain.services.conversation_service import ConversationService
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.tenant_repository import TenantRepository


@pytest.mark.asyncio
async def test_conversation_message_chronological_order(db_session):
    """Test that messages are stored and retrieved in chronological order."""
    tenant_repo = TenantRepository(db_session)
    conversation_service = ConversationService(db_session)
    
    # Create tenant
    tenant = await tenant_repo.create(None, name="Test Tenant", subdomain="test")
    
    # Create conversation
    conversation = await conversation_service.create_conversation(
        tenant.id, channel="web"
    )
    
    # Add messages in order
    msg1 = await conversation_service.add_message(
        tenant.id, conversation.id, "user", "Hello"
    )
    msg2 = await conversation_service.add_message(
        tenant.id, conversation.id, "assistant", "Hi there!"
    )
    msg3 = await conversation_service.add_message(
        tenant.id, conversation.id, "user", "How are you?"
    )
    
    # Retrieve conversation history
    history = await conversation_service.get_conversation_history(
        tenant.id, conversation.id
    )
    
    # Verify chronological order
    assert len(history) == 3
    assert history[0].id == msg1.id
    assert history[0].sequence_number == 1
    assert history[1].id == msg2.id
    assert history[1].sequence_number == 2
    assert history[2].id == msg3.id
    assert history[2].sequence_number == 3

