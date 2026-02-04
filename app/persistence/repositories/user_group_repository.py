"""User group repository for admin operations.

Handles group creation, membership management, and queries.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.persistence.models.forum import (
    Forum,
    ForumCategory,
    GroupRole,
    UserGroup,
    UserGroupMembership,
)
from app.persistence.models.tenant import User

logger = logging.getLogger(__name__)


class UserGroupRepository:
    """Repository for user group management (admin operations)."""

    def __init__(self, session: AsyncSession):
        """Initialize user group repository."""
        self.session = session

    # --- Group CRUD ---

    async def list_groups(
        self, skip: int = 0, limit: int = 100
    ) -> list[UserGroup]:
        """List all user groups with member counts."""
        stmt = select(UserGroup).order_by(UserGroup.name).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_group_by_id(self, group_id: int) -> UserGroup | None:
        """Get group by ID."""
        stmt = select(UserGroup).where(UserGroup.id == group_id).options(
            selectinload(UserGroup.memberships).joinedload(UserGroupMembership.user),
            joinedload(UserGroup.forum)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_group_by_slug(self, slug: str) -> UserGroup | None:
        """Get group by slug."""
        stmt = select(UserGroup).where(UserGroup.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_group_by_mapping_number(self, mapping_number: int) -> UserGroup | None:
        """Get group by mapping number."""
        stmt = select(UserGroup).where(UserGroup.mapping_number == mapping_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_group(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        mapping_number: int | None = None
    ) -> UserGroup:
        """Create a new user group."""
        group = UserGroup(
            name=name,
            slug=slug,
            description=description,
            mapping_number=mapping_number
        )
        self.session.add(group)
        await self.session.commit()
        await self.session.refresh(group)
        logger.info(f"Created user group: {name} (id={group.id})")
        return group

    async def update_group(
        self, group_id: int, **data
    ) -> UserGroup | None:
        """Update a user group."""
        stmt = select(UserGroup).where(UserGroup.id == group_id)
        result = await self.session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            return None

        for key, value in data.items():
            if hasattr(group, key) and key not in ("id", "created_at"):
                setattr(group, key, value)

        await self.session.commit()
        await self.session.refresh(group)
        logger.info(f"Updated user group id={group_id}")
        return group

    async def delete_group(self, group_id: int) -> bool:
        """Delete a user group and its forum."""
        stmt = select(UserGroup).where(UserGroup.id == group_id)
        result = await self.session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            return False

        await self.session.delete(group)
        await self.session.commit()
        logger.info(f"Deleted user group id={group_id}")
        return True

    # --- Membership Management ---

    async def get_group_members(
        self, group_id: int, skip: int = 0, limit: int = 100
    ) -> list[dict]:
        """Get members of a group with user info."""
        stmt = select(UserGroupMembership).where(
            UserGroupMembership.group_id == group_id
        ).options(
            joinedload(UserGroupMembership.user)
        ).order_by(
            UserGroupMembership.joined_at.desc()
        ).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        memberships = list(result.unique().scalars().all())

        return [
            {
                "id": m.id,
                "user_id": m.user_id,
                "email": m.user.email if m.user else None,
                "tenant_id": m.user.tenant_id if m.user else None,
                "role": m.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None
            }
            for m in memberships
        ]

    async def get_member_count(self, group_id: int) -> int:
        """Get count of members in a group."""
        stmt = select(func.count()).select_from(UserGroupMembership).where(
            UserGroupMembership.group_id == group_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def add_user_to_group(
        self,
        user_id: int,
        group_id: int,
        role: str = GroupRole.MEMBER.value
    ) -> UserGroupMembership:
        """Add a user to a group."""
        # Check if already a member
        existing = await self.get_membership(user_id, group_id)
        if existing:
            logger.info(f"User {user_id} already in group {group_id}")
            return existing

        membership = UserGroupMembership(
            user_id=user_id,
            group_id=group_id,
            role=role
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        logger.info(f"Added user {user_id} to group {group_id} with role {role}")
        return membership

    async def remove_user_from_group(
        self, user_id: int, group_id: int
    ) -> bool:
        """Remove a user from a group."""
        stmt = select(UserGroupMembership).where(
            UserGroupMembership.user_id == user_id,
            UserGroupMembership.group_id == group_id
        )
        result = await self.session.execute(stmt)
        membership = result.scalar_one_or_none()

        if not membership:
            return False

        await self.session.delete(membership)
        await self.session.commit()
        logger.info(f"Removed user {user_id} from group {group_id}")
        return True

    async def get_membership(
        self, user_id: int, group_id: int
    ) -> UserGroupMembership | None:
        """Get a user's membership in a group."""
        stmt = select(UserGroupMembership).where(
            UserGroupMembership.user_id == user_id,
            UserGroupMembership.group_id == group_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_member_role(
        self, user_id: int, group_id: int, role: str
    ) -> UserGroupMembership | None:
        """Update a member's role in a group."""
        membership = await self.get_membership(user_id, group_id)
        if not membership:
            return None

        membership.role = role
        await self.session.commit()
        await self.session.refresh(membership)
        logger.info(f"Updated role for user {user_id} in group {group_id} to {role}")
        return membership

    async def is_user_in_group(self, user_id: int, group_id: int) -> bool:
        """Check if a user is a member of a group."""
        stmt = select(func.count()).select_from(UserGroupMembership).where(
            UserGroupMembership.user_id == user_id,
            UserGroupMembership.group_id == group_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() > 0

    # --- Forum Creation ---

    async def create_forum_for_group(
        self,
        group_id: int,
        name: str,
        slug: str,
        description: str | None = None
    ) -> Forum:
        """Create a forum for a group."""
        forum = Forum(
            group_id=group_id,
            name=name,
            slug=slug,
            description=description,
            is_active=True
        )
        self.session.add(forum)
        await self.session.commit()
        await self.session.refresh(forum)
        logger.info(f"Created forum '{name}' for group {group_id}")
        return forum

    async def create_forum_category(
        self,
        forum_id: int,
        name: str,
        slug: str,
        description: str | None = None,
        sort_order: int = 0,
        allows_voting: bool = False,
        admin_only_posting: bool = False,
        icon: str | None = None
    ) -> ForumCategory:
        """Create a category in a forum."""
        category = ForumCategory(
            forum_id=forum_id,
            name=name,
            slug=slug,
            description=description,
            sort_order=sort_order,
            allows_voting=allows_voting,
            admin_only_posting=admin_only_posting,
            icon=icon
        )
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        logger.info(f"Created forum category '{name}' in forum {forum_id}")
        return category

    # --- User Lookup ---

    async def get_users_not_in_group(
        self, group_id: int, search: str | None = None, limit: int = 20
    ) -> list[User]:
        """Get users not in a group (for adding members)."""
        # Subquery for users already in group
        in_group = select(UserGroupMembership.user_id).where(
            UserGroupMembership.group_id == group_id
        )

        stmt = select(User).where(
            ~User.id.in_(in_group)
        )

        if search:
            stmt = stmt.where(User.email.ilike(f"%{search}%"))

        stmt = stmt.order_by(User.email).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
