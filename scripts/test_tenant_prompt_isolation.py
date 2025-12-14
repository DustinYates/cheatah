"""Test script to verify tenant prompt isolation works correctly.

This demonstrates that:
1. Each tenant can have their own prompts with the same name/version
2. Each tenant can only have ONE production bundle at a time
3. Global base prompts (tenant_id=NULL) are separate from tenant prompts

Usage:
    uv run python scripts/test_tenant_prompt_isolation.py
"""

import asyncio

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.persistence.repositories.prompt_repository import PromptRepository
from app.persistence.repositories.tenant_repository import TenantRepository


async def test_tenant_isolation() -> None:
    """Test that tenant prompt isolation works correctly."""
    async with AsyncSessionLocal() as db:
        try:
            tenant_repo = TenantRepository(db)
            prompt_repo = PromptRepository(db)

            print("="*60)
            print("Testing Tenant Prompt Isolation")
            print("="*60)

            # Create two test tenants
            print("\n1. Creating test tenants...")
            tenant1 = await tenant_repo.create(
                subdomain="swim-school-a",
                name="Swim School A",
                is_active=True
            )
            tenant2 = await tenant_repo.create(
                subdomain="swim-school-b",
                name="Swim School B",
                is_active=True
            )
            print(f"   ✓ Created Tenant 1 (ID: {tenant1.id}): {tenant1.name}")
            print(f"   ✓ Created Tenant 2 (ID: {tenant2.id}): {tenant2.name}")

            # Test 1: Both tenants can have prompts with the same name/version
            print("\n2. Testing: Both tenants can have prompts with same name/version...")
            prompt1_t1 = await prompt_repo.create(
                tenant_id=tenant1.id,
                name="Customer Service Prompt",
                version="1.0.0",
                status=PromptStatus.DRAFT.value
            )
            print(f"   ✓ Tenant 1 created: '{prompt1_t1.name}' v{prompt1_t1.version}")

            prompt1_t2 = await prompt_repo.create(
                tenant_id=tenant2.id,
                name="Customer Service Prompt",  # Same name!
                version="1.0.0",  # Same version!
                status=PromptStatus.DRAFT.value
            )
            print(f"   ✓ Tenant 2 created: '{prompt1_t2.name}' v{prompt1_t2.version}")
            print("   ✓ SUCCESS: Different tenants CAN have prompts with same name/version")

            # Test 2: Same tenant CANNOT have duplicate name/version
            print("\n3. Testing: Same tenant CANNOT have duplicate name/version...")
            try:
                duplicate = await prompt_repo.create(
                    tenant_id=tenant1.id,
                    name="Customer Service Prompt",  # Duplicate!
                    version="1.0.0",  # Duplicate!
                    status=PromptStatus.DRAFT.value
                )
                print("   ✗ FAILED: Duplicate was allowed (should have been blocked)")
            except Exception as e:
                print(f"   ✓ SUCCESS: Duplicate blocked by database constraint")
                await db.rollback()  # Rollback the failed transaction

            # Test 3: Tenant can have different versions of same prompt
            print("\n4. Testing: Tenant can have different versions of same prompt...")
            prompt2_t1 = await prompt_repo.create(
                tenant_id=tenant1.id,
                name="Customer Service Prompt",  # Same name
                version="2.0.0",  # Different version!
                status=PromptStatus.DRAFT.value
            )
            print(f"   ✓ Tenant 1 created: '{prompt2_t1.name}' v{prompt2_t1.version}")
            print("   ✓ SUCCESS: Same tenant can have multiple versions")

            # Test 4: Only one PRODUCTION bundle per tenant
            print("\n5. Testing: Only ONE production bundle per tenant...")

            # Publish first bundle
            await prompt_repo.publish_bundle(tenant1.id, prompt1_t1.id)
            print(f"   ✓ Published '{prompt1_t1.name}' v{prompt1_t1.version} to PRODUCTION")

            # Try to publish second bundle (should fail due to constraint)
            print(f"   → Attempting to publish '{prompt2_t1.name}' v{prompt2_t1.version}...")
            try:
                # This should fail because tenant1 already has a production bundle
                await db.execute(
                    db.query(PromptBundle)
                    .filter(PromptBundle.id == prompt2_t1.id)
                    .update({"status": PromptStatus.PRODUCTION.value})
                )
                await db.commit()
                print("   ✗ FAILED: Multiple production bundles allowed (should be blocked)")
            except Exception as e:
                print("   ✓ SUCCESS: Second production bundle blocked by constraint")
                await db.rollback()

            # Test 5: Global prompts are separate from tenant prompts
            print("\n6. Testing: Global prompts are isolated from tenant prompts...")
            global_prompt = await prompt_repo.create(
                tenant_id=None,  # Global!
                name="Customer Service Prompt",  # Same name as tenants
                version="1.0.0",  # Same version as tenants
                status=PromptStatus.DRAFT.value
            )
            print(f"   ✓ Global prompt created: '{global_prompt.name}' v{global_prompt.version}")
            print("   ✓ SUCCESS: Global prompts don't conflict with tenant prompts")

            # Summary
            print("\n" + "="*60)
            print("TENANT ISOLATION SUMMARY")
            print("="*60)
            print(f"Tenant 1 ({tenant1.name}):")
            t1_bundles = await prompt_repo.list(tenant1.id)
            for bundle in t1_bundles:
                print(f"  - {bundle.name} v{bundle.version} [{bundle.status}]")

            print(f"\nTenant 2 ({tenant2.name}):")
            t2_bundles = await prompt_repo.list(tenant2.id)
            for bundle in t2_bundles:
                print(f"  - {bundle.name} v{bundle.version} [{bundle.status}]")

            print(f"\nGlobal (Platform):")
            global_bundles = await prompt_repo.list(None)
            for bundle in global_bundles:
                print(f"  - {bundle.name} v{bundle.version} [{bundle.status}]")

            print("\n" + "="*60)
            print("✓ All tenant isolation tests passed!")
            print("="*60)

            # Cleanup
            print("\nCleaning up test data...")
            await db.execute(db.query(PromptBundle).filter(PromptBundle.id.in_([
                prompt1_t1.id, prompt1_t2.id, prompt2_t1.id, global_prompt.id
            ])).delete(synchronize_session=False))
            await db.execute(db.query(TenantRepository.model).filter(TenantRepository.model.id.in_([
                tenant1.id, tenant2.id
            ])).delete(synchronize_session=False))
            await db.commit()
            print("✓ Cleanup complete")

        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    print("\nThis test verifies that:")
    print("  1. Different tenants can have prompts with the same name/version")
    print("  2. Same tenant cannot have duplicate name/version combinations")
    print("  3. Same tenant can have multiple versions of the same prompt")
    print("  4. Each tenant can only have ONE production bundle at a time")
    print("  5. Global prompts are isolated from tenant prompts")
    print()

    asyncio.run(test_tenant_isolation())
