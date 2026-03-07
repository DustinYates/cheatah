"""Admin voice configuration endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_admin
from app.persistence.database import get_db
from app.persistence.models.tenant import TenantBusinessProfile, User
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class VoiceNumberResponse(BaseModel):
    """Voice number configuration response."""

    tenant_id: int
    phone_number: str | None
    voice_url: str | None
    status_callback: str | None


@router.get("/number", response_model=VoiceNumberResponse)
async def get_voice_number(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VoiceNumberResponse:
    """Get voice number configuration for tenant."""
    current_user, tenant_id = admin_data

    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile or not profile.voice_phone:
        return VoiceNumberResponse(
            tenant_id=tenant_id,
            phone_number=None,
            voice_url=None,
            status_callback=None,
        )

    webhook_base = settings.api_base_url or "https://your-domain.com"
    voice_url = f"{webhook_base}/api/v1/telnyx/call-progress"
    status_callback_url = f"{webhook_base}/api/v1/telnyx/ai-call-complete"

    return VoiceNumberResponse(
        tenant_id=tenant_id,
        phone_number=profile.voice_phone,
        voice_url=voice_url,
        status_callback=status_callback_url,
    )

