"""Create a test tenant and user for local development only.

Security: Refuses to run in production. The admin email and password must
be supplied at runtime (CLI flags or environment variables); no default
credentials are baked in. The seeded account is marked
``must_change_password=True``.
"""

import argparse
import asyncio
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.tenant_repository import TenantRepository
from app.persistence.models.tenant import User
from app.core.password import hash_password


MIN_PASSWORD_LENGTH = 12


def _generate_strong_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(24))


async def create_test_tenant(email: str, password: str, subdomain: str = "test") -> int:
    """Create a test tenant and admin user with operator-supplied credentials."""
    async with AsyncSessionLocal() as db:
        tenant_repo = TenantRepository(db)

        existing = await tenant_repo.get_by_subdomain(subdomain)
        if existing:
            print(f"Test tenant already exists (ID: {existing.id})")
            tenant = existing
        else:
            print("Creating test tenant...")
            tenant = await tenant_repo.create(
                tenant_id=None,
                name="Test Business",
                subdomain=subdomain,
                is_active=True,
            )
            print(f"Created tenant (ID: {tenant.id})")

        stmt = select(User).where(User.tenant_id == tenant.id, User.email == email)
        result = await db.execute(stmt)
        admin_user = result.scalar_one_or_none()

        if admin_user:
            print(f"Admin user already exists: {email} (no action taken)")
            return tenant.id

        admin_user = User(
            tenant_id=tenant.id,
            email=email,
            hashed_password=hash_password(password),
            role="tenant_admin",
            must_change_password=True,
        )
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        print(f"\nCreated admin user: {email}")
        print("must_change_password=True — operator must rotate on first login.")
        return tenant.id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Development-only: create a test tenant and its admin user.",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("TEST_TENANT_EMAIL"),
        help="Tenant admin email (or set TEST_TENANT_EMAIL)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("TEST_TENANT_PASSWORD"),
        help=(
            "Tenant admin password (min 12 chars, or set TEST_TENANT_PASSWORD). "
            "If omitted, a random password is generated and printed once."
        ),
    )
    parser.add_argument("--subdomain", default="test")
    args = parser.parse_args()

    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment == "production":
        raise SystemExit("create_test_tenant.py is dev-only and refuses to run in production.")

    if not args.email:
        raise SystemExit("--email (or TEST_TENANT_EMAIL) is required")

    password = args.password
    generated = False
    if not password:
        password = _generate_strong_password()
        generated = True

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    asyncio.run(create_test_tenant(args.email, password, args.subdomain))

    if generated:
        print("Generated initial password (store in a password manager; will not be shown again):")
        print(password)


if __name__ == "__main__":
    main()
