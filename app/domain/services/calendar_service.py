"""Calendar service for managing Google Calendar scheduling."""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.google_calendar_client import (
    GoogleCalendarClient,
    GoogleCalendarAuthError,
    GoogleCalendarAPIError,
)
from app.persistence.models.tenant_calendar_config import DEFAULT_SCHEDULING_PREFERENCES
from app.persistence.repositories.calendar_repository import TenantCalendarConfigRepository

logger = logging.getLogger(__name__)


@dataclass
class TimeSlot:
    """A single available time slot."""
    start: datetime
    end: datetime
    display_label: str  # e.g., "Mon Jan 15, 10:00 AM - 10:30 AM"


@dataclass
class BookingResult:
    """Result of a booking attempt."""
    success: bool
    event_id: str | None = None
    event_link: str | None = None
    error: str | None = None


class CalendarService:
    """Service for calendar scheduling operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.config_repo = TenantCalendarConfigRepository(session)

    async def get_scheduling_mode(self, tenant_id: int) -> str:
        """Determine the scheduling mode for a tenant.

        Returns:
            "calendar_api" if Google Calendar is connected and enabled,
            "booking_link" if only a booking link URL is configured,
            "none" if no scheduling is available.
        """
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config:
            return "none"
        if config.is_enabled and config.google_refresh_token:
            return "calendar_api"
        if config.booking_link_url:
            return "booking_link"
        return "none"

    async def get_booking_link(self, tenant_id: int) -> str | None:
        """Get the fallback booking link URL for a tenant."""
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if config:
            return config.booking_link_url
        return None

    async def get_available_slots(
        self,
        tenant_id: int,
        date_start: date,
        num_days: int = 3,
    ) -> list[TimeSlot]:
        """Get available time slots for a tenant.

        Generates candidate slots from scheduling preferences, then removes
        slots that conflict with existing calendar events via the freebusy API.

        Args:
            tenant_id: Tenant ID
            date_start: First date to check
            num_days: Number of days to check (default 3)

        Returns:
            List of available TimeSlot objects
        """
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.is_enabled or not config.google_refresh_token:
            return []

        prefs = config.scheduling_preferences or DEFAULT_SCHEDULING_PREFERENCES
        tz_name = prefs.get("timezone", "America/New_York")
        tz = ZoneInfo(tz_name)
        duration = prefs.get("meeting_duration_minutes", 30)
        buffer = prefs.get("buffer_minutes", 15)
        available_hours = prefs.get("available_hours", {"start": "09:00", "end": "17:00"})
        available_days = prefs.get("available_days", [0, 1, 2, 3, 4])
        max_advance = prefs.get("max_advance_days", 14)
        calendar_id = config.calendar_id or "primary"

        # Clamp num_days to max_advance_days
        num_days = min(num_days, max_advance)

        # Parse available hours
        hour_start_parts = available_hours.get("start", "09:00").split(":")
        hour_end_parts = available_hours.get("end", "17:00").split(":")
        start_hour, start_min = int(hour_start_parts[0]), int(hour_start_parts[1])
        end_hour, end_min = int(hour_end_parts[0]), int(hour_end_parts[1])

        # Generate candidate slots
        candidates: list[TimeSlot] = []
        for day_offset in range(num_days):
            current_date = date_start + timedelta(days=day_offset)
            # weekday(): Monday=0, Sunday=6
            if current_date.weekday() not in available_days:
                continue

            slot_start = datetime(
                current_date.year, current_date.month, current_date.day,
                start_hour, start_min, tzinfo=tz,
            )
            day_end = datetime(
                current_date.year, current_date.month, current_date.day,
                end_hour, end_min, tzinfo=tz,
            )

            while slot_start + timedelta(minutes=duration) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration)

                # Skip slots in the past
                now = datetime.now(tz)
                if slot_start <= now:
                    slot_start = slot_end + timedelta(minutes=buffer)
                    continue

                label = slot_start.strftime("%a %b %d, %I:%M %p") + " - " + slot_end.strftime("%I:%M %p")
                candidates.append(TimeSlot(start=slot_start, end=slot_end, display_label=label))
                slot_start = slot_end + timedelta(minutes=buffer)

        if not candidates:
            return []

        # Query Google Calendar freebusy
        try:
            client = self._build_client(config)
            range_start = candidates[0].start.isoformat()
            range_end = candidates[-1].end.isoformat()
            busy_periods = client.get_freebusy(calendar_id, range_start, range_end)
            await self._update_tokens_if_refreshed(tenant_id, client)
        except (GoogleCalendarAuthError, GoogleCalendarAPIError) as e:
            logger.error(f"Failed to query freebusy for tenant {tenant_id}: {e}")
            # Return candidates without filtering if freebusy fails
            return candidates[:12]  # Limit to 12 slots

        # Parse busy periods into datetime ranges
        busy_ranges: list[tuple[datetime, datetime]] = []
        for period in busy_periods:
            busy_start = datetime.fromisoformat(period["start"])
            busy_end = datetime.fromisoformat(period["end"])
            # Ensure timezone-aware for comparison
            if busy_start.tzinfo is None:
                busy_start = busy_start.replace(tzinfo=ZoneInfo("UTC"))
            if busy_end.tzinfo is None:
                busy_end = busy_end.replace(tzinfo=ZoneInfo("UTC"))
            busy_ranges.append((busy_start, busy_end))

        # Filter out slots that overlap with busy periods
        available: list[TimeSlot] = []
        for slot in candidates:
            slot_overlaps = False
            for busy_start, busy_end in busy_ranges:
                if slot.start < busy_end and slot.end > busy_start:
                    slot_overlaps = True
                    break
            if not slot_overlaps:
                available.append(slot)

        # Limit to reasonable number of slots
        return available[:12]

    async def book_meeting(
        self,
        tenant_id: int,
        slot_start: datetime,
        customer_name: str,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        topic: str = "Meeting",
    ) -> BookingResult:
        """Book a meeting on the tenant's Google Calendar.

        Re-checks availability before creating the event.

        Args:
            tenant_id: Tenant ID
            slot_start: Start time for the meeting
            customer_name: Customer's name
            customer_email: Optional customer email (added as attendee)
            customer_phone: Optional customer phone
            topic: Meeting topic/reason

        Returns:
            BookingResult with success status and event details
        """
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config or not config.is_enabled or not config.google_refresh_token:
            return BookingResult(success=False, error="Calendar not configured")

        prefs = config.scheduling_preferences or DEFAULT_SCHEDULING_PREFERENCES
        duration = prefs.get("meeting_duration_minutes", 30)
        tz_name = prefs.get("timezone", "America/New_York")
        title_template = prefs.get("meeting_title_template", "Meeting with {customer_name}")
        calendar_id = config.calendar_id or "primary"

        slot_end = slot_start + timedelta(minutes=duration)

        try:
            client = self._build_client(config)

            # Re-check availability
            busy_periods = client.get_freebusy(
                calendar_id,
                slot_start.isoformat(),
                slot_end.isoformat(),
            )

            if busy_periods:
                return BookingResult(
                    success=False,
                    error="This time slot is no longer available. Please select another time.",
                )

            # Build event details
            summary = title_template.format(customer_name=customer_name)
            description_parts = [f"Topic: {topic}", f"Customer: {customer_name}"]
            if customer_email:
                description_parts.append(f"Email: {customer_email}")
            if customer_phone:
                description_parts.append(f"Phone: {customer_phone}")
            description_parts.append("\nBooked via ChatterCheetah chatbot")
            description = "\n".join(description_parts)

            event = client.create_event(
                calendar_id=calendar_id,
                summary=summary,
                description=description,
                start_time=slot_start.isoformat(),
                end_time=slot_end.isoformat(),
                timezone=tz_name,
                attendee_email=customer_email,
            )

            await self._update_tokens_if_refreshed(tenant_id, client)

            logger.info(
                f"Meeting booked for tenant {tenant_id}: "
                f"event_id={event.get('id')}, customer={customer_name}"
            )

            # Send booking notification SMS if enabled
            if prefs.get("booking_notification_enabled", False):
                try:
                    from app.infrastructure.notifications import NotificationService

                    notification_service = NotificationService(self.session)
                    await notification_service.notify_booking(
                        tenant_id=tenant_id,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        slot_start=slot_start,
                        slot_end=slot_end,
                        topic=topic,
                    )
                except Exception as e:
                    logger.error(f"Failed to send booking notification: {e}", exc_info=True)

            return BookingResult(
                success=True,
                event_id=event.get("id"),
                event_link=event.get("htmlLink"),
            )

        except (GoogleCalendarAuthError, GoogleCalendarAPIError) as e:
            logger.error(f"Failed to book meeting for tenant {tenant_id}: {e}")
            return BookingResult(success=False, error=f"Failed to create meeting: {str(e)}")

    def _build_client(self, config) -> GoogleCalendarClient:
        """Build a GoogleCalendarClient from tenant config."""
        return GoogleCalendarClient(
            refresh_token=config.google_refresh_token,
            access_token=config.google_access_token,
            token_expires_at=config.google_token_expires_at,
        )

    async def _update_tokens_if_refreshed(
        self, tenant_id: int, client: GoogleCalendarClient
    ) -> None:
        """Persist updated tokens if the client refreshed them."""
        try:
            token_info = client.get_token_info()
            if token_info["access_token"] != client.access_token:
                return  # No change
            # Always update to be safe (token may have been refreshed)
            await self.config_repo.update_tokens(
                tenant_id=tenant_id,
                access_token=token_info["access_token"],
                token_expires_at=token_info["token_expires_at"],
            )
        except Exception as e:
            logger.warning(f"Failed to update calendar tokens for tenant {tenant_id}: {e}")
