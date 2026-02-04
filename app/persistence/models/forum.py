"""Forum models for cross-tenant discussion.

These models operate outside standard RLS since forums are cross-tenant by design.
Access is controlled via group membership checks in application code.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.tenant import Tenant, User


class GroupRole(str, Enum):
    """User role within a group."""

    MEMBER = "member"
    MODERATOR = "moderator"
    ADMIN = "admin"


class PostStatus(str, Enum):
    """Forum post status."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    IMPLEMENTED = "implemented"
    RESOLVED = "resolved"


class UserGroup(Base):
    """Cross-tenant user group for forum access.

    Groups define which users can access which forums.
    Example: "BSS Admin" group with mapping_number=1 for all British Swim School admins.
    """

    __tablename__ = "user_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    mapping_number = Column(Integer, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    memberships = relationship(
        "UserGroupMembership", back_populates="group", cascade="all, delete-orphan"
    )
    forum = relationship("Forum", back_populates="group", uselist=False)


class UserGroupMembership(Base):
    """Junction table for user-group membership.

    Links users to groups with an optional role (member, moderator, admin).
    """

    __tablename__ = "user_group_memberships"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id = Column(
        Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(50), default=GroupRole.MEMBER.value, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    group = relationship("UserGroup", back_populates="memberships")


class Forum(Base):
    """Forum linked to a user group.

    One forum per group. Users in the group can access the forum.
    """

    __tablename__ = "forums"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(
        Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    group = relationship("UserGroup", back_populates="forum")
    categories = relationship("ForumCategory", back_populates="forum", cascade="all, delete-orphan")


class ForumCategory(Base):
    """Category within a forum.

    Categories organize posts within a forum (e.g., Feature Requests, Bug Reports).
    """

    __tablename__ = "forum_categories"
    __table_args__ = (UniqueConstraint("forum_id", "slug", name="uq_forum_category_slug"),)

    id = Column(Integer, primary_key=True, index=True)
    forum_id = Column(
        Integer, ForeignKey("forums.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    allows_voting = Column(Boolean, default=False, nullable=False)
    admin_only_posting = Column(Boolean, default=False, nullable=False)
    icon = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    forum = relationship("Forum", back_populates="categories")
    posts = relationship("ForumPost", back_populates="category", cascade="all, delete-orphan")


class ForumPost(Base):
    """Post in a forum category.

    Posts can be voted on (if category allows) and archived by admins.
    """

    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer, ForeignKey("forum_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default=PostStatus.ACTIVE.value, nullable=False, index=True)
    vote_count = Column(Integer, default=0, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    archived_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    category = relationship("ForumCategory", back_populates="posts")
    author = relationship("User", foreign_keys=[author_user_id])
    author_tenant = relationship("Tenant", foreign_keys=[author_tenant_id])
    archived_by = relationship("User", foreign_keys=[archived_by_user_id])
    votes = relationship("ForumVote", back_populates="post", cascade="all, delete-orphan")


class ForumVote(Base):
    """Upvote on a forum post.

    Each user can only vote once per post.
    """

    __tablename__ = "forum_votes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_vote"),)

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(
        Integer, ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    post = relationship("ForumPost", back_populates="votes")
    user = relationship("User")


class ForumComment(Base):
    """Comment/reply on a forum post (Reddit-style).

    Supports nested replies via parent_comment_id.
    Score is calculated as upvotes - downvotes.
    """

    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(
        Integer, ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_comment_id = Column(
        Integer, ForeignKey("forum_comments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    content = Column(Text, nullable=False)
    score = Column(Integer, default=0, nullable=False)  # upvotes - downvotes
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    post = relationship("ForumPost")
    parent_comment = relationship("ForumComment", remote_side=[id], backref="replies")
    author = relationship("User", foreign_keys=[author_user_id])
    author_tenant = relationship("Tenant", foreign_keys=[author_tenant_id])
    votes = relationship("ForumCommentVote", back_populates="comment", cascade="all, delete-orphan")


class ForumCommentVote(Base):
    """Vote on a forum comment (upvote +1 or downvote -1).

    Each user can only vote once per comment.
    """

    __tablename__ = "forum_comment_votes"
    __table_args__ = (UniqueConstraint("comment_id", "user_id", name="uq_comment_vote"),)

    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(
        Integer, ForeignKey("forum_comments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vote_value = Column(Integer, nullable=False)  # +1 for upvote, -1 for downvote
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    comment = relationship("ForumComment", back_populates="votes")
    user = relationship("User")
