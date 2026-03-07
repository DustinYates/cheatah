"""Microsoft Outlook / Graph API client wrapper for OAuth and email operations."""

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)

AUTHORITY = "https://login.microsoftonline.com/common"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read", "Mail.Send", "offline_access", "User.Read"]


class OutlookClientError(Exception):
    """Base exception for Outlook client errors."""
    pass


class OutlookAuthError(OutlookClientError):
    """OAuth authentication error."""
    pass


class OutlookAPIError(OutlookClientError):
    """Microsoft Graph API operation error."""
    pass


class OutlookClient:
    """Microsoft Graph API client wrapper for Outlook email operations."""

    def __init__(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.token_expires_at = token_expires_at

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
        """Get OAuth authorization URL for Microsoft consent.

        Returns:
            Tuple of (authorization_url, state)
        """
        if not settings.outlook_client_id or not settings.outlook_client_secret:
            raise OutlookAuthError("Outlook OAuth credentials not configured")

        params = {
            "client_id": settings.outlook_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "response_mode": "query",
            "prompt": "consent",
            "state": state or "",
        }
        auth_url = f"{AUTHORITY}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
        return auth_url, state or ""

    @classmethod
    async def exchange_code_for_tokens(cls, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for OAuth tokens.

        Returns:
            Dictionary with access_token, refresh_token, token_expires_at, email
        """
        if not settings.outlook_client_id or not settings.outlook_client_secret:
            raise OutlookAuthError("Outlook OAuth credentials not configured")

        try:
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    f"{AUTHORITY}/oauth2/v2.0/token",
                    data={
                        "client_id": settings.outlook_client_id,
                        "client_secret": settings.outlook_client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                        "scope": " ".join(SCOPES),
                    },
                )
                token_response.raise_for_status()
                token_data = token_response.json()

                access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

                # Get user email from /me endpoint
                me_response = await client.get(
                    f"{GRAPH_BASE}/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                me_response.raise_for_status()
                me_data = me_response.json()
                email = me_data.get("mail") or me_data.get("userPrincipalName")

                return {
                    "access_token": access_token,
                    "refresh_token": token_data.get("refresh_token"),
                    "token_expires_at": token_expires_at,
                    "email": email,
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook token exchange failed: {e.response.text}")
            raise OutlookAuthError(f"Token exchange failed: {e.response.text}") from e
        except Exception as e:
            logger.error(f"Outlook token exchange failed: {e}")
            raise OutlookAuthError(f"Token exchange failed: {str(e)}") from e

    async def _refresh_token_if_needed(self) -> str:
        """Refresh access token if expired. Returns valid access token."""
        if not self.refresh_token:
            raise OutlookAuthError("No refresh token available")

        # Check if token is still valid (with 5 min buffer)
        if (
            self.access_token
            and self.token_expires_at
            and self.token_expires_at > datetime.utcnow() + timedelta(minutes=5)
        ):
            return self.access_token

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{AUTHORITY}/oauth2/v2.0/token",
                    data={
                        "client_id": settings.outlook_client_id,
                        "client_secret": settings.outlook_client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token",
                        "scope": " ".join(SCOPES),
                    },
                )
                response.raise_for_status()
                data = response.json()

                self.access_token = data["access_token"]
                expires_in = data.get("expires_in", 3600)
                self.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                # Microsoft may issue a new refresh token
                if data.get("refresh_token"):
                    self.refresh_token = data["refresh_token"]

                return self.access_token
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook token refresh failed: {e.response.text}")
            raise OutlookAuthError(f"Token refresh failed: {e.response.text}") from e
        except Exception as e:
            logger.error(f"Outlook token refresh failed: {e}")
            raise OutlookAuthError(f"Token refresh failed: {str(e)}") from e

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated request headers."""
        token = await self._refresh_token_if_needed()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_token_info(self) -> dict[str, Any]:
        """Get current token information after potential refresh."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expires_at": self.token_expires_at,
        }

    async def get_profile(self) -> dict[str, Any]:
        """Get the connected Outlook profile info."""
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{GRAPH_BASE}/me", headers=headers)
                response.raise_for_status()
                data = response.json()
                return {
                    "email": data.get("mail") or data.get("userPrincipalName"),
                    "displayName": data.get("displayName"),
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook get profile failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to get profile: {e.response.text}") from e

    async def watch_mailbox(self, notification_url: str, client_state: str) -> dict[str, Any]:
        """Create a Graph subscription for inbox change notifications.

        Args:
            notification_url: Webhook URL for notifications
            client_state: Secret value echoed back in notifications for verification

        Returns:
            Dictionary with subscription_id and expiration
        """
        # Max expiration for mail resources: 4230 minutes (~2.9 days)
        expiration = datetime.now(timezone.utc) + timedelta(minutes=4200)

        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{GRAPH_BASE}/subscriptions",
                    headers=headers,
                    json={
                        "changeType": "created",
                        "notificationUrl": notification_url,
                        "resource": "me/mailFolders('Inbox')/messages",
                        "expirationDateTime": expiration.isoformat(),
                        "clientState": client_state,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "subscription_id": data["id"],
                    "expiration": datetime.fromisoformat(
                        data["expirationDateTime"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook subscription creation failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to create subscription: {e.response.text}") from e

    async def renew_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Renew an existing Graph subscription.

        Returns:
            Dictionary with subscription_id and new expiration
        """
        expiration = datetime.now(timezone.utc) + timedelta(minutes=4200)

        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{GRAPH_BASE}/subscriptions/{subscription_id}",
                    headers=headers,
                    json={"expirationDateTime": expiration.isoformat()},
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "subscription_id": data["id"],
                    "expiration": datetime.fromisoformat(
                        data["expirationDateTime"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook subscription renewal failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to renew subscription: {e.response.text}") from e

    async def stop_watch(self, subscription_id: str) -> bool:
        """Delete a Graph subscription."""
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{GRAPH_BASE}/subscriptions/{subscription_id}",
                    headers=headers,
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook stop watch failed: {e.response.text}")
            return False

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a specific email message.

        Returns:
            Message details matching GmailClient.get_message() shape
        """
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GRAPH_BASE}/me/messages/{message_id}",
                    headers=headers,
                    params={"$select": "id,conversationId,subject,from,toRecipients,receivedDateTime,body,bodyPreview"},
                )
                response.raise_for_status()
                msg = response.json()

                body = self._extract_body(msg)
                from_addr = msg.get("from", {}).get("emailAddress", {})
                to_addrs = msg.get("toRecipients", [])
                to_email = to_addrs[0]["emailAddress"]["address"] if to_addrs else ""

                return {
                    "id": msg["id"],
                    "thread_id": msg.get("conversationId"),
                    "subject": msg.get("subject", ""),
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>".strip(),
                    "from_email": from_addr.get("address", ""),
                    "to": to_email,
                    "date": msg.get("receivedDateTime", ""),
                    "body": body,
                    "snippet": msg.get("bodyPreview", ""),
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook get message failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to get message: {e.response.text}") from e

    async def get_thread(self, conversation_id: str) -> dict[str, Any]:
        """Get all messages in a conversation thread.

        Args:
            conversation_id: Outlook conversation ID

        Returns:
            Thread details with all messages
        """
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GRAPH_BASE}/me/messages",
                    headers=headers,
                    params={
                        "$filter": f"conversationId eq '{conversation_id}'",
                        "$orderby": "receivedDateTime asc",
                        "$select": "id,conversationId,subject,from,toRecipients,receivedDateTime,body,bodyPreview",
                    },
                )
                response.raise_for_status()
                data = response.json()

                messages = []
                for msg in data.get("value", []):
                    from_addr = msg.get("from", {}).get("emailAddress", {})
                    to_addrs = msg.get("toRecipients", [])
                    to_email = to_addrs[0]["emailAddress"]["address"] if to_addrs else ""
                    messages.append({
                        "id": msg["id"],
                        "thread_id": msg.get("conversationId"),
                        "subject": msg.get("subject", ""),
                        "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>".strip(),
                        "to": to_email,
                        "date": msg.get("receivedDateTime", ""),
                        "body": self._extract_body(msg),
                        "snippet": msg.get("bodyPreview", ""),
                    })

                return {
                    "id": conversation_id,
                    "messages": messages,
                    "message_count": len(messages),
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook get thread failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to get thread: {e.response.text}") from e

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        conversation_id: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        """Send an email message via Outlook.

        Returns:
            Sent message details
        """
        try:
            headers = await self._get_headers()
            message_payload: dict[str, Any] = {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }

            if in_reply_to:
                message_payload["internetMessageHeaders"] = [
                    {"name": "In-Reply-To", "value": in_reply_to},
                ]
                if references:
                    message_payload["internetMessageHeaders"].append(
                        {"name": "References", "value": references}
                    )

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{GRAPH_BASE}/me/sendMail",
                    headers=headers,
                    json={"message": message_payload, "saveToSentItems": True},
                )
                response.raise_for_status()

                return {"id": None, "thread_id": conversation_id}
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook send message failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to send message: {e.response.text}") from e

    async def list_recent_messages(self, max_results: int = 5) -> list[dict[str, Any]]:
        """List recent messages from the inbox."""
        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
                    headers=headers,
                    params={
                        "$top": min(max_results, 10),
                        "$orderby": "receivedDateTime desc",
                        "$select": "id,subject,from,receivedDateTime,bodyPreview",
                    },
                )
                response.raise_for_status()
                data = response.json()

                return [
                    {
                        "id": msg["id"],
                        "subject": msg.get("subject", "(no subject)"),
                        "from": msg.get("from", {}).get("emailAddress", {}).get("address", "unknown"),
                        "date": msg.get("receivedDateTime", ""),
                        "snippet": msg.get("bodyPreview", ""),
                    }
                    for msg in data.get("value", [])
                ]
        except httpx.HTTPStatusError as e:
            logger.error(f"Outlook list recent messages failed: {e.response.text}")
            raise OutlookAPIError(f"Failed to list messages: {e.response.text}") from e

    def _extract_body(self, message: dict) -> str:
        """Extract plain text body from Outlook message.

        Prefers text content, converts HTML if needed.
        """
        body_data = message.get("body", {})
        content_type = body_data.get("contentType", "")
        content = body_data.get("content", "")

        if not content:
            return message.get("bodyPreview", "")

        if content_type.lower() == "html":
            return self._html_to_text(content)

        return content

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML content to plain text, preserving structure."""
        text = html

        # Replace <br> variants with newlines
        text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)

        # Replace closing block tags with newlines
        block_tags = ['p', 'div', 'tr', 'td', 'th', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
        for tag in block_tags:
            text = re.sub(rf'</{tag}\s*>', '\n', text, flags=re.IGNORECASE)

        # Separate table cells
        text = re.sub(r'<t[dh][^>]*>', '\n', text, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode common HTML entities
        html_entities = {
            '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
            '&quot;': '"', '&#39;': "'", '&apos;': "'",
        }
        for entity, char in html_entities.items():
            text = text.replace(entity, char)

        # Handle numeric entities
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
        text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)

        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)

        return text.strip()

    @staticmethod
    def parse_email_address(email_header: str) -> tuple[str, str]:
        """Parse email address from header (e.g., 'Name <email@example.com>')."""
        match = re.match(r'^(.+?)\s*<([^>]+)>$', email_header.strip())
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return name, email
        return "", email_header.strip()
