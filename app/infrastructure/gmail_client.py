"""Gmail API client wrapper for OAuth and email operations."""

import base64
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.settings import settings

logger = logging.getLogger(__name__)


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a datetime to naive UTC.
    
    Google's OAuth library returns timezone-aware datetimes, but our database
    columns are timezone-naive. This helper ensures consistency.
    
    Args:
        dt: A datetime that may be timezone-aware or naive
        
    Returns:
        A timezone-naive datetime in UTC, or None if input is None
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convert to UTC and remove timezone info
        return dt.replace(tzinfo=None)
    return dt


class GmailClientError(Exception):
    """Base exception for Gmail client errors."""
    pass


class GmailAuthError(GmailClientError):
    """OAuth authentication error."""
    pass


class GmailAPIError(GmailClientError):
    """Gmail API operation error."""
    pass


class GmailClient:
    """Gmail API client wrapper for email operations."""

    # Required OAuth scopes for email responder
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ]

    def __init__(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        """Initialize Gmail client.
        
        Args:
            refresh_token: OAuth refresh token (for long-term access)
            access_token: OAuth access token (short-lived)
            token_expires_at: Access token expiration time
        """
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.token_expires_at = token_expires_at
        self._service = None
        self._credentials = None

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
        """Get OAuth authorization URL for user consent.
        
        Args:
            redirect_uri: Callback URL after authorization
            state: Optional state parameter for CSRF protection
            
        Returns:
            Tuple of (authorization_url, state)
            
        Raises:
            GmailAuthError: If OAuth configuration is missing
        """
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise GmailAuthError("Gmail OAuth credentials not configured")

        client_config = {
            "web": {
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
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
            prompt="consent",  # Force consent to get refresh token
            state=state,
        )

        return authorization_url, returned_state

    @classmethod
    def exchange_code_for_tokens(cls, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for OAuth tokens.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: The redirect URI used in authorization request
            
        Returns:
            Dictionary with tokens and email info
            
        Raises:
            GmailAuthError: If token exchange fails
        """
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise GmailAuthError("Gmail OAuth credentials not configured")

        client_config = {
            "web": {
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
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

            # Get the user's email address
            service = build("gmail", "v1", credentials=credentials)
            profile = service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress")

            return {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expires_at": _to_naive_utc(credentials.expiry),
                "email": email,
            }

        except Exception as e:
            logger.error(f"Failed to exchange authorization code: {e}")
            raise GmailAuthError(f"Token exchange failed: {str(e)}") from e

    def _get_credentials(self) -> Credentials:
        """Get or refresh OAuth credentials.
        
        Returns:
            Valid Google OAuth credentials
            
        Raises:
            GmailAuthError: If credentials are invalid or refresh fails
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        if not self.refresh_token:
            raise GmailAuthError("No refresh token available")

        try:
            self._credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret,
                scopes=self.SCOPES,
            )

            # Check if token needs refresh
            if not self._credentials.valid:
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    self.access_token = self._credentials.token
                    self.token_expires_at = _to_naive_utc(self._credentials.expiry)
                else:
                    raise GmailAuthError("Credentials expired and cannot be refreshed")

            return self._credentials

        except Exception as e:
            logger.error(f"Failed to get/refresh credentials: {e}")
            raise GmailAuthError(f"Credential refresh failed: {str(e)}") from e

    def _get_service(self):
        """Get Gmail API service instance.
        
        Returns:
            Gmail API service object
        """
        if self._service is None:
            credentials = self._get_credentials()
            self._service = build("gmail", "v1", credentials=credentials)
        return self._service

    def get_token_info(self) -> dict[str, Any]:
        """Get current token information after potential refresh.
        
        Returns:
            Dictionary with current token info
        """
        credentials = self._get_credentials()
        return {
            "access_token": credentials.token,
            "token_expires_at": _to_naive_utc(credentials.expiry),
        }

    def watch_mailbox(self, topic_name: str, label_ids: list[str] | None = None) -> dict[str, Any]:
        """Setup Gmail push notifications for inbox changes.
        
        Args:
            topic_name: Google Cloud Pub/Sub topic name (full path)
            label_ids: Optional list of label IDs to watch (defaults to INBOX)
            
        Returns:
            Watch response with historyId and expiration
            
        Raises:
            GmailAPIError: If watch setup fails
        """
        try:
            service = self._get_service()
            request_body = {
                "topicName": topic_name,
                "labelIds": label_ids or ["INBOX"],
            }
            response = service.users().watch(userId="me", body=request_body).execute()
            
            # Convert expiration (ms since epoch) to naive UTC datetime
            # Database columns are timezone-naive, so we return naive UTC
            expiration_ms = int(response.get("expiration", 0))
            expiration_dt = datetime.utcfromtimestamp(expiration_ms / 1000)
            
            return {
                "history_id": response.get("historyId"),
                "expiration": expiration_dt,
            }
        except HttpError as e:
            logger.error(f"Gmail watch setup failed: {e}")
            
            # Provide actionable error messages for common issues
            error_str = str(e)
            if e.resp.status == 403:
                if "User not authorized to perform this action" in error_str:
                    # This is a PubSub permissions issue
                    raise GmailAPIError(
                        f"Failed to setup watch: {error_str}. "
                        "The Gmail API service account (gmail-api-push@system.gserviceaccount.com) "
                        "needs the 'Pub/Sub Publisher' role on the topic. "
                        "Run: gcloud pubsub topics add-iam-policy-binding <topic-name> "
                        "--member='serviceAccount:gmail-api-push@system.gserviceaccount.com' "
                        "--role='roles/pubsub.publisher' --project=<project-id>"
                    ) from e
                else:
                    raise GmailAPIError(
                        f"Failed to setup watch (403 Forbidden): {error_str}. "
                        "Check that the Gmail API is enabled and OAuth scopes are correct."
                    ) from e
            elif e.resp.status == 404:
                raise GmailAPIError(
                    f"Failed to setup watch (404 Not Found): {error_str}. "
                    f"Verify the Pub/Sub topic exists: {topic_name}"
                ) from e
            else:
                raise GmailAPIError(f"Failed to setup watch: {error_str}") from e

    def stop_watch(self) -> bool:
        """Stop Gmail push notifications.
        
        Returns:
            True if successful
        """
        try:
            service = self._get_service()
            service.users().stop(userId="me").execute()
            return True
        except HttpError as e:
            logger.error(f"Gmail stop watch failed: {e}")
            return False

    def get_history(
        self,
        start_history_id: str,
        label_id: str = "INBOX",
        history_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get mailbox history changes since a history ID.
        
        Args:
            start_history_id: Starting history ID
            label_id: Label ID to filter history
            history_types: Types to include (messageAdded, messageDeleted, labelAdded, labelRemoved)
            
        Returns:
            History response with messages and new historyId
        """
        try:
            service = self._get_service()
            response = service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                labelId=label_id,
                historyTypes=history_types or ["messageAdded"],
            ).execute()
            
            messages = []
            for history in response.get("history", []):
                for msg_added in history.get("messagesAdded", []):
                    messages.append(msg_added.get("message", {}))
            
            return {
                "messages": messages,
                "history_id": response.get("historyId"),
            }
        except HttpError as e:
            logger.error(f"Gmail get history failed: {e}")
            raise GmailAPIError(f"Failed to get history: {str(e)}") from e

    def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Get a specific email message.
        
        Args:
            message_id: Gmail message ID
            format: Response format (full, metadata, minimal, raw)
            
        Returns:
            Message details including headers and body
            
        Raises:
            GmailAPIError: If message retrieval fails
        """
        try:
            service = self._get_service()
            message = service.users().messages().get(
                userId="me",
                id=message_id,
                format=format,
            ).execute()
            
            # Parse headers
            headers = {}
            for header in message.get("payload", {}).get("headers", []):
                headers[header["name"].lower()] = header["value"]
            
            # Extract body
            body = self._extract_body(message.get("payload", {}))
            
            return {
                "id": message.get("id"),
                "thread_id": message.get("threadId"),
                "label_ids": message.get("labelIds", []),
                "snippet": message.get("snippet"),
                "headers": headers,
                "subject": headers.get("subject", ""),
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "date": headers.get("date", ""),
                "body": body,
                "internal_date": message.get("internalDate"),
            }
        except HttpError as e:
            logger.error(f"Gmail get message failed: {e}")
            raise GmailAPIError(f"Failed to get message: {str(e)}") from e

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from message payload.
        
        Args:
            payload: Message payload from Gmail API
            
        Returns:
            Plain text body content
        """
        body = ""
        
        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    if part.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break
                elif part.get("mimeType", "").startswith("multipart/"):
                    body = self._extract_body(part)
                    if body:
                        break
        
        return body

    def get_thread(self, thread_id: str, format: str = "full") -> dict[str, Any]:
        """Get an email thread with all messages.
        
        Args:
            thread_id: Gmail thread ID
            format: Response format for messages
            
        Returns:
            Thread details with all messages
            
        Raises:
            GmailAPIError: If thread retrieval fails
        """
        try:
            service = self._get_service()
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format=format,
            ).execute()
            
            messages = []
            for msg in thread.get("messages", []):
                headers = {}
                for header in msg.get("payload", {}).get("headers", []):
                    headers[header["name"].lower()] = header["value"]
                
                body = self._extract_body(msg.get("payload", {}))
                
                messages.append({
                    "id": msg.get("id"),
                    "thread_id": msg.get("threadId"),
                    "snippet": msg.get("snippet"),
                    "headers": headers,
                    "subject": headers.get("subject", ""),
                    "from": headers.get("from", ""),
                    "to": headers.get("to", ""),
                    "date": headers.get("date", ""),
                    "body": body,
                    "internal_date": msg.get("internalDate"),
                })
            
            return {
                "id": thread.get("id"),
                "messages": messages,
                "message_count": len(messages),
            }
        except HttpError as e:
            logger.error(f"Gmail get thread failed: {e}")
            raise GmailAPIError(f"Failed to get thread: {str(e)}") from e

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        """Send an email message.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            thread_id: Optional thread ID for replies
            in_reply_to: Optional Message-ID header for threading
            references: Optional References header for threading
            
        Returns:
            Sent message details
            
        Raises:
            GmailAPIError: If sending fails
        """
        try:
            service = self._get_service()
            
            # Get sender email from profile
            profile = service.users().getProfile(userId="me").execute()
            from_email = profile.get("emailAddress")
            
            # Create message
            message = MIMEMultipart()
            message["to"] = to
            message["from"] = from_email
            message["subject"] = subject
            
            # Add threading headers for replies
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
            if references:
                message["References"] = references
            
            message.attach(MIMEText(body, "plain"))
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            
            # Build request body
            request_body: dict[str, Any] = {"raw": raw_message}
            if thread_id:
                request_body["threadId"] = thread_id
            
            # Send message
            sent_message = service.users().messages().send(
                userId="me",
                body=request_body,
            ).execute()
            
            return {
                "id": sent_message.get("id"),
                "thread_id": sent_message.get("threadId"),
                "label_ids": sent_message.get("labelIds", []),
            }
        except HttpError as e:
            logger.error(f"Gmail send message failed: {e}")
            raise GmailAPIError(f"Failed to send message: {str(e)}") from e

    def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            True if successful
        """
        try:
            service = self._get_service()
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Gmail mark as read failed: {e}")
            return False

    def add_label(self, message_id: str, label_id: str) -> bool:
        """Add a label to a message.
        
        Args:
            message_id: Gmail message ID
            label_id: Label ID to add
            
        Returns:
            True if successful
        """
        try:
            service = self._get_service()
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Gmail add label failed: {e}")
            return False

    @staticmethod
    def parse_email_address(email_header: str) -> tuple[str, str]:
        """Parse email address from header (e.g., 'Name <email@example.com>').
        
        Args:
            email_header: Email header value
            
        Returns:
            Tuple of (name, email_address)
        """
        import re
        
        # Try to match "Name <email>" format
        match = re.match(r'^(.+?)\s*<([^>]+)>$', email_header.strip())
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return name, email
        
        # Just an email address
        return "", email_header.strip()

