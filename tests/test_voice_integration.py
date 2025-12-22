"""Integration tests for voice features with database."""

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.persistence.models.call import Call
from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.call_repository import CallRepository


@pytest.mark.asyncio
async def test_call_repository_create(db_session):
    """Test CallRepository can create a call record."""
    # Create a tenant first
    tenant = Tenant(name="Test Tenant", subdomain="test-voice", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    # Create call using repository
    call_repo = CallRepository(db_session)
    call = await call_repo.create(
        tenant_id=tenant.id,
        call_sid="CA_TEST_123",
        from_number="+1234567890",
        to_number="+0987654321",
        status="ringing",
        direction="inbound",
        started_at=datetime.now(timezone.utc),
    )
    
    assert call.id is not None
    assert call.tenant_id == tenant.id
    assert call.call_sid == "CA_TEST_123"
    assert call.from_number == "+1234567890"
    assert call.to_number == "+0987654321"
    assert call.status == "ringing"
    assert call.direction == "inbound"


@pytest.mark.asyncio
async def test_call_repository_get_by_call_sid(db_session):
    """Test CallRepository can find a call by SID."""
    # Create a tenant and call
    tenant = Tenant(name="Test Tenant", subdomain="test-voice-2", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    call = Call(
        tenant_id=tenant.id,
        call_sid="CA_FIND_ME",
        from_number="+1234567890",
        to_number="+0987654321",
        status="in-progress",
        direction="inbound",
    )
    db_session.add(call)
    await db_session.commit()
    
    # Find by SID
    call_repo = CallRepository(db_session)
    found_call = await call_repo.get_by_call_sid("CA_FIND_ME")
    
    assert found_call is not None
    assert found_call.call_sid == "CA_FIND_ME"
    assert found_call.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_call_repository_get_by_tenant(db_session):
    """Test CallRepository can list calls by tenant."""
    # Create two tenants with calls
    tenant1 = Tenant(name="Tenant 1", subdomain="tenant-1-voice", is_active=True)
    tenant2 = Tenant(name="Tenant 2", subdomain="tenant-2-voice", is_active=True)
    db_session.add_all([tenant1, tenant2])
    await db_session.flush()
    
    # Add calls for each tenant
    call1 = Call(
        tenant_id=tenant1.id,
        call_sid="CA_T1_CALL",
        from_number="+1111111111",
        to_number="+2222222222",
        status="completed",
        direction="inbound",
    )
    call2 = Call(
        tenant_id=tenant2.id,
        call_sid="CA_T2_CALL",
        from_number="+3333333333",
        to_number="+4444444444",
        status="completed",
        direction="inbound",
    )
    db_session.add_all([call1, call2])
    await db_session.commit()
    
    # Get calls for tenant 1
    call_repo = CallRepository(db_session)
    tenant1_calls = await call_repo.get_by_tenant(tenant1.id)
    
    assert len(tenant1_calls) == 1
    assert tenant1_calls[0].call_sid == "CA_T1_CALL"


@pytest.mark.asyncio
async def test_call_status_update(db_session):
    """Test updating call status and recording info."""
    # Create tenant and call
    tenant = Tenant(name="Test Tenant", subdomain="test-update", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    call = Call(
        tenant_id=tenant.id,
        call_sid="CA_UPDATE_ME",
        from_number="+1234567890",
        to_number="+0987654321",
        status="in-progress",
        direction="inbound",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.commit()
    
    # Update the call
    call.status = "completed"
    call.duration = 120
    call.recording_sid = "RE_TEST_123"
    call.recording_url = "https://api.twilio.com/recordings/RE_TEST_123"
    call.ended_at = datetime.now(timezone.utc)
    await db_session.commit()
    
    # Verify update persisted
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.duration == 120
    assert call.recording_sid == "RE_TEST_123"
    assert call.ended_at is not None


@pytest.mark.asyncio
async def test_tenant_voice_phone_storage(db_session):
    """Test storing voice phone number in TenantBusinessProfile."""
    # Create tenant
    tenant = Tenant(name="Voice Tenant", subdomain="voice-tenant", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    # Create business profile with voice phone
    profile = TenantBusinessProfile(
        tenant_id=tenant.id,
        business_name="Test Business",
        twilio_voice_phone="+15551234567",
    )
    db_session.add(profile)
    await db_session.commit()
    
    # Query back
    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.twilio_voice_phone == "+15551234567"
    )
    result = await db_session.execute(stmt)
    found_profile = result.scalar_one_or_none()
    
    assert found_profile is not None
    assert found_profile.tenant_id == tenant.id
    assert found_profile.twilio_voice_phone == "+15551234567"


@pytest.mark.asyncio
async def test_call_tenant_relationship(db_session):
    """Test Call model has correct relationship to Tenant."""
    # Create tenant
    tenant = Tenant(name="Related Tenant", subdomain="related-tenant", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    # Create call
    call = Call(
        tenant_id=tenant.id,
        call_sid="CA_RELATED",
        from_number="+1234567890",
        to_number="+0987654321",
        status="completed",
        direction="inbound",
    )
    db_session.add(call)
    await db_session.commit()
    
    # Access tenant through relationship
    await db_session.refresh(call, ["tenant"])
    assert call.tenant is not None
    assert call.tenant.name == "Related Tenant"

