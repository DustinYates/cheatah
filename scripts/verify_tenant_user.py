"""Verify tenant user exists and optionally reset password.

Usage:
    uv run python scripts/verify_tenant_user.py --email "admin@tenant.com"
    uv run python scripts/verify_tenant_user.py --email "admin@tenant.com" --reset-password "newpassword123"
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.user_repository import UserRepository
from app.core.password import hash_password, verify_password


async def verify_user(email: str, reset_password: str | None = None):
    """Verify user exists and optionally reset password."""
    print(f"Checking for user: {email}")
    print()
    
    async with AsyncSessionLocal() as db:
        try:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_email(email)
            
            if not user:
                print(f"❌ User with email '{email}' not found in database")
                return
            
            print("✓ User found!")
            print()
            print("=" * 70)
            print("USER INFORMATION")
            print("=" * 70)
            print(f"User ID: {user.id}")
            print(f"Email: {user.email}")
            print(f"Role: {user.role}")
            print(f"Tenant ID: {user.tenant_id}")
            print()
            
            # Get tenant info
            from sqlalchemy import select
            from app.persistence.models.tenant import Tenant
            if user.tenant_id:
                stmt = select(Tenant).where(Tenant.id == user.tenant_id)
                result = await db.execute(stmt)
                tenant = result.scalar_one_or_none()
            else:
                tenant = None
            
            if tenant:
                print("TENANT INFORMATION")
                print("-" * 70)
                print(f"Tenant ID: {tenant.id}")
                print(f"Tenant Name: {tenant.name}")
                print(f"Subdomain: {tenant.subdomain}")
                print(f"Is Active: {tenant.is_active}")
                print()
            
            # Test password if provided
            if reset_password:
                print("Resetting password...")
                user.hashed_password = hash_password(reset_password)
                await db.commit()
                await db.refresh(user)
                print(f"✓ Password reset successfully")
                print()
                print("You can now login with:")
                print(f"  Email: {user.email}")
                print(f"  Password: {reset_password}")
                print()
            else:
                print("Note: To reset password, use --reset-password flag")
                print()
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Parse arguments and run verification."""
    parser = argparse.ArgumentParser(
        description="Verify tenant user exists and optionally reset password",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify user exists:
  uv run python scripts/verify_tenant_user.py --email "admin@tenant.com"

  # Reset password:
  uv run python scripts/verify_tenant_user.py --email "admin@tenant.com" --reset-password "newpassword123"
        """
    )
    
    parser.add_argument("--email", required=True, help="User email to verify")
    parser.add_argument("--reset-password", help="Optional: Reset password to this value (min 8 chars)")
    
    args = parser.parse_args()
    
    if args.reset_password and len(args.reset_password) < 8:
        print("❌ Error: Password must be at least 8 characters long")
        sys.exit(1)
    
    asyncio.run(verify_user(args.email, args.reset_password))


if __name__ == "__main__":
    main()

