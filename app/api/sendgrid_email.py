"""SendGrid email sending endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_context
from app.infrastructure.sendgrid_client import SendGridClient
from app.persistence.database import get_db
from app.persistence.repositories.email_repository import TenantEmailConfigRepository
from app.settings import settings

router = APIRouter(prefix="/email", tags=["email"])


class SendEmailRequest(BaseModel):
    """Request model for sending email."""

    to_email: str
    subject: str
    html_content: str
    text_content: str | None = None
    from_email: str | None = None
    reply_to: str | None = None


class SendEmailResponse(BaseModel):
    """Response model for email send."""

    status: str
    message_id: str | None
    status_code: int


@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    request: SendEmailRequest,
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SendEmailResponse:
    """
    Send an email via SendGrid using tenant's credentials.

    Falls back to global credentials if tenant has no SendGrid configured.

    Example:
        POST /api/v1/email/send
        {
            "to_email": "user@example.com",
            "subject": "Welcome!",
            "html_content": "<h1>Hello!</h1>",
            "text_content": "Hello!"
        }
    """
    # Get tenant's email config
    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    # Determine which credentials to use (tenant-specific or global fallback)
    api_key = config.sendgrid_api_key if config else None
    from_email = config.sendgrid_from_email if config else None

    # Check if we have credentials (either tenant or global)
    effective_api_key = api_key or settings.sendgrid_api_key
    if not effective_api_key:
        raise HTTPException(
            status_code=400,
            detail="SendGrid not configured. Please configure SendGrid API key in settings.",
        )

    try:
        sendgrid = SendGridClient(
            api_key=api_key,  # Falls back to global if None
            from_email=from_email,  # Falls back to global if None
        )
        result = await sendgrid.send_email(
            to_email=request.to_email,
            subject=request.subject,
            html_content=request.html_content,
            text_content=request.text_content,
            from_email=request.from_email,  # Request can override
            reply_to=request.reply_to,
        )
        return SendEmailResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
