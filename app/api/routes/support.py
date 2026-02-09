"""Tenant support request routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant
from app.infrastructure.sendgrid_client import get_sendgrid_client
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.tenant_repository import TenantRepository

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORT_EMAIL = "dustin.yates143@gmail.com"


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
    """Submit a support request. Sends email to admin."""
    # Get tenant name for context
    tenant_name = "Unknown"
    if tenant_id:
        tenant_repo = TenantRepository(db)
        tenant = await tenant_repo.get_by_id(None, tenant_id)
        if tenant:
            tenant_name = tenant.name

    html_content = f"""
    <h2>Support Request from {tenant_name}</h2>
    <p><strong>Category:</strong> {data.category}</p>
    <p><strong>Subject:</strong> {data.subject}</p>
    <p><strong>From:</strong> {current_user.email} (Tenant: {tenant_name}, ID: {tenant_id})</p>
    <hr>
    <p>{data.message.replace(chr(10), '<br>')}</p>
    """

    text_content = (
        f"Support Request from {tenant_name}\n\n"
        f"Category: {data.category}\n"
        f"Subject: {data.subject}\n"
        f"From: {current_user.email} (Tenant: {tenant_name}, ID: {tenant_id})\n\n"
        f"{data.message}"
    )

    try:
        client = get_sendgrid_client()
        await client.send_email(
            to_email=SUPPORT_EMAIL,
            subject=f"[ConvoPro Support] [{data.category}] {data.subject}",
            html_content=html_content,
            text_content=text_content,
            reply_to=current_user.email,
        )
    except Exception as e:
        logger.error(f"Failed to send support email: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send support request. Please try again.",
        )

    return SupportResponse(success=True, message="Support request sent successfully.")
