"""Non-interactive script to add a new tenant with admin user.

Usage:
    uv run python scripts/add_tenant.py \
        --name "Customer Name" \
        --subdomain "customer" \
        --email "admin@customer.com" \
        --password "secure_password123"
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.tenant_repository import TenantRepository
from app.persistence.repositories.user_repository import UserRepository
from app.persistence.repositories.business_profile_repository import BusinessProfileRepository
from app.persistence.models.tenant import User
from app.core.password import hash_password


def validate_subdomain(subdomain: str) -> bool:
    """Validate subdomain format."""
    if not subdomain:
        return False
    import re
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$'
    return bool(re.match(pattern, subdomain)) and len(subdomain) <= 100


def validate_email(email: str) -> bool:
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


async def add_tenant(
    name: str,
    subdomain: str,
    email: str,
    password: str,
    business_name: str | None = None,
    website_url: str | None = None,
    phone_number: str | None = None,
    business_email: str | None = None,
):
    """Create a new tenant with admin user and optional business profile."""
    print("=" * 70)
    print("TENANT ONBOARDING - Adding New Tenant")
    print("=" * 70)
    print()
    
    # Validate inputs
    if not name:
        print("❌ Tenant name is required.")
        return None
    
    if not subdomain:
        print("❌ Subdomain is required.")
        return None
    
    subdomain = subdomain.lower().strip()
    if not validate_subdomain(subdomain):
        print("❌ Invalid subdomain format. Use alphanumeric characters and hyphens only.")
        return None
    
    if not email:
        print("❌ Admin email is required.")
        return None
    
    email = email.lower().strip()
    if not validate_email(email):
        print("❌ Invalid email format.")
        return None
    
    if not password or len(password) < 8:
        print("❌ Password must be at least 8 characters long.")
        return None
    
    async with AsyncSessionLocal() as db:
        try:
            # Initialize repositories
            tenant_repo = TenantRepository(db)
            user_repo = UserRepository(db)
            profile_repo = BusinessProfileRepository(db)
            
            # Check if subdomain already exists
            existing_tenant = await tenant_repo.get_by_subdomain(subdomain)
            if existing_tenant:
                print(f"❌ Subdomain '{subdomain}' is already taken (Tenant ID: {existing_tenant.id})")
                return None
            
            # Check if email already exists
            existing_user = await user_repo.get_by_email(email)
            if existing_user:
                print(f"❌ Email '{email}' is already registered (User ID: {existing_user.id})")
                return None
            
            # Create tenant
            print("Creating tenant...")
            tenant = await tenant_repo.create(
                tenant_id=None,
                name=name,
                subdomain=subdomain,
                is_active=True,
            )
            print(f"✓ Created tenant: {tenant.name} (ID: {tenant.id})")
            
            # Create admin user
            print("Creating admin user...")
            admin_user = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=hash_password(password),
                role="tenant_admin",
            )
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
            print(f"✓ Created admin user: {admin_user.email}")
            
            # Create business profile if any details provided
            if business_name or website_url or phone_number or business_email:
                print("Creating business profile...")
                profile = await profile_repo.create_for_tenant(tenant.id)
                
                await profile_repo.update_profile(
                    tenant_id=tenant.id,
                    business_name=business_name or name,
                    website_url=website_url,
                    phone_number=phone_number,
                    email=business_email or email,
                    twilio_phone=None,
                )
                print(f"✓ Created business profile")
            
            # Summary
            print()
            print("=" * 70)
            print("ONBOARDING COMPLETE!")
            print("=" * 70)
            print()
            print(f"Tenant ID: {tenant.id}")
            print(f"Tenant Name: {tenant.name}")
            print(f"Subdomain: {tenant.subdomain}")
            print()
            print("Admin User:")
            print(f"  Email: {admin_user.email}")
            print(f"  Password: [hidden]")
            print()
            print("Next Steps:")
            print()
            print("1. Login and get JWT token:")
            print(f"   POST /api/v1/auth/login")
            print(f"   Body: {{'email': '{admin_user.email}', 'password': '<your-password>'}}")
            print()
            print("2. Configure integrations (use JWT token in Authorization header):")
            print("   - SMS: POST /api/v1/admin/sms/config")
            print("   - Voice: PUT /api/v1/voice/settings")
            print("   - Email: POST /api/v1/email/oauth/start")
            print()
            print("3. Set up prompt bundle:")
            print("   POST /api/v1/tenant-setup/setup-prompt")
            print()
            print("For detailed setup instructions, see: docs/tenant_onboarding.md")
            print()
            
            return tenant
            
        except Exception as e:
            print(f"\n❌ Error during onboarding: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Parse arguments and run onboarding."""
    parser = argparse.ArgumentParser(
        description="Add a new tenant to the system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Minimal (required fields only):
  uv run python scripts/add_tenant.py --name "Acme Corp" --subdomain "acme" \\
      --email "admin@acme.com" --password "secure123"

  # With business profile:
  uv run python scripts/add_tenant.py --name "Acme Corp" --subdomain "acme" \\
      --email "admin@acme.com" --password "secure123" \\
      --business-name "Acme Corporation" --website "https://acme.com" \\
      --phone "+15555551234" --business-email "support@acme.com"
        """
    )
    
    parser.add_argument("--name", required=True, help="Tenant name")
    parser.add_argument("--subdomain", required=True, help="Subdomain (alphanumeric, hyphens allowed)")
    parser.add_argument("--email", required=True, help="Admin user email")
    parser.add_argument("--password", required=True, help="Admin user password (min 8 chars)")
    
    parser.add_argument("--business-name", help="Business name (optional, defaults to tenant name)")
    parser.add_argument("--website", help="Website URL (optional)")
    parser.add_argument("--phone", help="Phone number (optional, e.g., +15555551234)")
    parser.add_argument("--business-email", help="Business email (optional, defaults to admin email)")
    
    args = parser.parse_args()
    
    asyncio.run(add_tenant(
        name=args.name,
        subdomain=args.subdomain,
        email=args.email,
        password=args.password,
        business_name=args.business_name,
        website_url=args.website,
        phone_number=args.phone,
        business_email=args.business_email,
    ))


if __name__ == "__main__":
    main()

