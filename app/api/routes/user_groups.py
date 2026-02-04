"""User group management API endpoints (admin only).

Handles group creation, membership management, and forum setup.
"""

from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.persistence.database import get_db_no_rls
from app.persistence.models.forum import GroupRole
from app.persistence.models.tenant import User
from app.persistence.repositories.user_group_repository import UserGroupRepository

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


# --- Request/Response Models ---

class GroupCreate(BaseModel):
    """Create group request."""

    name: str
    slug: str
    description: str | None = None
    mapping_number: int | None = None


class GroupUpdate(BaseModel):
    """Update group request."""

    name: str | None = None
    description: str | None = None
    mapping_number: int | None = None


class GroupResponse(BaseModel):
    """Group response."""

    id: int
    name: str
    slug: str
    description: str | None
    mapping_number: int | None
    member_count: int = 0
    has_forum: bool = False
    created_at: str

    class Config:
        from_attributes = True


class MemberResponse(BaseModel):
    """Group member response."""

    id: int
    user_id: int
    email: str | None
    tenant_id: int | None
    role: str
    joined_at: str | None


class AddMemberRequest(BaseModel):
    """Add member request."""

    user_id: int
    role: str = GroupRole.MEMBER.value


class UserSearchResult(BaseModel):
    """User search result."""

    id: int
    email: str
    tenant_id: int | None


class ForumCreate(BaseModel):
    """Create forum for group request."""

    name: str
    slug: str
    description: str | None = None


class CategoryCreate(BaseModel):
    """Create forum category request."""

    name: str
    slug: str
    description: str | None = None
    sort_order: int = 0
    allows_voting: bool = False
    admin_only_posting: bool = False
    icon: str | None = None


class ForumResponse(BaseModel):
    """Forum response."""

    id: int
    name: str
    slug: str
    description: str | None


class CategoryResponse(BaseModel):
    """Category response."""

    id: int
    name: str
    slug: str
    description: str | None
    sort_order: int
    allows_voting: bool
    admin_only_posting: bool


# --- Endpoints ---

@router.get("", response_model=list[GroupResponse])
async def list_groups(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[GroupResponse]:
    """List all user groups (admin only)."""
    repo = UserGroupRepository(db)
    groups = await repo.list_groups(skip=skip, limit=limit)

    result = []
    for group in groups:
        member_count = await repo.get_member_count(group.id)
        result.append(GroupResponse(
            id=group.id,
            name=group.name,
            slug=group.slug,
            description=group.description,
            mapping_number=group.mapping_number,
            member_count=member_count,
            has_forum=group.forum is not None if hasattr(group, 'forum') else False,
            created_at=_isoformat_utc(group.created_at)
        ))

    return result


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> GroupResponse:
    """Create a new user group (admin only)."""
    repo = UserGroupRepository(db)

    # Validate slug format
    if not group_data.slug.replace("-", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Slug must contain only letters, numbers, and hyphens"
        )

    # Check for existing slug
    existing = await repo.get_group_by_slug(group_data.slug)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A group with this slug already exists"
        )

    # Check for existing mapping number
    if group_data.mapping_number is not None:
        existing_mapping = await repo.get_group_by_mapping_number(group_data.mapping_number)
        if existing_mapping:
            raise HTTPException(
                status_code=400,
                detail="A group with this mapping number already exists"
            )

    group = await repo.create_group(
        name=group_data.name,
        slug=group_data.slug,
        description=group_data.description,
        mapping_number=group_data.mapping_number
    )

    return GroupResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        mapping_number=group.mapping_number,
        member_count=0,
        has_forum=False,
        created_at=_isoformat_utc(group.created_at)
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> GroupResponse:
    """Get a specific user group (admin only)."""
    repo = UserGroupRepository(db)
    group = await repo.get_group_by_id(group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    member_count = await repo.get_member_count(group_id)

    return GroupResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        mapping_number=group.mapping_number,
        member_count=member_count,
        has_forum=group.forum is not None,
        created_at=_isoformat_utc(group.created_at)
    )


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    group_data: GroupUpdate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> GroupResponse:
    """Update a user group (admin only)."""
    repo = UserGroupRepository(db)

    # Check for existing mapping number if being updated
    if group_data.mapping_number is not None:
        existing = await repo.get_group_by_mapping_number(group_data.mapping_number)
        if existing and existing.id != group_id:
            raise HTTPException(
                status_code=400,
                detail="A group with this mapping number already exists"
            )

    update_data = group_data.model_dump(exclude_unset=True)
    group = await repo.update_group(group_id, **update_data)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    member_count = await repo.get_member_count(group_id)

    return GroupResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        mapping_number=group.mapping_number,
        member_count=member_count,
        has_forum=group.forum is not None if hasattr(group, 'forum') else False,
        created_at=_isoformat_utc(group.created_at)
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> None:
    """Delete a user group (admin only)."""
    repo = UserGroupRepository(db)
    deleted = await repo.delete_group(group_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")


# --- Member Management ---

@router.get("/{group_id}/members", response_model=list[MemberResponse])
async def list_members(
    group_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[MemberResponse]:
    """List members of a group (admin only)."""
    repo = UserGroupRepository(db)

    # Verify group exists
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    members = await repo.get_group_members(group_id, skip=skip, limit=limit)

    return [
        MemberResponse(
            id=m["id"],
            user_id=m["user_id"],
            email=m["email"],
            tenant_id=m["tenant_id"],
            role=m["role"],
            joined_at=m["joined_at"]
        )
        for m in members
    ]


@router.post("/{group_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int,
    member_data: AddMemberRequest,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> MemberResponse:
    """Add a user to a group (admin only)."""
    repo = UserGroupRepository(db)

    # Verify group exists
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Validate role
    valid_roles = {r.value for r in GroupRole}
    if member_data.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )

    membership = await repo.add_user_to_group(
        user_id=member_data.user_id,
        group_id=group_id,
        role=member_data.role
    )

    # Get user email for response
    members = await repo.get_group_members(group_id)
    member_info = next((m for m in members if m["user_id"] == member_data.user_id), None)

    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        email=member_info["email"] if member_info else None,
        tenant_id=member_info["tenant_id"] if member_info else None,
        role=membership.role,
        joined_at=_isoformat_utc(membership.joined_at)
    )


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> None:
    """Remove a user from a group (admin only)."""
    repo = UserGroupRepository(db)
    removed = await repo.remove_user_from_group(user_id, group_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Membership not found")


@router.get("/{group_id}/available-users", response_model=list[UserSearchResult])
async def search_available_users(
    group_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
    search: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=50),
) -> list[UserSearchResult]:
    """Search for users not in a group (admin only)."""
    repo = UserGroupRepository(db)

    # Verify group exists
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    users = await repo.get_users_not_in_group(
        group_id=group_id,
        search=search if search else None,
        limit=limit
    )

    return [
        UserSearchResult(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id
        )
        for user in users
    ]


# --- Forum Management ---

@router.post("/{group_id}/forum", response_model=ForumResponse, status_code=status.HTTP_201_CREATED)
async def create_forum_for_group(
    group_id: int,
    forum_data: ForumCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> ForumResponse:
    """Create a forum for a group (admin only)."""
    repo = UserGroupRepository(db)

    # Verify group exists
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check if forum already exists
    if group.forum:
        raise HTTPException(status_code=400, detail="Forum already exists for this group")

    # Validate slug format
    if not forum_data.slug.replace("-", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Slug must contain only letters, numbers, and hyphens"
        )

    forum = await repo.create_forum_for_group(
        group_id=group_id,
        name=forum_data.name,
        slug=forum_data.slug,
        description=forum_data.description
    )

    return ForumResponse(
        id=forum.id,
        name=forum.name,
        slug=forum.slug,
        description=forum.description
    )


@router.post("/{group_id}/forum/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    group_id: int,
    category_data: CategoryCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db_no_rls)],
) -> CategoryResponse:
    """Create a category in a group's forum (admin only)."""
    repo = UserGroupRepository(db)

    # Verify group exists and has forum
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if not group.forum:
        raise HTTPException(status_code=400, detail="Group does not have a forum yet")

    # Validate slug format
    if not category_data.slug.replace("-", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Slug must contain only letters, numbers, and hyphens"
        )

    category = await repo.create_forum_category(
        forum_id=group.forum.id,
        name=category_data.name,
        slug=category_data.slug,
        description=category_data.description,
        sort_order=category_data.sort_order,
        allows_voting=category_data.allows_voting,
        admin_only_posting=category_data.admin_only_posting,
        icon=category_data.icon
    )

    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        sort_order=category.sort_order,
        allows_voting=category.allows_voting,
        admin_only_posting=category.admin_only_posting
    )
