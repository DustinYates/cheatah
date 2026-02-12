"""User repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.persistence.models.tenant import User
from app.persistence.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entities."""

    def __init__(self, session: AsyncSession):
        """Initialize user repository."""
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(func.lower(User.email) == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_global_admin(self) -> User | None:
        """Get global admin user (tenant_id is NULL)."""
        stmt = select(User).where(User.tenant_id.is_(None), User.role == "admin")
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def link_contact(self, user_id: int, contact_id: int) -> User | None:
        """Link a user to a contact by setting user.contact_id.

        Args:
            user_id: User ID
            contact_id: Contact ID to link

        Returns:
            Updated user or None if not found
        """
        user = await self.get_by_id(None, user_id)
        if not user:
            return None

        user.contact_id = contact_id
        await self.session.commit()
        await self.session.refresh(user)
        return user

