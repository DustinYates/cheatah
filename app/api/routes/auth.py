"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.auth import create_access_token
from app.persistence.database import get_db
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
    
    return LoginResponse(
        access_token=access_token,
        tenant_id=user.tenant_id,
    )

