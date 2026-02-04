"""Forum repository for cross-tenant forum operations.

Unlike other repositories, this one does not use tenant-scoped queries.
Access is controlled via group membership checks.
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
    ForumPost,
    ForumVote,
    PostStatus,
    UserGroup,
    UserGroupMembership,
)

logger = logging.getLogger(__name__)


class ForumRepository:
    """Repository for forum operations.

    These operations are cross-tenant by design - access is controlled
    via group membership, not tenant isolation.
    """

    def __init__(self, session: AsyncSession):
        """Initialize forum repository."""
        self.session = session

    # --- Forum Access Checks ---

    async def user_has_forum_access(self, user_id: int, forum_id: int) -> bool:
        """Check if a user has access to a forum via group membership."""
        stmt = select(func.count()).select_from(UserGroupMembership).join(
            Forum, Forum.group_id == UserGroupMembership.group_id
        ).where(
            UserGroupMembership.user_id == user_id,
            Forum.id == forum_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() > 0

    async def get_user_groups(self, user_id: int) -> list[UserGroup]:
        """Get all groups a user belongs to."""
        stmt = select(UserGroup).join(
            UserGroupMembership, UserGroupMembership.group_id == UserGroup.id
        ).where(
            UserGroupMembership.user_id == user_id
        ).order_by(UserGroup.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Forum Queries ---

    async def get_forums_for_user(self, user_id: int) -> list[Forum]:
        """Get all forums accessible by a user (via group membership)."""
        stmt = select(Forum).join(
            UserGroup, UserGroup.id == Forum.group_id
        ).join(
            UserGroupMembership, UserGroupMembership.group_id == UserGroup.id
        ).where(
            UserGroupMembership.user_id == user_id,
            Forum.is_active == True
        ).options(
            joinedload(Forum.group),
            selectinload(Forum.categories)
        ).order_by(Forum.name)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get_forum_by_slug(self, slug: str) -> Forum | None:
        """Get forum by URL slug."""
        stmt = select(Forum).where(Forum.slug == slug).options(
            joinedload(Forum.group),
            selectinload(Forum.categories)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_forum_by_id(self, forum_id: int) -> Forum | None:
        """Get forum by ID."""
        stmt = select(Forum).where(Forum.id == forum_id).options(
            joinedload(Forum.group),
            selectinload(Forum.categories)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    # --- Category Queries ---

    async def get_category_by_slugs(
        self, forum_slug: str, category_slug: str
    ) -> ForumCategory | None:
        """Get category by forum and category slugs."""
        stmt = select(ForumCategory).join(
            Forum, Forum.id == ForumCategory.forum_id
        ).where(
            Forum.slug == forum_slug,
            ForumCategory.slug == category_slug
        ).options(
            joinedload(ForumCategory.forum)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_category_post_counts(self, forum_id: int) -> dict[int, int]:
        """Get post counts for all categories in a forum."""
        stmt = select(
            ForumCategory.id,
            func.count(ForumPost.id).filter(ForumPost.status == PostStatus.ACTIVE.value)
        ).outerjoin(
            ForumPost, ForumPost.category_id == ForumCategory.id
        ).where(
            ForumCategory.forum_id == forum_id
        ).group_by(ForumCategory.id)
        result = await self.session.execute(stmt)
        return dict(result.all())

    # --- Post Queries ---

    async def get_category_posts(
        self,
        category_id: int,
        status: str = "active",
        user_id: int | None = None,
        skip: int = 0,
        limit: int = 50
    ) -> list[dict]:
        """Get posts in a category with author info and vote status.

        Returns a list of dicts with post data + user_has_voted flag.
        """
        # Get posts with author info
        stmt = select(ForumPost).where(
            ForumPost.category_id == category_id,
            ForumPost.status == status
        ).options(
            joinedload(ForumPost.author),
            joinedload(ForumPost.author_tenant)
        ).order_by(
            ForumPost.is_pinned.desc(),
            ForumPost.created_at.desc()
        ).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        posts = list(result.unique().scalars().all())

        # Get user's votes for these posts
        user_voted_post_ids = set()
        if user_id and posts:
            post_ids = [p.id for p in posts]
            vote_stmt = select(ForumVote.post_id).where(
                ForumVote.post_id.in_(post_ids),
                ForumVote.user_id == user_id
            )
            vote_result = await self.session.execute(vote_stmt)
            user_voted_post_ids = set(vote_result.scalars().all())

        # Build response with vote status
        return [
            {
                "post": post,
                "user_has_voted": post.id in user_voted_post_ids
            }
            for post in posts
        ]

    async def get_post_by_id(
        self, post_id: int, user_id: int | None = None
    ) -> dict | None:
        """Get a single post with author info and vote status."""
        stmt = select(ForumPost).where(
            ForumPost.id == post_id
        ).options(
            joinedload(ForumPost.author),
            joinedload(ForumPost.author_tenant),
            joinedload(ForumPost.category).joinedload(ForumCategory.forum)
        )
        result = await self.session.execute(stmt)
        post = result.unique().scalar_one_or_none()

        if not post:
            return None

        # Check if user has voted
        user_has_voted = False
        if user_id:
            vote_stmt = select(func.count()).select_from(ForumVote).where(
                ForumVote.post_id == post_id,
                ForumVote.user_id == user_id
            )
            vote_result = await self.session.execute(vote_stmt)
            user_has_voted = vote_result.scalar() > 0

        return {
            "post": post,
            "user_has_voted": user_has_voted
        }

    async def create_post(
        self,
        category_id: int,
        author_user_id: int,
        author_tenant_id: int | None,
        title: str,
        content: str
    ) -> ForumPost:
        """Create a new forum post."""
        post = ForumPost(
            category_id=category_id,
            author_user_id=author_user_id,
            author_tenant_id=author_tenant_id,
            title=title,
            content=content,
            status=PostStatus.ACTIVE.value,
            vote_count=0
        )
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        logger.info(f"Created forum post id={post.id} by user_id={author_user_id}")
        return post

    async def update_post(
        self, post_id: int, **data
    ) -> ForumPost | None:
        """Update a forum post."""
        stmt = select(ForumPost).where(ForumPost.id == post_id)
        result = await self.session.execute(stmt)
        post = result.scalar_one_or_none()

        if not post:
            return None

        for key, value in data.items():
            if hasattr(post, key):
                setattr(post, key, value)

        await self.session.commit()
        await self.session.refresh(post)
        return post

    # --- Vote Operations ---

    async def toggle_vote(self, post_id: int, user_id: int) -> tuple[bool, int]:
        """Toggle vote on a post. Returns (is_now_voted, new_vote_count)."""
        # Check if user already voted
        vote_stmt = select(ForumVote).where(
            ForumVote.post_id == post_id,
            ForumVote.user_id == user_id
        )
        vote_result = await self.session.execute(vote_stmt)
        existing_vote = vote_result.scalar_one_or_none()

        if existing_vote:
            # Remove vote
            await self.session.delete(existing_vote)
            # Decrement vote count
            post_stmt = select(ForumPost).where(ForumPost.id == post_id)
            post_result = await self.session.execute(post_stmt)
            post = post_result.scalar_one()
            post.vote_count = max(0, post.vote_count - 1)
            await self.session.commit()
            logger.info(f"User {user_id} removed vote from post {post_id}")
            return (False, post.vote_count)
        else:
            # Add vote
            new_vote = ForumVote(post_id=post_id, user_id=user_id)
            self.session.add(new_vote)
            # Increment vote count
            post_stmt = select(ForumPost).where(ForumPost.id == post_id)
            post_result = await self.session.execute(post_stmt)
            post = post_result.scalar_one()
            post.vote_count += 1
            await self.session.commit()
            logger.info(f"User {user_id} voted on post {post_id}")
            return (True, post.vote_count)

    # --- Archive Operations ---

    async def archive_post(
        self,
        post_id: int,
        archived_by_user_id: int,
        status: str,
        resolution_notes: str | None = None
    ) -> ForumPost | None:
        """Archive a post (mark as implemented/resolved)."""
        stmt = select(ForumPost).where(ForumPost.id == post_id)
        result = await self.session.execute(stmt)
        post = result.scalar_one_or_none()

        if not post:
            return None

        post.status = status
        post.archived_at = datetime.utcnow()
        post.archived_by_user_id = archived_by_user_id
        post.resolution_notes = resolution_notes

        await self.session.commit()
        await self.session.refresh(post)
        logger.info(f"Post {post_id} archived with status={status} by user {archived_by_user_id}")
        return post
