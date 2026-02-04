#!/usr/bin/env python
"""Seed the BSS Admin group, forum, and default categories.

Also adds existing BSS tenant admins to the group.

Usage:
    uv run python scripts/seed_bss_forum.py

This script will:
1. Create the "BSS Admin" user group with mapping_number=1
2. Create the "BSS Franchise Forum" linked to that group
3. Create default categories: Announcements, Feature Requests, Bug Reports, Tips & Tricks, Open Chatter
4. Add all users with tenant_id=3 (BSS Cypress-Spring) to the group
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.persistence.models.forum import (
    UserGroup,
    UserGroupMembership,
    Forum,
    ForumCategory,
    GroupRole,
)
from app.persistence.models.tenant import User


async def seed_bss_forum():
    """Create the BSS forum with default categories."""
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

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Create or get BSS Admin group
        result = await session.execute(
            select(UserGroup).where(UserGroup.slug == "bss-admin")
        )
        group = result.scalar_one_or_none()

        if group:
            print(f"BSS Admin group already exists (id={group.id})")
        else:
            group = UserGroup(
                name="BSS Admin",
                slug="bss-admin",
                description="Administrators for British Swim School franchise locations",
                mapping_number=1,
            )
            session.add(group)
            await session.commit()
            await session.refresh(group)
            print(f"Created BSS Admin group (id={group.id})")

        # 2. Create or get BSS Forum
        result = await session.execute(
            select(Forum).where(Forum.group_id == group.id)
        )
        forum = result.scalar_one_or_none()

        if forum:
            print(f"BSS Forum already exists (id={forum.id})")
        else:
            forum = Forum(
                group_id=group.id,
                name="BSS Franchise Forum",
                slug="bss",
                description="Discussion forum for British Swim School franchise administrators. Share ideas, report issues, and collaborate with other franchises.",
                is_active=True,
            )
            session.add(forum)
            await session.commit()
            await session.refresh(forum)
            print(f"Created BSS Forum (id={forum.id})")

        # 3. Create default categories
        default_categories = [
            {
                "name": "Announcements",
                "slug": "announcements",
                "description": "Official announcements from the ConvoPro team",
                "sort_order": 0,
                "allows_voting": False,
                "admin_only_posting": True,
                "icon": "megaphone",
            },
            {
                "name": "Feature Requests",
                "slug": "feature-requests",
                "description": "Request new features and vote on ideas from other franchises",
                "sort_order": 1,
                "allows_voting": True,
                "admin_only_posting": False,
                "icon": "lightbulb",
            },
            {
                "name": "Bug Reports",
                "slug": "bug-reports",
                "description": "Report issues and bugs you've encountered",
                "sort_order": 2,
                "allows_voting": True,
                "admin_only_posting": False,
                "icon": "bug",
            },
            {
                "name": "Tips & Tricks",
                "slug": "tips-tricks",
                "description": "Share helpful tips and best practices with other franchises",
                "sort_order": 3,
                "allows_voting": False,
                "admin_only_posting": False,
                "icon": "sparkles",
            },
            {
                "name": "Open Chatter",
                "slug": "open-chatter",
                "description": "General discussion - anything goes!",
                "sort_order": 4,
                "allows_voting": False,
                "admin_only_posting": False,
                "icon": "chat",
            },
        ]

        for cat_data in default_categories:
            result = await session.execute(
                select(ForumCategory).where(
                    ForumCategory.forum_id == forum.id,
                    ForumCategory.slug == cat_data["slug"],
                )
            )
            existing_cat = result.scalar_one_or_none()

            if existing_cat:
                print(f"  Category '{cat_data['name']}' already exists")
            else:
                category = ForumCategory(
                    forum_id=forum.id,
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    description=cat_data["description"],
                    sort_order=cat_data["sort_order"],
                    allows_voting=cat_data["allows_voting"],
                    admin_only_posting=cat_data["admin_only_posting"],
                    icon=cat_data["icon"],
                )
                session.add(category)
                print(f"  Created category '{cat_data['name']}'")

        await session.commit()

        # 4. Add BSS tenant users to the group
        # Get all users from tenant_id=3 (BSS Cypress-Spring)
        bss_tenant_ids = [3]  # Add more tenant IDs here as you onboard more BSS locations

        for tenant_id in bss_tenant_ids:
            result = await session.execute(
                select(User).where(User.tenant_id == tenant_id)
            )
            users = result.scalars().all()

            for user in users:
                # Check if already a member
                result = await session.execute(
                    select(UserGroupMembership).where(
                        UserGroupMembership.user_id == user.id,
                        UserGroupMembership.group_id == group.id,
                    )
                )
                existing_membership = result.scalar_one_or_none()

                if existing_membership:
                    print(f"  User {user.email} already in BSS Admin group")
                else:
                    membership = UserGroupMembership(
                        user_id=user.id,
                        group_id=group.id,
                        role=GroupRole.MEMBER.value,
                    )
                    session.add(membership)
                    print(f"  Added user {user.email} to BSS Admin group")

        await session.commit()

        # Also add the global admin to the group
        result = await session.execute(
            select(User).where(User.role == "admin", User.tenant_id.is_(None))
        )
        admins = result.scalars().all()

        for admin in admins:
            result = await session.execute(
                select(UserGroupMembership).where(
                    UserGroupMembership.user_id == admin.id,
                    UserGroupMembership.group_id == group.id,
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                membership = UserGroupMembership(
                    user_id=admin.id,
                    group_id=group.id,
                    role=GroupRole.ADMIN.value,
                )
                session.add(membership)
                print(f"  Added global admin {admin.email} to BSS Admin group")

        await session.commit()
        print("\nBSS Forum setup complete!")
        print(f"\nForum URL: /forums/bss")


if __name__ == "__main__":
    asyncio.run(seed_bss_forum())
