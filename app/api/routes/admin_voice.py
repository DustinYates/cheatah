"""Admin voice configuration endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_admin
from app.infrastructure.twilio_client import TwilioVoiceClient
from app.persistence.database import get_db
from app.persistence.models.tenant import TenantBusinessProfile, User
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ProvisionNumberRequest(BaseModel):
    """Request to provision a Twilio phone number."""
    
    area_code: str | None = None  # e.g., "415"
    phone_number: str | None = None  # Specific number in E.164 format


class ProvisionNumberResponse(BaseModel):
    """Response after provisioning a number."""
    
    phone_number: str
    phone_number_sid: str
    tenant_id: int
    message: str


class VoiceNumberResponse(BaseModel):
    """Voice number configuration response."""
    
    tenant_id: int
    phone_number: str | None
    phone_number_sid: str | None
    voice_url: str | None
    status_callback: str | None


@router.post("/provision-number", response_model=ProvisionNumberResponse)
async def provision_voice_number(
    request_data: ProvisionNumberRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProvisionNumberResponse:
    """Provision a Twilio phone number for voice calls.
    
    Args:
        request_data: Provision number request (area_code or phone_number)
        admin_data: Admin user and tenant ID
        db: Database session
        
    Returns:
        Provisioned number details
    """
    current_user, tenant_id = admin_data
    
    # Check if tenant already has a voice number
    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    
    if not profile:
        # Create profile if it doesn't exist
        profile = TenantBusinessProfile(tenant_id=tenant_id)
        db.add(profile)
        await db.flush()
    
    if profile.twilio_voice_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant already has a voice number: {profile.twilio_voice_phone}",
        )
    
    # Provision number via Twilio
    try:
        voice_client = TwilioVoiceClient()
        provision_result = voice_client.provision_phone_number(
            area_code=request_data.area_code,
            phone_number=request_data.phone_number,
        )
        
        phone_number = provision_result["phone_number"]
        phone_number_sid = provision_result["sid"]
        
        # Configure webhook URL
        webhook_base = settings.twilio_webhook_url_base or "https://your-domain.com"
        voice_url = f"{webhook_base}/api/v1/voice/inbound"
        status_callback_url = f"{webhook_base}/api/v1/voice/status"
        
        voice_client.configure_phone_webhook(
            phone_number_sid=phone_number_sid,
            voice_url=voice_url,
            status_callback_url=status_callback_url,
        )
        
        # Store phone number in tenant business profile
        profile.twilio_voice_phone = phone_number
        await db.commit()
        await db.refresh(profile)
        
        return ProvisionNumberResponse(
            phone_number=phone_number,
            phone_number_sid=phone_number_sid,
            tenant_id=tenant_id,
            message=f"Voice number {phone_number} provisioned and configured successfully",
        )
        
    except Exception as e:
        logger.error(f"Error provisioning voice number: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision voice number: {str(e)}",
        ) from e


@router.get("/number", response_model=VoiceNumberResponse)
async def get_voice_number(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VoiceNumberResponse:
    """Get voice number configuration for tenant.
    
    Args:
        admin_data: Admin user and tenant ID
        db: Database session
        
    Returns:
        Voice number configuration
    """
    current_user, tenant_id = admin_data
    
    stmt = select(TenantBusinessProfile).where(
        TenantBusinessProfile.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    
    if not profile or not profile.twilio_voice_phone:
        return VoiceNumberResponse(
            tenant_id=tenant_id,
            phone_number=None,
            phone_number_sid=None,
            voice_url=None,
            status_callback=None,
        )
    
    # Fetch phone number details from Twilio
    try:
        voice_client = TwilioVoiceClient()
        # We need to find the phone number SID - in a production system,
        # we might want to store this in the database. For now, we'll
        # return what we have.
        webhook_base = settings.twilio_webhook_url_base or "https://your-domain.com"
        voice_url = f"{webhook_base}/api/v1/voice/inbound"
        status_callback_url = f"{webhook_base}/api/v1/voice/status"
        
        return VoiceNumberResponse(
            tenant_id=tenant_id,
            phone_number=profile.twilio_voice_phone,
            phone_number_sid=None,  # Would need to store this separately
            voice_url=voice_url,
            status_callback=status_callback_url,
        )
    except Exception as e:
        logger.error(f"Error fetching voice number details: {e}", exc_info=True)
        # Return basic info even if Twilio fetch fails
        return VoiceNumberResponse(
            tenant_id=tenant_id,
            phone_number=profile.twilio_voice_phone,
            phone_number_sid=None,
            voice_url=None,
            status_callback=None,
        )

