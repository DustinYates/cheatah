"""Authentication routes."""

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.auth import create_access_token, decode_access_token
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

logger = logging.getLogger(__name__)

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
    must_change_password: bool = False
    password_change_token: str | None = None


class UserInfoResponse(BaseModel):
    """Current user info response."""

    id: int
    email: str
    role: str
    tenant_id: int | None = None
    is_global_admin: bool = False
    must_change_password: bool = False


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Reset password request."""

    token: str
    new_password: str


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

    # If user must change password, generate a reset token so frontend
    # can redirect to the existing reset-password page
    password_change_token = None
    if user.must_change_password:
        password_change_token = create_access_token(
            data={"sub": str(user.id), "type": "password_reset"},
            expires_delta=timedelta(minutes=30),
        )

    # Log successful login
    await audit.log_login(user=user, request=request, success=True)

    return LoginResponse(
        access_token=access_token,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
        is_global_admin=is_global_admin(user),
        must_change_password=user.must_change_password,
        password_change_token=password_change_token,
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
        must_change_password=current_user.must_change_password,
    )


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: None = Depends(rate_limit("auth")),
):
    """Request a password reset email.

    Always returns success to avoid leaking whether email exists.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(data.email.strip())

    if user:
        # Create short-lived token (15 minutes)
        reset_token = create_access_token(
            data={"sub": str(user.id), "type": "password_reset"},
            expires_delta=timedelta(minutes=15),
        )

        reset_url = f"https://app.getconvopro.com/reset-password?token={reset_token}"

        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #1e293b; font-size: 24px; margin: 0;">Reset Your Password</h1>
            </div>
            <p style="color: #475569; font-size: 15px; line-height: 1.6;">
                We received a request to reset the password for your ConvoPro account.
                Click the button below to set a new password:
            </p>
            <div style="text-align: center; margin: 32px 0;">
                <a href="{reset_url}"
                   style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #6366f1, #8b5cf6);
                          color: #fff; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 15px;">
                    Reset Password
                </a>
            </div>
            <p style="color: #94a3b8; font-size: 13px; line-height: 1.5;">
                This link expires in 15 minutes. If you didn't request a password reset, you can safely ignore this email.
            </p>
        </div>
        """

        try:
            from app.infrastructure.gmail_client import GmailClient
            from app.persistence.repositories.email_repository import TenantEmailConfigRepository

            email_repo = TenantEmailConfigRepository(db)
            # Use tenant 1 (ConvoPro) Gmail OAuth to send system emails
            email_config = await email_repo.get_by_tenant_id(1)

            if email_config and email_config.gmail_refresh_token:
                gmail = GmailClient(
                    refresh_token=email_config.gmail_refresh_token,
                    access_token=email_config.gmail_access_token,
                )
                plain_text = (
                    f"Reset your ConvoPro password\n\n"
                    f"We received a request to reset your password. "
                    f"Click the link below to set a new one:\n\n"
                    f"{reset_url}\n\n"
                    f"This link expires in 15 minutes. "
                    f"If you didn't request this, you can ignore this email."
                )
                gmail.send_message(
                    to=user.email,
                    subject="Reset your ConvoPro password",
                    body=plain_text,
                )
            else:
                logger.error("No Gmail OAuth config found for tenant 1 - cannot send reset email")
        except Exception:
            logger.exception(f"Failed to send password reset email to {user.email}")

    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: None = Depends(rate_limit("auth")),
):
    """Reset password using a token from the reset email."""
    payload = decode_access_token(data.token)

    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token.",
        )

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(None, int(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token.",
        )

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    await db.commit()

    return {"message": "Password has been reset successfully. You can now sign in."}
