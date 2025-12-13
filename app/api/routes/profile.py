"""Tenant business profile routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.business_profile_repository import BusinessProfileRepository

router = APIRouter()


class BusinessProfileResponse(BaseModel):
    """Business profile response."""
    
    id: int
    tenant_id: int
    business_name: str | None
    website_url: str | None
    phone_number: str | None
    twilio_phone: str | None
    email: str | None
    profile_complete: bool

    class Config:
        from_attributes = True


class BusinessProfileUpdate(BaseModel):
    """Business profile update request."""
    
    business_name: str | None = None
    website_url: str | None = None
    phone_number: str | None = None
    twilio_phone: str | None = None
    email: str | None = None


@router.get("/profile", response_model=BusinessProfileResponse)
async def get_business_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BusinessProfileResponse:
    """Get business profile for current tenant."""
    profile_repo = BusinessProfileRepository(db)
    profile = await profile_repo.get_by_tenant_id(tenant_id)
    
    if not profile:
        profile = await profile_repo.create_for_tenant(tenant_id)
    
    return BusinessProfileResponse(
        id=profile.id,
        tenant_id=profile.tenant_id,
        business_name=profile.business_name,
        website_url=profile.website_url,
        phone_number=profile.phone_number,
        twilio_phone=profile.twilio_phone,
        email=profile.email,
        profile_complete=profile.profile_complete,
    )


@router.put("/profile", response_model=BusinessProfileResponse)
async def update_business_profile(
    profile_data: BusinessProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BusinessProfileResponse:
    """Update business profile for current tenant."""
    profile_repo = BusinessProfileRepository(db)
    
    existing = await profile_repo.get_by_tenant_id(tenant_id)
    if not existing:
        await profile_repo.create_for_tenant(tenant_id)
    
    profile = await profile_repo.update_profile(
        tenant_id=tenant_id,
        business_name=profile_data.business_name,
        website_url=profile_data.website_url,
        phone_number=profile_data.phone_number,
        twilio_phone=profile_data.twilio_phone,
        email=profile_data.email,
    )
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    
    return BusinessProfileResponse(
        id=profile.id,
        tenant_id=profile.tenant_id,
        business_name=profile.business_name,
        website_url=profile.website_url,
        phone_number=profile.phone_number,
        twilio_phone=profile.twilio_phone,
        email=profile.email,
        profile_complete=profile.profile_complete,
    )
