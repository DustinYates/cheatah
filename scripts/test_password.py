"""Test password verification for a user."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.user_repository import UserRepository
from app.core.password import verify_password


async def test_password(email: str, password: str):
    """Test if password is correct for user."""
    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_email(email)
        
        if not user:
            print(f"❌ User not found: {email}")
            return False
        
        is_valid = verify_password(password, user.hashed_password)
        
        if is_valid:
            print(f"✓ Password is correct for {email}")
        else:
            print(f"❌ Password is incorrect for {email}")
        
        return is_valid


if __name__ == "__main__":
    email = "dustin.yates@gmail.com"
    password = "Hudlink2168"
    
    result = asyncio.run(test_password(email, password))
    sys.exit(0 if result else 1)

