"""Forum API endpoints for cross-tenant discussion.

Forums are accessible based on user group membership, not tenant isolation.
"""

from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, is_global_admin
from app.persistence.database import get_db_no_rls
from app.persistence.models.forum import PostStatus
from app.persistence.models.tenant import User
from app.persistence.repositories.forum_repository import ForumRepository

router = APIRouter()


def _isoformat_utc(dt):
    """Convert datetime to UTC ISO format."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# --- Response Models ---

class CategoryResponse(BaseModel):
    """Forum category response."""

    id: int
    name: str
    slug: str
    description: str | None
    allows_voting: bool
    admin_only_posting: bool
    post_count: int = 0
    icon: str | None = None

    class Config:
        from_attributes = True


class ForumResponse(BaseModel):
    """Forum response with categories."""

    id: int
    name: str
    slug: str
    description: str | None
    group_name: str
    categories: list[CategoryResponse]

    class Config:
        from_attributes = True


class ForumListItem(BaseModel):
    """Forum list item (without full category details)."""

    id: int
    name: str
    slug: str
    description: str | None
    group_name: str
    total_post_count: int = 0
    member_count: int = 0
    last_activity: str | None = None


class PostListItem(BaseModel):
    """Post in list view."""

    id: int
    title: str
    status: str
    vote_count: int
    author_email: str
    author_tenant_name: str | None
    is_pinned: bool
    created_at: str
    user_has_voted: bool


class PostDetail(BaseModel):
    """Full post detail."""

    id: int
    title: str
    content: str
    status: str
    vote_count: int
    author_email: str
    author_tenant_name: str | None
    is_pinned: bool
    created_at: str
    updated_at: str
    user_has_voted: bool
    resolution_notes: str | None
    category_name: str
    category_slug: str
    forum_slug: str


class PostCreate(BaseModel):
    """Create post request."""

    title: str
    content: str


class ArchivePost(BaseModel):
    """Archive post request."""

    status: str  # 'implemented' or 'resolved'
    resolution_notes: str | None = None


class VoteResponse(BaseModel):
    """Vote toggle response."""

    user_has_voted: bool
    vote_count: int


class CommentResponse(BaseModel):
    """Comment in response."""

    id: int
    post_id: int
    parent_comment_id: int | None
    author_email: str | None
    author_tenant_name: str | None
    content: str
    score: int
    is_deleted: bool
    created_at: str | None
    user_vote: int  # +1, -1, or 0


class CommentCreate(BaseModel):
    """Create comment request."""

    content: str
    parent_comment_id: int | None = None


class CommentVote(BaseModel):
    """Vote on comment request."""

    vote_value: int  # +1 for upvote, -1 for downvote, 0 to remove


class CommentVoteResponse(BaseModel):
    """Vote on comment response."""

    user_vote: int
    score: int


# --- Helper Functions ---

async def _verify_forum_access(
    forum_slug: str,
    user: User,
    repo: ForumRepository
) -> "Forum":
    """Verify user has access to the forum."""
    from app.persistence.models.forum import Forum

    forum = await repo.get_forum_by_slug(forum_slug)
    if not forum:
        raise HTTPException(status_code=404, detail="Forum not found")

    # Global admins have access to all forums
    if is_global_admin(user):
        return forum

    # Check group membership
    has_access = await repo.user_has_forum_access(user.id, forum.id)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this forum")

    return forum


# --- Endpoints ---

@router.get("/my-forums", response_model=list[ForumListItem])
async def list_my_forums(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> list[ForumListItem]:
    """List all forums the current user has access to."""
    repo = ForumRepository(db)

    # Global admins see all forums - get them differently
    if is_global_admin(current_user):
        # For now, global admins also use group membership
        # Could expand this later to show all forums
        pass

    forums = await repo.get_forums_for_user(current_user.id)

    # Fetch aggregate stats for all forums in one batch
    forum_ids = [f.id for f in forums]
    stats = await repo.get_forum_stats(forum_ids) if forum_ids else {}

    return [
        ForumListItem(
            id=forum.id,
            name=forum.name,
            slug=forum.slug,
            description=forum.description,
            group_name=forum.group.name if forum.group else "",
            total_post_count=stats.get(forum.id, {}).get("total_post_count", 0),
            member_count=stats.get(forum.id, {}).get("member_count", 0),
            last_activity=_isoformat_utc(stats.get(forum.id, {}).get("last_activity")),
        )
        for forum in forums
    ]


@router.get("/{forum_slug}", response_model=ForumResponse)
async def get_forum(
    forum_slug: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> ForumResponse:
    """Get forum details with categories."""
    repo = ForumRepository(db)
    forum = await _verify_forum_access(forum_slug, current_user, repo)

    # Get post counts per category
    post_counts = await repo.get_category_post_counts(forum.id)

    categories = [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            slug=cat.slug,
            description=cat.description,
            allows_voting=cat.allows_voting,
            admin_only_posting=cat.admin_only_posting,
            post_count=post_counts.get(cat.id, 0),
            icon=cat.icon
        )
        for cat in sorted(forum.categories, key=lambda c: c.sort_order)
    ]

    return ForumResponse(
        id=forum.id,
        name=forum.name,
        slug=forum.slug,
        description=forum.description,
        group_name=forum.group.name if forum.group else "",
        categories=categories
    )


@router.get("/{forum_slug}/{category_slug}", response_model=list[PostListItem])
async def list_posts(
    forum_slug: str,
    category_slug: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
    post_status: str = Query("active", alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[PostListItem]:
    """List posts in a category."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    category = await repo.get_category_by_slugs(forum_slug, category_slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    posts_data = await repo.get_category_posts(
        category_id=category.id,
        status=post_status,
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )

    return [
        PostListItem(
            id=item["post"].id,
            title=item["post"].title,
            status=item["post"].status,
            vote_count=item["post"].vote_count,
            author_email=item["post"].author.email if item["post"].author else "Unknown",
            author_tenant_name=item["post"].author_tenant.name if item["post"].author_tenant else None,
            is_pinned=item["post"].is_pinned,
            created_at=_isoformat_utc(item["post"].created_at),
            user_has_voted=item["user_has_voted"]
        )
        for item in posts_data
    ]


@router.get("/{forum_slug}/{category_slug}/{post_id}", response_model=PostDetail)
async def get_post(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> PostDetail:
    """Get a single post with full details."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    post_data = await repo.get_post_by_id(post_id, current_user.id)
    if not post_data:
        raise HTTPException(status_code=404, detail="Post not found")

    post = post_data["post"]

    # Verify post belongs to the correct category
    if post.category.slug != category_slug or post.category.forum.slug != forum_slug:
        raise HTTPException(status_code=404, detail="Post not found in this category")

    return PostDetail(
        id=post.id,
        title=post.title,
        content=post.content,
        status=post.status,
        vote_count=post.vote_count,
        author_email=post.author.email if post.author else "Unknown",
        author_tenant_name=post.author_tenant.name if post.author_tenant else None,
        is_pinned=post.is_pinned,
        created_at=_isoformat_utc(post.created_at),
        updated_at=_isoformat_utc(post.updated_at),
        user_has_voted=post_data["user_has_voted"],
        resolution_notes=post.resolution_notes,
        category_name=post.category.name,
        category_slug=post.category.slug,
        forum_slug=post.category.forum.slug
    )


@router.post("/{forum_slug}/{category_slug}", response_model=PostDetail, status_code=status.HTTP_201_CREATED)
async def create_post(
    forum_slug: str,
    category_slug: str,
    post_data: PostCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> PostDetail:
    """Create a new post in a category."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    category = await repo.get_category_by_slugs(forum_slug, category_slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if admin-only posting
    if category.admin_only_posting and not is_global_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can post in this category"
        )

    # Validate input
    if not post_data.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if not post_data.content.strip():
        raise HTTPException(status_code=400, detail="Content is required")

    post = await repo.create_post(
        category_id=category.id,
        author_user_id=current_user.id,
        author_tenant_id=current_user.tenant_id,
        title=post_data.title.strip(),
        content=post_data.content.strip()
    )

    return PostDetail(
        id=post.id,
        title=post.title,
        content=post.content,
        status=post.status,
        vote_count=post.vote_count,
        author_email=current_user.email,
        author_tenant_name=None,  # Would need to load tenant
        is_pinned=post.is_pinned,
        created_at=_isoformat_utc(post.created_at),
        updated_at=_isoformat_utc(post.updated_at),
        user_has_voted=False,
        resolution_notes=post.resolution_notes,
        category_name=category.name,
        category_slug=category.slug,
        forum_slug=forum_slug
    )


@router.post("/{forum_slug}/{category_slug}/{post_id}/vote", response_model=VoteResponse)
async def toggle_vote(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> VoteResponse:
    """Toggle vote on a post (add if not voted, remove if already voted)."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    category = await repo.get_category_by_slugs(forum_slug, category_slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if voting is allowed
    if not category.allows_voting:
        raise HTTPException(
            status_code=403,
            detail="Voting is not enabled for this category"
        )

    # Verify post exists and is in this category
    post_data = await repo.get_post_by_id(post_id)
    if not post_data or post_data["post"].category_id != category.id:
        raise HTTPException(status_code=404, detail="Post not found in this category")

    # Only allow voting on active posts
    if post_data["post"].status != PostStatus.ACTIVE.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot vote on archived posts"
        )

    user_has_voted, new_count = await repo.toggle_vote(post_id, current_user.id)

    return VoteResponse(
        user_has_voted=user_has_voted,
        vote_count=new_count
    )


@router.post("/{forum_slug}/{category_slug}/{post_id}/archive", response_model=PostDetail)
async def archive_post(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    archive_data: ArchivePost,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> PostDetail:
    """Archive a post (global admin only)."""
    # Only global admins can archive
    if not is_global_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only global administrators can archive posts"
        )

    repo = ForumRepository(db)

    # Validate status
    valid_statuses = {PostStatus.IMPLEMENTED.value, PostStatus.RESOLVED.value, PostStatus.ARCHIVED.value}
    if archive_data.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    # Verify post exists
    post_data = await repo.get_post_by_id(post_id, current_user.id)
    if not post_data:
        raise HTTPException(status_code=404, detail="Post not found")

    post = post_data["post"]

    # Verify post belongs to correct forum/category
    if post.category.slug != category_slug or post.category.forum.slug != forum_slug:
        raise HTTPException(status_code=404, detail="Post not found in this category")

    # Archive the post
    updated_post = await repo.archive_post(
        post_id=post_id,
        archived_by_user_id=current_user.id,
        status=archive_data.status,
        resolution_notes=archive_data.resolution_notes
    )

    return PostDetail(
        id=updated_post.id,
        title=updated_post.title,
        content=updated_post.content,
        status=updated_post.status,
        vote_count=updated_post.vote_count,
        author_email=post.author.email if post.author else "Unknown",
        author_tenant_name=post.author_tenant.name if post.author_tenant else None,
        is_pinned=updated_post.is_pinned,
        created_at=_isoformat_utc(updated_post.created_at),
        updated_at=_isoformat_utc(updated_post.updated_at),
        user_has_voted=post_data["user_has_voted"],
        resolution_notes=updated_post.resolution_notes,
        category_name=post.category.name,
        category_slug=post.category.slug,
        forum_slug=post.category.forum.slug
    )


# --- Comment Endpoints ---

@router.get("/{forum_slug}/{category_slug}/{post_id}/comments", response_model=list[CommentResponse])
async def get_comments(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> list[CommentResponse]:
    """Get all comments for a post."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    # Verify post exists
    post_data = await repo.get_post_by_id(post_id)
    if not post_data:
        raise HTTPException(status_code=404, detail="Post not found")

    comments = await repo.get_post_comments(post_id, current_user.id)

    return [CommentResponse(**c) for c in comments]


@router.post("/{forum_slug}/{category_slug}/{post_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    comment_data: CommentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> CommentResponse:
    """Create a comment on a post."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    # Verify post exists
    post_data = await repo.get_post_by_id(post_id)
    if not post_data:
        raise HTTPException(status_code=404, detail="Post not found")

    # Validate content
    if not comment_data.content.strip():
        raise HTTPException(status_code=400, detail="Comment content is required")

    comment = await repo.create_comment(
        post_id=post_id,
        author_user_id=current_user.id,
        author_tenant_id=current_user.tenant_id,
        content=comment_data.content.strip(),
        parent_comment_id=comment_data.parent_comment_id
    )

    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        parent_comment_id=comment.parent_comment_id,
        author_email=current_user.email,
        author_tenant_name=None,  # Would need to load tenant
        content=comment.content,
        score=comment.score,
        is_deleted=comment.is_deleted,
        created_at=_isoformat_utc(comment.created_at),
        user_vote=0
    )


@router.post("/{forum_slug}/{category_slug}/{post_id}/comments/{comment_id}/vote", response_model=CommentVoteResponse)
async def vote_on_comment(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    comment_id: int,
    vote_data: CommentVote,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> CommentVoteResponse:
    """Vote on a comment (upvote +1, downvote -1, or remove 0)."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    # Validate vote value
    if vote_data.vote_value not in [-1, 0, 1]:
        raise HTTPException(status_code=400, detail="Vote value must be -1, 0, or 1")

    try:
        user_vote, score = await repo.vote_on_comment(
            comment_id=comment_id,
            user_id=current_user.id,
            vote_value=vote_data.vote_value
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return CommentVoteResponse(user_vote=user_vote, score=score)


@router.delete("/{forum_slug}/{category_slug}/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    forum_slug: str,
    category_slug: str,
    post_id: int,
    comment_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
):
    """Soft delete a comment (only the author can delete)."""
    repo = ForumRepository(db)
    await _verify_forum_access(forum_slug, current_user, repo)

    deleted = await repo.delete_comment(comment_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found or not authorized")
