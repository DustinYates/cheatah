"""Business profile repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.persistence.models.tenant import TenantBusinessProfile
from app.persistence.repositories.base import BaseRepository


class BusinessProfileRepository(BaseRepository[TenantBusinessProfile]):
    """Repository for TenantBusinessProfile entities."""

    def __init__(self, session: AsyncSession):
        """Initialize business profile repository."""
        super().__init__(TenantBusinessProfile, session)

    async def get_by_tenant_id(self, tenant_id: int) -> TenantBusinessProfile | None:
        """Get business profile by tenant ID."""
        stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_for_tenant(self, tenant_id: int) -> TenantBusinessProfile:
        """Create a new empty business profile for a tenant."""
        profile = TenantBusinessProfile(tenant_id=tenant_id, profile_complete=False)
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_profile(
        self,
        tenant_id: int,
        business_name: str | None = None,
        website_url: str | None = None,
        phone_number: str | None = None,
        twilio_phone: str | None = None,
        email: str | None = None,
    ) -> TenantBusinessProfile | None:
        """Update business profile for a tenant."""
        profile = await self.get_by_tenant_id(tenant_id)
        if not profile:
            return None
        
        if business_name is not None:
            profile.business_name = business_name
        if website_url is not None:
            profile.website_url = website_url
        if phone_number is not None:
            profile.phone_number = phone_number
        if twilio_phone is not None:
            profile.twilio_phone = twilio_phone
        if email is not None:
            profile.email = email
        
        required_fields = [profile.business_name, profile.website_url, profile.phone_number, profile.email]
        profile.profile_complete = all(f and len(str(f).strip()) > 0 for f in required_fields)
        
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
