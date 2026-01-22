"""SendGrid email client for sending emails."""

from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, ReplyTo
from app.settings import settings
from app.core.debug import debug_log


class SendGridClient:
    """Client for sending emails via SendGrid.

    Supports multi-tenant usage by accepting credentials in constructor.
    Falls back to global settings if not provided.
    """

    def __init__(
        self,
        api_key: str | None = None,
        from_email: str | None = None,
    ):
        """Initialize SendGrid client.

        Args:
            api_key: SendGrid API key (defaults to global settings.sendgrid_api_key)
            from_email: Default sender email (defaults to global settings.sendgrid_from_email)
        """
        self.api_key = api_key or settings.sendgrid_api_key
        self.default_from_email = from_email or settings.sendgrid_from_email

        if not self.api_key:
            raise ValueError("SendGrid API key must be provided or set in SENDGRID_API_KEY")
        self.client = SendGridAPIClient(self.api_key)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        text_content: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """
        Send an email via SendGrid.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            from_email: Sender email (defaults to instance default_from_email)
            text_content: Plain text email body (optional)
            reply_to: Reply-to email address (optional)

        Returns:
            Response dict with status and message_id
        """
        try:
            from_addr = from_email or self.default_from_email

            message = Mail(
                from_email=Email(from_addr),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=text_content,
                html_content=Content("text/html", html_content),
            )

            if reply_to:
                message.reply_to = ReplyTo(reply_to)

            response = self.client.send(message)

            debug_log(
                "sendgrid_client.py:send_email",
                "Email sent successfully",
                {
                    "to": to_email,
                    "subject": subject,
                    "status_code": response.status_code,
                },
            )

            return {
                "status": "success",
                "message_id": response.headers.get("X-Message-Id"),
                "status_code": response.status_code,
            }

        except Exception as e:
            debug_log(
                "sendgrid_client.py:send_email",
                f"Failed to send email: {str(e)}",
                {"to": to_email, "error": str(e)},
            )
            raise


# Singleton instance
_sendgrid_client: Optional[SendGridClient] = None


def get_sendgrid_client() -> SendGridClient:
    """Get or create SendGrid client singleton."""
    global _sendgrid_client
    if _sendgrid_client is None:
        _sendgrid_client = SendGridClient()
    return _sendgrid_client
