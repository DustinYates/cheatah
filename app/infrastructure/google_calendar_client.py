"""Google Calendar API client wrapper for OAuth and calendar operations."""

import logging
from datetime import datetime, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.settings import settings

logger = logging.getLogger(__name__)


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a datetime to naive UTC for database storage."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class GoogleCalendarError(Exception):
    """Base exception for Google Calendar client errors."""
    pass


class GoogleCalendarAuthError(GoogleCalendarError):
    """OAuth authentication error."""
    pass


class GoogleCalendarAPIError(GoogleCalendarError):
    """Google Calendar API operation error."""
    pass


class GoogleCalendarClient:
    """Google Calendar API client wrapper for scheduling operations."""

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def __init__(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.token_expires_at = token_expires_at
        self._service = None
        self._credentials = None

    @classmethod
    def _get_client_id(cls) -> str:
        """Get Google OAuth client ID, falling back to Gmail credentials."""
        return settings.google_calendar_client_id or settings.gmail_client_id or ""

    @classmethod
    def _get_client_secret(cls) -> str:
        """Get Google OAuth client secret, falling back to Gmail credentials."""
        return settings.google_calendar_client_secret or settings.gmail_client_secret or ""

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
        """Get OAuth authorization URL for user consent.

        Returns:
            Tuple of (authorization_url, state)
        """
        client_id = cls._get_client_id()
        client_secret = cls._get_client_secret()

        if not client_id or not client_secret:
            raise GoogleCalendarAuthError("Google Calendar OAuth credentials not configured")

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=cls.SCOPES,
            redirect_uri=redirect_uri,
        )

        authorization_url, returned_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )

        return authorization_url, returned_state

    @classmethod
    def exchange_code_for_tokens(cls, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for OAuth tokens.

        Returns:
            Dictionary with access_token, refresh_token, token_expires_at, email
        """
        client_id = cls._get_client_id()
        client_secret = cls._get_client_secret()

        if not client_id or not client_secret:
            raise GoogleCalendarAuthError("Google Calendar OAuth credentials not configured")

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=cls.SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.fetch_token(code=code)
            credentials = flow.credentials

            # Get the user's email via userinfo endpoint
            from google.auth.transport.requests import Request as AuthRequest
            import google.auth.transport.requests
            import json
            import urllib.request

            authed_session = google.auth.transport.requests.AuthorizedSession(credentials)
            response = authed_session.get("https://www.googleapis.com/oauth2/v2/userinfo")
            user_info = response.json()
            email = user_info.get("email")

            return {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": _to_naive_utc(credentials.expiry),
                "email": email,
            }

        except Exception as e:
            logger.error(f"Failed to exchange authorization code: {e}")
            raise GoogleCalendarAuthError(f"Token exchange failed: {str(e)}") from e

    def _get_credentials(self) -> Credentials:
        """Get or refresh OAuth credentials."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        if not self.refresh_token:
            raise GoogleCalendarAuthError("No refresh token available")

        try:
            self._credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self._get_client_id(),
                client_secret=self._get_client_secret(),
                scopes=self.SCOPES,
            )

            if not self._credentials.valid:
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    self.access_token = self._credentials.token
                    self.token_expires_at = _to_naive_utc(self._credentials.expiry)
                else:
                    raise GoogleCalendarAuthError("Credentials expired and cannot be refreshed")

            return self._credentials

        except GoogleCalendarAuthError:
            raise
        except Exception as e:
            logger.error(f"Failed to get/refresh credentials: {e}")
            raise GoogleCalendarAuthError(f"Credential refresh failed: {str(e)}") from e

    def _get_service(self):
        """Get Google Calendar API service instance."""
        if self._service is None:
            credentials = self._get_credentials()
            self._service = build("calendar", "v3", credentials=credentials)
        return self._service

    def get_token_info(self) -> dict[str, Any]:
        """Get current token information after potential refresh."""
        credentials = self._get_credentials()
        return {
            "access_token": credentials.token,
            "token_expires_at": _to_naive_utc(credentials.expiry),
        }

    def get_freebusy(
        self,
        calendar_id: str,
        time_min: str,
        time_max: str,
    ) -> list[dict[str, str]]:
        """Query free/busy information for a calendar.

        Args:
            calendar_id: Google Calendar ID (e.g., "primary")
            time_min: Start of query range (RFC 3339 format)
            time_max: End of query range (RFC 3339 format)

        Returns:
            List of busy periods [{"start": "...", "end": "..."}, ...]
        """
        try:
            service = self._get_service()
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": calendar_id}],
            }
            result = service.freebusy().query(body=body).execute()
            calendars = result.get("calendars", {})
            calendar_data = calendars.get(calendar_id, {})
            return calendar_data.get("busy", [])

        except HttpError as e:
            logger.error(f"Google Calendar freebusy query failed: {e}")
            raise GoogleCalendarAPIError(f"Failed to query free/busy: {str(e)}") from e

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        description: str,
        start_time: str,
        end_time: str,
        timezone: str = "America/New_York",
        attendee_email: str | None = None,
    ) -> dict[str, Any]:
        """Create a calendar event.

        Args:
            calendar_id: Google Calendar ID
            summary: Event title
            description: Event description
            start_time: Start time (RFC 3339 format)
            end_time: End time (RFC 3339 format)
            timezone: IANA timezone
            attendee_email: Optional attendee email address

        Returns:
            Event data including id and htmlLink
        """
        try:
            service = self._get_service()
            event_body: dict[str, Any] = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start_time,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": timezone,
                },
            }

            if attendee_email:
                event_body["attendees"] = [{"email": attendee_email}]

            event = service.events().insert(
                calendarId=calendar_id,
                body=event_body,
                sendUpdates="all" if attendee_email else "none",
            ).execute()

            return {
                "id": event.get("id"),
                "htmlLink": event.get("htmlLink"),
                "summary": event.get("summary"),
                "start": event.get("start"),
                "end": event.get("end"),
            }

        except HttpError as e:
            logger.error(f"Google Calendar create event failed: {e}")
            raise GoogleCalendarAPIError(f"Failed to create event: {str(e)}") from e

    def list_events(
        self,
        calendar_id: str,
        time_min: str,
        time_max: str,
    ) -> list[dict[str, Any]]:
        """List calendar events in a time range.

        Args:
            calendar_id: Google Calendar ID (e.g., "primary")
            time_min: Start of query range (RFC 3339 format)
            time_max: End of query range (RFC 3339 format)

        Returns:
            List of events with id, summary, start, end, htmlLink, etc.
        """
        try:
            service = self._get_service()
            result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=50,
                )
                .execute()
            )
            events = []
            for item in result.get("items", []):
                start = item.get("start", {})
                end = item.get("end", {})
                events.append({
                    "id": item.get("id"),
                    "summary": item.get("summary", "(No title)"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "all_day": "date" in start and "dateTime" not in start,
                    "htmlLink": item.get("htmlLink"),
                    "status": item.get("status"),
                })
            return events

        except HttpError as e:
            logger.error(f"Google Calendar list events failed: {e}")
            raise GoogleCalendarAPIError(f"Failed to list events: {str(e)}") from e

    def list_calendars(self) -> list[dict[str, str]]:
        """List calendars accessible by the user.

        Returns:
            List of calendars [{"id": "...", "summary": "...", "primary": bool}, ...]
        """
        try:
            service = self._get_service()
            result = service.calendarList().list().execute()
            calendars = []
            for item in result.get("items", []):
                calendars.append({
                    "id": item.get("id"),
                    "summary": item.get("summary"),
                    "primary": item.get("primary", False),
                })
            return calendars

        except HttpError as e:
            logger.error(f"Google Calendar list calendars failed: {e}")
            raise GoogleCalendarAPIError(f"Failed to list calendars: {str(e)}") from e
