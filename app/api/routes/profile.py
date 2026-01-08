"""Tenant business profile routes."""

import asyncio
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_context
from app.domain.services.website_scraper_service import WebsiteScraperService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.business_profile_repository import BusinessProfileRepository

logger = logging.getLogger(__name__)
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
    last_scraped_at: datetime | None = None
    has_scraped_data: bool = False

    class Config:
        from_attributes = True


class BusinessProfileUpdate(BaseModel):
    """Business profile update request."""

    business_name: str | None = None
    website_url: str | None = None
    phone_number: str | None = None
    twilio_phone: str | None = None
    email: str | None = None


class ScrapeStatusResponse(BaseModel):
    """Response for scrape status check."""

    last_scraped_at: datetime | None
    has_scraped_data: bool
    scraping_in_progress: bool = False


# Track ongoing scraping tasks
_scraping_in_progress: dict[int, bool] = {}


async def _run_website_scrape(tenant_id: int, website_url: str, db_url: str) -> None:
    """Background task to scrape a website and update the profile.

    Args:
        tenant_id: The tenant ID
        website_url: The URL to scrape
        db_url: Database connection URL for creating new session
    """
    from app.persistence.database import async_session_factory

    _scraping_in_progress[tenant_id] = True
    try:
        logger.info(f"Starting background scrape for tenant {tenant_id}: {website_url}")
        scraper = WebsiteScraperService()
        scraped_data = await scraper.scrape_business_website(website_url)

        # Create a new database session for the background task
        async with async_session_factory() as session:
            profile_repo = BusinessProfileRepository(session)
            db_data = scraped_data.to_db_format()
            await profile_repo.update_scraped_data(tenant_id, db_data)

        logger.info(f"Completed background scrape for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Background scrape failed for tenant {tenant_id}: {e}", exc_info=True)
    finally:
        _scraping_in_progress.pop(tenant_id, None)


def _has_scraped_data(profile: Any) -> bool:
    """Check if profile has any scraped data."""
    return any([
        profile.scraped_services,
        profile.scraped_programs,
        profile.scraped_locations,
        profile.scraped_hours,
    ])


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
        last_scraped_at=profile.last_scraped_at,
        has_scraped_data=_has_scraped_data(profile),
    )


@router.put("/profile", response_model=BusinessProfileResponse)
async def update_business_profile(
    profile_data: BusinessProfileUpdate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BusinessProfileResponse:
    """Update business profile for current tenant.

    If the website URL changes, automatically triggers background scraping
    to extract business information from the website.
    """
    profile_repo = BusinessProfileRepository(db)

    existing = await profile_repo.get_by_tenant_id(tenant_id)
    if not existing:
        existing = await profile_repo.create_for_tenant(tenant_id)

    # Check if website URL is changing
    url_changed = (
        profile_data.website_url is not None
        and profile_data.website_url != existing.website_url
        and profile_data.website_url.strip()
    )

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

    # Trigger background scraping if URL changed
    if url_changed and profile.website_url:
        logger.info(f"Website URL changed for tenant {tenant_id}, triggering scrape")
        # Run scraping in background using asyncio.create_task
        asyncio.create_task(
            _run_website_scrape(tenant_id, profile.website_url, "")
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
        last_scraped_at=profile.last_scraped_at,
        has_scraped_data=_has_scraped_data(profile),
    )


@router.get("/profile/scrape-status", response_model=ScrapeStatusResponse)
async def get_scrape_status(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScrapeStatusResponse:
    """Get the current scraping status for the tenant's profile."""
    profile_repo = BusinessProfileRepository(db)
    profile = await profile_repo.get_by_tenant_id(tenant_id)

    if not profile:
        return ScrapeStatusResponse(
            last_scraped_at=None,
            has_scraped_data=False,
            scraping_in_progress=tenant_id in _scraping_in_progress,
        )

    return ScrapeStatusResponse(
        last_scraped_at=profile.last_scraped_at,
        has_scraped_data=_has_scraped_data(profile),
        scraping_in_progress=tenant_id in _scraping_in_progress,
    )


@router.post("/profile/rescrape", response_model=ScrapeStatusResponse)
async def trigger_rescrape(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScrapeStatusResponse:
    """Manually trigger a rescrape of the tenant's website."""
    profile_repo = BusinessProfileRepository(db)
    profile = await profile_repo.get_by_tenant_id(tenant_id)

    if not profile or not profile.website_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No website URL configured",
        )

    if tenant_id in _scraping_in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scraping already in progress",
        )

    logger.info(f"Manual rescrape triggered for tenant {tenant_id}")
    asyncio.create_task(
        _run_website_scrape(tenant_id, profile.website_url, "")
    )

    return ScrapeStatusResponse(
        last_scraped_at=profile.last_scraped_at,
        has_scraped_data=_has_scraped_data(profile),
        scraping_in_progress=True,
    )
