"""Create a test tenant and user for development."""

import asyncio
from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.tenant_repository import TenantRepository
from app.core.password import hash_password


async def create_test_tenant():
    """Create a test tenant and admin user."""
    async with AsyncSessionLocal() as db:
        try:
            tenant_repo = TenantRepository(db)

            # Check if test tenant already exists
            existing = await tenant_repo.get_by_subdomain("test")
            if existing:
                print(f"⚠️  Test tenant already exists (ID: {existing.id})")
                print(f"   Name: {existing.name}")
                print(f"   Subdomain: {existing.subdomain}")

                # Get the admin user
                from sqlalchemy import select
                from app.persistence.models.tenant import User
                stmt = select(User).where(User.tenant_id == existing.id, User.email == "admin@test.com")
                result = await db.execute(stmt)
                admin_user = result.scalar_one_or_none()

                if admin_user:
                    print(f"\n✓ Admin user exists: admin@test.com")
                    print(f"   Password: password123")
                    print(f"   Tenant ID: {existing.id}")
                    return existing.id
                else:
                    print("\n⚠️  Creating admin user...")
            else:
                # Create tenant
                print("Creating test tenant...")
                tenant = await tenant_repo.create(
                    tenant_id=None,
                    name="Test Business",
                    subdomain="test",
                    is_active=True,
                )
                print(f"✓ Created tenant (ID: {tenant.id})")
                existing = tenant

            # Create admin user
            from app.persistence.models.tenant import User
            admin_user = User(
                tenant_id=existing.id,
                email="admin@test.com",
                hashed_password=hash_password("password123"),
                role="tenant_admin",
            )
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)

            print(f"\n{'='*60}")
            print(f"SUCCESS! Test tenant and user created")
            print(f"{'='*60}")
            print(f"Tenant ID: {existing.id}")
            print(f"Tenant Name: {existing.name}")
            print(f"Subdomain: {existing.subdomain}")
            print(f"\nAdmin User:")
            print(f"  Email: admin@test.com")
            print(f"  Password: password123")
            print(f"\nYou can now:")
            print(f"1. Login at POST /api/v1/auth/login")
            print(f"2. Use the JWT token to access protected endpoints")
            print(f"3. Test the chat at POST /api/v1/chat")

            return existing.id

        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(create_test_tenant())
