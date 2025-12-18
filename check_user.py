#!/usr/bin/env python
"""Check if user exists in database."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select
from app.persistence.models.tenant import User

async def check_user():
    """Check if admin@test.com exists."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CHECKING FOR USER: admin@test.com")
        print("=" * 80)
        
        stmt = select(User).where(User.email == "admin@test.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            print(f"\n✅ User found!")
            print(f"  ID: {user.id}")
            print(f"  Email: {user.email}")
            print(f"  Tenant ID: {user.tenant_id}")
            print(f"  Role: {user.role}")
        else:
            print(f"\n❌ User 'admin@test.com' not found")
            print("\nChecking for other users...")
            all_stmt = select(User)
            all_result = await session.execute(all_stmt)
            all_users = all_result.scalars().all()
            
            if all_users:
                print(f"\nFound {len(all_users)} user(s) in database:")
                for u in all_users:
                    print(f"  - {u.email} (Tenant: {u.tenant_id}, Role: {u.role})")
            else:
                print("\nNo users found in database")
            
            print("\n💡 You can create the test user with:")
            print("   python scripts/create_test_tenant.py")

if __name__ == "__main__":
    asyncio.run(check_user())

