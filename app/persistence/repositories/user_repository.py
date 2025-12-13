"""User repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.tenant import User
from app.persistence.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entities."""

    def __init__(self, session: AsyncSession):
        """Initialize user repository."""
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_global_admin(self) -> User | None:
        """Get global admin user (tenant_id is NULL)."""
        stmt = select(User).where(User.tenant_id.is_(None), User.role == "admin")
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

