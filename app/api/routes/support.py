"""Tenant support request routes."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant
from app.infrastructure.gmail_client import GmailClient
from app.persistence.database import get_db, get_db_no_rls
from app.persistence.models.tenant import User
from app.persistence.repositories.email_repository import TenantEmailConfigRepository
from app.persistence.repositories.tenant_repository import TenantRepository

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORT_EMAIL = "dustin.yates143@gmail.com"
SUPPORT_GMAIL_TENANT_ID = 1  # ConvoPro tenant — owns the platform Gmail


class SupportRequest(BaseModel):
    """Support request submission."""

    subject: str
    category: str
    message: str


class SupportResponse(BaseModel):
    """Support request response."""

    success: bool
    message: str


@router.post("/request", response_model=SupportResponse)
async def submit_support_request(
    data: SupportRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SupportResponse:
    """Submit a support request. Sends email to admin via Gmail API."""
    # Get tenant name for context
    tenant_name = "Unknown"
    if tenant_id:
        tenant_repo = TenantRepository(db)
        tenant = await tenant_repo.get_by_id(None, tenant_id)
        if tenant:
            tenant_name = tenant.name

    subject = f"[ConvoPro Support] [{data.category}] {data.subject}"
    body = (
        f"Support Request from {tenant_name}\n\n"
        f"Category: {data.category}\n"
        f"Subject: {data.subject}\n"
        f"From: {current_user.email} (Tenant: {tenant_name}, ID: {tenant_id})\n\n"
        f"{data.message}"
    )

    try:
        # Fetch platform Gmail credentials (tenant 1) using no-RLS session
        # so any tenant's user can send support requests
        async for no_rls_session in get_db_no_rls():
            email_repo = TenantEmailConfigRepository(no_rls_session)
            email_config = await email_repo.get_by_tenant_id(SUPPORT_GMAIL_TENANT_ID)
            break

        if not email_config or not email_config.gmail_refresh_token:
            raise ValueError("Platform Gmail not configured for support emails")

        gmail_client = GmailClient(
            refresh_token=email_config.gmail_refresh_token,
            access_token=email_config.gmail_access_token,
            token_expires_at=email_config.gmail_token_expires_at,
        )

        # Run sync Gmail API call in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: gmail_client.send_message(
                to=SUPPORT_EMAIL,
                subject=subject,
                body=body,
            ),
        )
    except Exception as e:
        logger.error(f"Failed to send support email: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send support request. Please try again.",
        )

    return SupportResponse(success=True, message="Support request sent successfully.")
