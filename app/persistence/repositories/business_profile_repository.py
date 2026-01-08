"""Business profile repository."""

from datetime import datetime
from typing import Any

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

    async def update_scraped_data(
        self,
        tenant_id: int,
        scraped_data: dict[str, Any],
    ) -> TenantBusinessProfile | None:
        """Update scraped website data for a tenant's business profile.

        Args:
            tenant_id: The tenant ID
            scraped_data: Dictionary containing scraped data fields

        Returns:
            Updated profile or None if not found
        """
        profile = await self.get_by_tenant_id(tenant_id)
        if not profile:
            return None

        # Update scraped fields
        if "scraped_services" in scraped_data:
            profile.scraped_services = scraped_data["scraped_services"]
        if "scraped_hours" in scraped_data:
            profile.scraped_hours = scraped_data["scraped_hours"]
        if "scraped_locations" in scraped_data:
            profile.scraped_locations = scraped_data["scraped_locations"]
        if "scraped_pricing" in scraped_data:
            profile.scraped_pricing = scraped_data["scraped_pricing"]
        if "scraped_faqs" in scraped_data:
            profile.scraped_faqs = scraped_data["scraped_faqs"]
        if "scraped_policies" in scraped_data:
            profile.scraped_policies = scraped_data["scraped_policies"]
        if "scraped_programs" in scraped_data:
            profile.scraped_programs = scraped_data["scraped_programs"]
        if "scraped_unique_selling_points" in scraped_data:
            profile.scraped_unique_selling_points = scraped_data["scraped_unique_selling_points"]
        if "scraped_target_audience" in scraped_data:
            profile.scraped_target_audience = scraped_data["scraped_target_audience"]
        if "scraped_raw_content" in scraped_data:
            profile.scraped_raw_content = scraped_data["scraped_raw_content"]
        if "last_scraped_at" in scraped_data:
            profile.last_scraped_at = scraped_data["last_scraped_at"]
        else:
            profile.last_scraped_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def get_scraped_suggestions(self, tenant_id: int) -> dict[str, Any] | None:
        """Get scraped data suggestions for the interview.

        Args:
            tenant_id: The tenant ID

        Returns:
            Dictionary with scraped data for interview pre-fill or None
        """
        profile = await self.get_by_tenant_id(tenant_id)
        if not profile:
            return None

        return {
            "business_name": profile.business_name,
            "services": profile.scraped_services,
            "programs": profile.scraped_programs,
            "locations": profile.scraped_locations,
            "hours": profile.scraped_hours,
            "pricing": profile.scraped_pricing,
            "faqs": profile.scraped_faqs,
            "policies": profile.scraped_policies,
            "target_audience": profile.scraped_target_audience,
            "unique_selling_points": profile.scraped_unique_selling_points,
            "last_scraped_at": profile.last_scraped_at.isoformat() if profile.last_scraped_at else None,
            "has_scraped_data": any([
                profile.scraped_services,
                profile.scraped_programs,
                profile.scraped_locations,
                profile.scraped_hours,
            ]),
        }
