#!/usr/bin/env python
"""Seed an initial global admin user for the application."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.persistence.models.tenant import User
from app.core.password import hash_password


async def seed_admin():
    """Create the initial global admin user."""
    database_url = os.environ.get("DATABASE_URL", "")
    
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Remove sslmode parameter as asyncpg handles it differently
    if "?" in database_url:
        base_url, params = database_url.split("?", 1)
        params_list = [p for p in params.split("&") if not p.startswith("sslmode=")]
        database_url = base_url + ("?" + "&".join(params_list) if params_list else "")
    
    engine = create_async_engine(database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    admin_email = "admin@chattercheetah.com"
    admin_password = "admin123"
    
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"Admin user already exists: {admin_email}")
            return
        
        admin_user = User(
            tenant_id=None,
            email=admin_email,
            hashed_password=hash_password(admin_password),
            role="admin"
        )
        session.add(admin_user)
        await session.commit()
        print(f"Created global admin user: {admin_email}")
        print(f"Password: {admin_password}")
        print("Please change this password after first login!")

if __name__ == "__main__":
    asyncio.run(seed_admin())
