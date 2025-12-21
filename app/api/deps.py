"""FastAPI dependencies for auth and tenant resolution."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decode_access_token
from app.core.tenant_context import set_tenant_context
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.user_repository import UserRepository

security = HTTPBearer()


def is_global_admin(user: User) -> bool:
    """Check if user is a global admin.

    A global admin has no tenant_id and admin role.

    Args:
        user: User to check

    Returns:
        True if user is global admin, False otherwise
    """
    return user.tenant_id is None and user.role == "admin"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get current authenticated user from JWT token.

    Args:
        credentials: HTTP bearer credentials
        db: Database session

    Returns:
        Current user

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(None, user_id)  # No tenant scoping for user lookup
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return user


async def get_current_tenant(
    current_user: Annotated[User, Depends(get_current_user)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
) -> int | None:
    """Get current tenant from user context or header override.

    Global admins can pass X-Tenant-Id header to impersonate a tenant.

    Args:
        current_user: Current authenticated user
        x_tenant_id: Optional tenant ID header for global admin impersonation

    Returns:
        Tenant ID or None for global admin without impersonation

    Raises:
        HTTPException: If user has no tenant and is not global admin
    """
    # If global admin and header provided, use header value
    if is_global_admin(current_user) and x_tenant_id:
        try:
            tenant_id = int(x_tenant_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Tenant-Id header value",
            )
    else:
        tenant_id = current_user.tenant_id
    
    # Set tenant context
    set_tenant_context(tenant_id)
    
    return tenant_id


async def require_global_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require global admin role.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user if admin

    Raises:
        HTTPException: If user is not global admin
    """
    if not is_global_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin access required",
        )
    return current_user


async def require_tenant_context(
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> int:
    """Require a tenant context to be present.

    Args:
        tenant_id: Current tenant ID from get_current_tenant

    Returns:
        Tenant ID (guaranteed non-None)

    Raises:
        HTTPException: If no tenant context is present
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )
    return tenant_id


async def require_tenant_admin(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> tuple[User, int]:
    """Require tenant admin role.

    Args:
        current_user: Current authenticated user
        tenant_id: Current tenant ID

    Returns:
        Tuple of (user, tenant_id)

    Raises:
        HTTPException: If user is not tenant admin
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )
    
    if current_user.tenant_id != tenant_id or current_user.role not in ("admin", "tenant_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin access required",
        )
    
    return current_user, tenant_id

