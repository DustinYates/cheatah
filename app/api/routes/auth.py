"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.auth import create_access_token
from app.api.deps import get_current_user
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.user_repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
security = HTTPBasic()


class LoginRequest(BaseModel):
    """Login request."""
    
    email: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    
    access_token: str
    token_type: str = "bearer"
    tenant_id: int | None = None
    role: str
    email: str
    is_global_admin: bool = False


class UserInfoResponse(BaseModel):
    """Current user info response."""
    
    id: int
    email: str
    role: str
    tenant_id: int | None = None
    is_global_admin: bool = False


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Login endpoint for admin dashboard.
    
    Args:
        login_data: Login credentials
        db: Database session
        
    Returns:
        JWT access token
    """
    import bcrypt
    
    user_repo = UserRepository(db)
    
    # Find user by email
    user = await user_repo.get_by_email(login_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    # Verify password using bcrypt directly
    try:
        password_valid = bcrypt.checkpw(
            login_data.password.encode('utf-8'),
            user.hashed_password.encode('utf-8')
        )
    except Exception:
        password_valid = False
    
    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    # Create access token (sub must be string for JWT compatibility)
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Check if user is global admin (no tenant_id and admin role)
    is_global_admin = user.tenant_id is None and user.role == "admin"
    
    return LoginResponse(
        access_token=access_token,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
        is_global_admin=is_global_admin,
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserInfoResponse:
    """Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User information including role and tenant
    """
    is_global_admin = current_user.tenant_id is None and current_user.role == "admin"
    
    return UserInfoResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        is_global_admin=is_global_admin,
    )
