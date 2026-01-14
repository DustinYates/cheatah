"""Integration tests for voice features with database."""

import pytest
import uuid
from datetime import datetime

from sqlalchemy import select

from app.persistence.models.call import Call
from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.repositories.call_repository import CallRepository


@pytest.mark.asyncio
async def test_call_repository_create(db_session):
    """Test CallRepository can create a call record."""
    # Create a tenant first with unique subdomain
    unique_id = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Test Tenant", subdomain=f"test-voice-{unique_id}", is_active=True)
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
        started_at=datetime.utcnow(),
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
    # Create a tenant and call with unique subdomain
    unique_id = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Test Tenant", subdomain=f"test-voice-2-{unique_id}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    unique_call_sid = f"CA_FIND_ME_{unique_id}"
    call = Call(
        tenant_id=tenant.id,
        call_sid=unique_call_sid,
        from_number="+1234567890",
        to_number="+0987654321",
        status="in-progress",
        direction="inbound",
    )
    db_session.add(call)
    await db_session.commit()
    
    # Find by SID
    call_repo = CallRepository(db_session)
    found_call = await call_repo.get_by_call_sid(unique_call_sid)

    assert found_call is not None
    assert found_call.call_sid == unique_call_sid
    assert found_call.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_call_repository_get_by_tenant(db_session):
    """Test CallRepository can list calls by tenant."""
    # Create two tenants with calls with unique subdomains
    unique_id = uuid.uuid4().hex[:8]
    tenant1 = Tenant(name="Tenant 1", subdomain=f"tenant-1-voice-{unique_id}", is_active=True)
    tenant2 = Tenant(name="Tenant 2", subdomain=f"tenant-2-voice-{unique_id}", is_active=True)
    db_session.add_all([tenant1, tenant2])
    await db_session.flush()
    
    # Add calls for each tenant with unique call_sids
    call1_sid = f"CA_T1_CALL_{unique_id}"
    call2_sid = f"CA_T2_CALL_{unique_id}"
    call1 = Call(
        tenant_id=tenant1.id,
        call_sid=call1_sid,
        from_number="+1111111111",
        to_number="+2222222222",
        status="completed",
        direction="inbound",
    )
    call2 = Call(
        tenant_id=tenant2.id,
        call_sid=call2_sid,
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

    assert len(tenant1_calls) >= 1
    assert any(c.call_sid == call1_sid for c in tenant1_calls)


@pytest.mark.asyncio
async def test_call_status_update(db_session):
    """Test updating call status and recording info."""
    # Create tenant and call with unique subdomain
    unique_id = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Test Tenant", subdomain=f"test-update-{unique_id}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    call = Call(
        tenant_id=tenant.id,
        call_sid=f"CA_UPDATE_ME_{unique_id}",
        from_number="+1234567890",
        to_number="+0987654321",
        status="in-progress",
        direction="inbound",
        started_at=datetime.utcnow(),
    )
    db_session.add(call)
    await db_session.commit()
    
    # Update the call
    call.status = "completed"
    call.duration = 120
    call.recording_sid = "RE_TEST_123"
    call.recording_url = "https://api.twilio.com/recordings/RE_TEST_123"
    call.ended_at = datetime.utcnow()
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
    # Create tenant with unique subdomain
    unique_id = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Voice Tenant", subdomain=f"voice-tenant-{unique_id}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    
    # Create business profile with voice phone using unique phone number
    unique_phone = f"+1555{unique_id[:7]}"
    profile = TenantBusinessProfile(
        tenant_id=tenant.id,
        business_name="Test Business",
        twilio_voice_phone=unique_phone,
    )
    db_session.add(profile)
    await db_session.commit()

    # Query back
    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.twilio_voice_phone == unique_phone
    )
    result = await db_session.execute(stmt)
    found_profile = result.scalar_one_or_none()

    assert found_profile is not None
    assert found_profile.tenant_id == tenant.id
    assert found_profile.twilio_voice_phone == unique_phone


@pytest.mark.asyncio
async def test_call_tenant_relationship(db_session):
    """Test Call model has correct relationship to Tenant."""
    # Create tenant with unique subdomain
    unique_id = uuid.uuid4().hex[:8]
    tenant = Tenant(name="Related Tenant", subdomain=f"related-tenant-{unique_id}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    # Create call with unique call_sid
    call = Call(
        tenant_id=tenant.id,
        call_sid=f"CA_RELATED_{unique_id}",
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

