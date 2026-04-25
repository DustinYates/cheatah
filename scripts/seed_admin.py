#!/usr/bin/env python
"""Seed an initial global admin user for the application.

Security: No shared/default credentials. The admin email and password
MUST be supplied by the operator at runtime (via CLI flags or environment
variables). The seeded account is marked with ``must_change_password=True``
so the initial operator-supplied password cannot be reused beyond first
login. This script also refuses to run in production unless an explicit
override is set.
"""

import argparse
import asyncio
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.persistence.models.tenant import User
from app.core.password import hash_password


MIN_PASSWORD_LENGTH = 12


def _generate_strong_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(24))


async def seed_admin(email: str, password: str) -> None:
    """Create the initial global admin user with an operator-supplied credential."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if "?" in database_url:
        base_url, params = database_url.split("?", 1)
        params_list = [p for p in params.split("&") if not p.startswith("sslmode=")]
        database_url = base_url + ("?" + "&".join(params_list) if params_list else "")

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Admin user already exists: {email} (no action taken)")
            return

        admin_user = User(
            tenant_id=None,
            email=email,
            hashed_password=hash_password(password),
            role="admin",
            must_change_password=True,
        )
        session.add(admin_user)
        await session.commit()
        print(f"Created initial admin user: {email}")
        print("must_change_password=True — operator must rotate on first login.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create the initial admin user. Credentials MUST be supplied by the "
            "operator; this script never uses a hardcoded default."
        )
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("SEED_ADMIN_EMAIL"),
        help="Admin email (or set SEED_ADMIN_EMAIL)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SEED_ADMIN_PASSWORD"),
        help=(
            "Admin password (or set SEED_ADMIN_PASSWORD). Minimum 12 chars. "
            "If omitted entirely, a random password is generated and printed once."
        ),
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Required to run when ENVIRONMENT=production",
    )
    args = parser.parse_args()

    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment == "production" and not args.allow_production:
        raise SystemExit(
            "Refusing to run in production without --allow-production. "
            "Prefer provisioning the initial admin via IAM-managed console tooling."
        )

    if not args.email:
        raise SystemExit("--email (or SEED_ADMIN_EMAIL) is required")

    password = args.password
    generated = False
    if not password:
        password = _generate_strong_password()
        generated = True

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    asyncio.run(seed_admin(args.email, password))

    if generated:
        print("Generated initial password (store in a password manager; will not be shown again):")
        print(password)


if __name__ == "__main__":
    main()
