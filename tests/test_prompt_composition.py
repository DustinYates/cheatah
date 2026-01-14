"""Tests for prompt composition."""

import pytest
import uuid

from app.domain.services.prompt_service import PromptService
from app.persistence.models.prompt import PromptBundle, PromptSection
from app.persistence.models.tenant import Tenant
from app.persistence.repositories.prompt_repository import PromptRepository
from app.persistence.repositories.tenant_repository import TenantRepository


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires clean database - conflicts with existing prompt bundles")
async def test_prompt_composition_global_base(db_session):
    """Test prompt composition with global base bundle."""
    prompt_service = PromptService(db_session)
    prompt_repo = PromptRepository(db_session)

    # Use unique name to avoid conflicts with existing data
    unique_name = f"Global Base {uuid.uuid4().hex[:8]}"

    # Create global base bundle
    global_bundle = await prompt_repo.create(
        None,  # Global bundle
        name=unique_name,
        version="1.0.0",
        is_active=True,
    )
    
    # Add sections to global bundle
    section1 = PromptSection(
        bundle_id=global_bundle.id,
        section_key="system",
        content="You are a helpful assistant.",
        order=1,
    )
    section2 = PromptSection(
        bundle_id=global_bundle.id,
        section_key="instructions",
        content="Be polite and professional.",
        order=2,
    )
    db_session.add(section1)
    db_session.add(section2)
    await db_session.commit()
    
    # Compose prompt (no tenant)
    prompt = await prompt_service.compose_prompt(None)
    assert "You are a helpful assistant." in prompt
    assert "Be polite and professional." in prompt


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires clean database - conflicts with existing prompt bundles")
async def test_prompt_composition_tenant_override(db_session):
    """Test prompt composition with tenant override."""
    tenant_repo = TenantRepository(db_session)
    prompt_service = PromptService(db_session)
    prompt_repo = PromptRepository(db_session)
    
    # Create tenant with unique subdomain
    unique_subdomain = f"test-{uuid.uuid4().hex[:8]}"
    tenant = await tenant_repo.create(None, name="Test Tenant", subdomain=unique_subdomain)
    
    # Create global base bundle
    global_bundle = await prompt_repo.create(
        None,
        name="Global Base",
        version="1.0.0",
        is_active=True,
    )
    global_section = PromptSection(
        bundle_id=global_bundle.id,
        section_key="system",
        content="Global system prompt",
        order=1,
    )
    db_session.add(global_section)
    await db_session.commit()
    
    # Create tenant-specific bundle
    tenant_bundle = await prompt_repo.create(
        tenant.id,
        name="Tenant Override",
        version="1.0.0",
        is_active=True,
    )
    tenant_section = PromptSection(
        bundle_id=tenant_bundle.id,
        section_key="system",
        content="Tenant-specific system prompt",
        order=1,
    )
    db_session.add(tenant_section)
    await db_session.commit()
    
    # Compose prompt for tenant (should use tenant override)
    prompt = await prompt_service.compose_prompt(tenant.id)
    assert "Tenant-specific system prompt" in prompt
    assert "Global system prompt" not in prompt

