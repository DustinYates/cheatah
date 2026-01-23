"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.auth import create_access_token
from app.core.password import verify_password, hash_password
from app.api.deps import get_current_user, is_global_admin
from app.infrastructure.rate_limiter import rate_limit
from app.domain.services.audit_service import AuditService
from app.persistence.database import get_db
from app.persistence.models.audit_log import AuditAction
from app.persistence.models.tenant import User
from app.persistence.repositories.user_repository import UserRepository
from app.persistence.repositories.tenant_repository import TenantRepository
from app.domain.services.user_contact_link_service import UserContactLinkService
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


class SignupRequest(BaseModel):
    """Signup request."""

    email: str
    password: str
    tenant_subdomain: str


class SignupResponse(BaseModel):
    """Signup response."""

    user_id: int
    email: str
    tenant_id: int
    contact_linked: bool
    contact_id: int | None = None
    message: str


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: None = Depends(rate_limit("auth")),
) -> LoginResponse:
    """Login endpoint for admin dashboard.

    Args:
        login_data: Login credentials
        request: FastAPI request for audit logging
        db: Database session

    Returns:
        JWT access token
    """
    user_repo = UserRepository(db)
    audit = AuditService(db)

    # Find user by email
    user = await user_repo.get_by_email(login_data.email)

    # Always verify password to prevent timing attacks
    # Use a dummy hash if user doesn't exist so response time is constant
    dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.V4ferYxZ1uYmWe"
    stored_hash = user.hashed_password if user else dummy_hash
    password_valid = verify_password(login_data.password, stored_hash)

    if not user or not password_valid:
        # Log failed login attempt (with email for investigation)
        await audit.log(
            action=AuditAction.LOGIN_FAILED,
            details={"email": login_data.email},
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create access token (sub must be string for JWT compatibility)
    access_token = create_access_token(data={"sub": str(user.id)})

    # Log successful login
    await audit.log_login(user=user, request=request, success=True)

    return LoginResponse(
        access_token=access_token,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
        is_global_admin=is_global_admin(user),
    )


@router.post("/signup", response_model=SignupResponse)
async def signup(
    signup_data: SignupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: None = Depends(rate_limit("auth")),
) -> SignupResponse:
    """Public signup endpoint for new users.

    Creates a new user account and auto-links to existing contact
    if email matches.

    Args:
        signup_data: Signup credentials
        request: FastAPI request for audit logging
        db: Database session

    Returns:
        User info and contact linking status
    """
    audit = AuditService(db)

    # Validate tenant exists
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_subdomain(signup_data.tenant_subdomain)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Check if user already exists
    user_repo = UserRepository(db)
    existing = await user_repo.get_by_email(signup_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Hash password
    hashed = hash_password(signup_data.password)

    # Create user
    user = await user_repo.create(
        tenant_id=tenant.id,
        email=signup_data.email.lower().strip(),
        hashed_password=hashed,
        role="user"
    )

    # Auto-link to contact
    link_service = UserContactLinkService(db)
    linked_contact = await link_service.link_user_to_contact_by_email(user)

    # Log user creation
    await audit.log(
        action=AuditAction.USER_CREATED,
        user=user,
        tenant=tenant,
        resource_type="user",
        resource_id=user.id,
        details={"contact_linked": linked_contact is not None},
        request=request,
    )

    return SignupResponse(
        user_id=user.id,
        email=user.email,
        tenant_id=user.tenant_id,
        contact_linked=linked_contact is not None,
        contact_id=linked_contact.id if linked_contact else None,
        message=(
            f"Account created and linked to existing contact"
            if linked_contact
            else "Account created"
        )
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
    return UserInfoResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        is_global_admin=is_global_admin(current_user),
    )
