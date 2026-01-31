"""Tenant-facing calendar endpoints for Google Calendar OAuth and scheduling."""

import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.api.deps import get_current_user, get_current_tenant
from app.domain.services.calendar_service import CalendarService
from app.infrastructure.google_calendar_client import (
    GoogleCalendarAuthError,
    GoogleCalendarClient,
)
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.calendar_repository import TenantCalendarConfigRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models

class CalendarSettingsResponse(BaseModel):
    """Calendar settings visible to tenant."""
    is_enabled: bool
    google_email: str | None
    is_connected: bool
    calendar_id: str | None
    booking_link_url: str | None
    scheduling_preferences: dict | None


class UpdateCalendarSettingsRequest(BaseModel):
    """Tenant-editable calendar settings."""
    booking_link_url: str | None = None
    calendar_id: str | None = "primary"
    scheduling_preferences: dict | None = None


class OAuthStartResponse(BaseModel):
    """Response from Calendar OAuth start."""
    authorization_url: str
    state: str


class AvailableSlotsResponse(BaseModel):
    """Available time slots for scheduling."""
    slots: list[dict]
    scheduling_mode: str
    booking_link: str | None = None


class BookMeetingRequest(BaseModel):
    """Request to book a meeting."""
    slot_start: str  # ISO datetime
    customer_name: str
    customer_email: str | None = None
    customer_phone: str | None = None
    topic: str = "Meeting"


class BookMeetingResponse(BaseModel):
    """Response from booking a meeting."""
    success: bool
    event_link: str | None = None
    error: str | None = None


class CalendarEventsResponse(BaseModel):
    """Calendar events for a date range."""
    events: list[dict]
    week_start: str
    week_end: str


class CalendarListResponse(BaseModel):
    """List of available calendars."""
    calendars: list[dict]


# Endpoints

@router.get("/settings", response_model=CalendarSettingsResponse)
async def get_calendar_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalendarSettingsResponse:
    """Get calendar settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if not config:
        from app.persistence.models.tenant_calendar_config import DEFAULT_SCHEDULING_PREFERENCES
        return CalendarSettingsResponse(
            is_enabled=False,
            google_email=None,
            is_connected=False,
            calendar_id="primary",
            booking_link_url=None,
            scheduling_preferences=DEFAULT_SCHEDULING_PREFERENCES,
        )

    return CalendarSettingsResponse(
        is_enabled=config.is_enabled,
        google_email=config.google_email,
        is_connected=bool(config.google_refresh_token),
        calendar_id=config.calendar_id,
        booking_link_url=config.booking_link_url,
        scheduling_preferences=config.scheduling_preferences,
    )


@router.put("/settings", response_model=CalendarSettingsResponse)
async def update_calendar_settings(
    settings_data: UpdateCalendarSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalendarSettingsResponse:
    """Update calendar settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    update_kwargs: dict = {}
    if settings_data.booking_link_url is not None:
        update_kwargs["booking_link_url"] = settings_data.booking_link_url
    if settings_data.calendar_id is not None:
        update_kwargs["calendar_id"] = settings_data.calendar_id
    if settings_data.scheduling_preferences is not None:
        update_kwargs["scheduling_preferences"] = settings_data.scheduling_preferences

    config = await config_repo.create_or_update(tenant_id=tenant_id, **update_kwargs)

    return CalendarSettingsResponse(
        is_enabled=config.is_enabled,
        google_email=config.google_email,
        is_connected=bool(config.google_refresh_token),
        calendar_id=config.calendar_id,
        booking_link_url=config.booking_link_url,
        scheduling_preferences=config.scheduling_preferences,
    )


@router.put("/enable")
async def toggle_calendar(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    enabled: bool = True,
) -> dict[str, bool]:
    """Enable or disable calendar scheduling."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if enabled and (not config or not config.google_refresh_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot enable calendar without connecting Google Calendar first.",
        )

    await config_repo.create_or_update(tenant_id=tenant_id, is_enabled=enabled)
    return {"is_enabled": enabled}


@router.post("/oauth/start", response_model=OAuthStartResponse)
async def start_calendar_oauth(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OAuthStartResponse:
    """Start Google Calendar OAuth flow."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    client_id = settings.google_calendar_client_id or settings.gmail_client_id
    client_secret = settings.google_calendar_client_secret or settings.gmail_client_secret

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration not configured. Contact support.",
        )

    redirect_uri = settings.google_calendar_oauth_redirect_uri
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth redirect URI not configured.",
        )

    # Generate state token with embedded tenant_id
    state = f"{tenant_id}:{secrets.token_urlsafe(32)}"

    try:
        authorization_url, returned_state = GoogleCalendarClient.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
        )
        return OAuthStartResponse(
            authorization_url=authorization_url,
            state=state,
        )
    except GoogleCalendarAuthError as e:
        logger.error(f"Calendar OAuth start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start OAuth flow: {str(e)}",
        )


@router.get("/oauth/callback")
async def calendar_oauth_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Handle Google Calendar OAuth callback (public endpoint)."""
    base_url = settings.frontend_url or "https://chattercheatah-900139201687.us-central1.run.app"

    if error:
        logger.error(f"Calendar OAuth error from Google: {error}")
        return RedirectResponse(
            url=f"{base_url}/settings/calendar?error=oauth_error&message={error}",
            status_code=302,
        )

    if not code or not state:
        logger.error("Calendar OAuth callback missing required parameters")
        return RedirectResponse(
            url=f"{base_url}/settings/calendar?error=missing_parameters",
            status_code=302,
        )

    # Parse tenant_id from state
    try:
        parts = state.split(":", 1)
        tenant_id = int(parts[0])
    except (ValueError, IndexError):
        logger.error(f"Invalid Calendar OAuth state: {state}")
        return RedirectResponse(
            url=f"{base_url}/settings/calendar?error=invalid_state",
            status_code=302,
        )

    redirect_uri = settings.google_calendar_oauth_redirect_uri
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth redirect URI not configured.",
        )

    try:
        token_data = GoogleCalendarClient.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
        )

        config_repo = TenantCalendarConfigRepository(db)
        await config_repo.create_or_update(
            tenant_id=tenant_id,
            google_email=token_data["email"],
            google_refresh_token=token_data["refresh_token"],
            google_access_token=token_data["access_token"],
            google_token_expires_at=token_data["token_expires_at"],
            is_enabled=True,
        )

        logger.info(f"Google Calendar connected for tenant {tenant_id}: {token_data['email']}")

        return RedirectResponse(
            url=f"{base_url}/settings/calendar?connected=true&email={token_data['email']}",
            status_code=302,
        )

    except GoogleCalendarAuthError as e:
        logger.error(f"Calendar OAuth callback failed: {e}")
        return RedirectResponse(
            url=f"{base_url}/settings/calendar?error={str(e)}",
            status_code=302,
        )


@router.delete("/disconnect")
async def disconnect_calendar(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Disconnect Google Calendar from tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    await config_repo.create_or_update(
        tenant_id=tenant_id,
        is_enabled=False,
        google_email=None,
        google_refresh_token=None,
        google_access_token=None,
        google_token_expires_at=None,
    )

    logger.info(f"Google Calendar disconnected for tenant {tenant_id}")
    return {"status": "ok", "message": "Google Calendar disconnected successfully"}


@router.get("/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    date_start: Annotated[str | None, Query()] = None,
    num_days: Annotated[int, Query(ge=1, le=14)] = 3,
) -> AvailableSlotsResponse:
    """Get available time slots for scheduling."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    calendar_service = CalendarService(db)
    mode = await calendar_service.get_scheduling_mode(tenant_id)

    if mode == "none":
        return AvailableSlotsResponse(slots=[], scheduling_mode="none")

    if mode == "booking_link":
        link = await calendar_service.get_booking_link(tenant_id)
        return AvailableSlotsResponse(
            slots=[], scheduling_mode="booking_link", booking_link=link,
        )

    # calendar_api mode
    start = date.fromisoformat(date_start) if date_start else date.today()
    slots = await calendar_service.get_available_slots(tenant_id, start, num_days)

    return AvailableSlotsResponse(
        slots=[
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "display_label": s.display_label,
            }
            for s in slots
        ],
        scheduling_mode="calendar_api",
    )


@router.post("/book", response_model=BookMeetingResponse)
async def book_meeting(
    request: BookMeetingRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BookMeetingResponse:
    """Book a meeting on the tenant's calendar."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    calendar_service = CalendarService(db)

    # Parse the slot_start datetime
    try:
        slot_start = datetime.fromisoformat(request.slot_start)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid slot_start format. Use ISO 8601.",
        )

    result = await calendar_service.book_meeting(
        tenant_id=tenant_id,
        slot_start=slot_start,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        customer_phone=request.customer_phone,
        topic=request.topic,
    )

    return BookMeetingResponse(
        success=result.success,
        event_link=result.event_link,
        error=result.error,
    )


@router.get("/events", response_model=CalendarEventsResponse)
async def get_calendar_events(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    week_offset: Annotated[int, Query(ge=-4, le=4)] = 0,
) -> CalendarEventsResponse:
    """Get calendar events for the current week (Mon-Sun).

    Args:
        week_offset: 0 = current week, 1 = next week, -1 = last week
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    # Calculate week boundaries (Monday-Sunday)
    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)

    if not config or not config.google_refresh_token:
        return CalendarEventsResponse(
            events=[],
            week_start=monday.isoformat(),
            week_end=sunday.isoformat(),
        )

    tz_name = "America/New_York"
    if config.scheduling_preferences:
        tz_name = config.scheduling_preferences.get("timezone", tz_name)
    tz = ZoneInfo(tz_name)

    time_min = datetime.combine(monday, datetime.min.time(), tzinfo=tz).isoformat()
    time_max = datetime.combine(sunday + timedelta(days=1), datetime.min.time(), tzinfo=tz).isoformat()

    calendar_id = config.calendar_id or "primary"

    try:
        client = GoogleCalendarClient(
            refresh_token=config.google_refresh_token,
            access_token=config.google_access_token,
            token_expires_at=config.google_token_expires_at,
        )
        events = client.list_events(calendar_id, time_min, time_max)

        # Update tokens if refreshed
        token_info = client.get_token_info()
        await config_repo.update_tokens(
            tenant_id=tenant_id,
            access_token=token_info["access_token"],
            token_expires_at=token_info["token_expires_at"],
        )

        return CalendarEventsResponse(
            events=events,
            week_start=monday.isoformat(),
            week_end=sunday.isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to fetch calendar events for tenant {tenant_id}: {e}")
        return CalendarEventsResponse(
            events=[],
            week_start=monday.isoformat(),
            week_end=sunday.isoformat(),
        )


@router.get("/calendars", response_model=CalendarListResponse)
async def list_calendars(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalendarListResponse:
    """List available Google Calendars for the connected account."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantCalendarConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if not config or not config.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar not connected",
        )

    try:
        client = GoogleCalendarClient(
            refresh_token=config.google_refresh_token,
            access_token=config.google_access_token,
            token_expires_at=config.google_token_expires_at,
        )
        calendars = client.list_calendars()

        # Update tokens if refreshed
        token_info = client.get_token_info()
        await config_repo.update_tokens(
            tenant_id=tenant_id,
            access_token=token_info["access_token"],
            token_expires_at=token_info["token_expires_at"],
        )

        return CalendarListResponse(calendars=calendars)

    except Exception as e:
        logger.error(f"Failed to list calendars for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list calendars: {str(e)}",
        )
