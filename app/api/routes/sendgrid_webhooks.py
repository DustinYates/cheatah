"""SendGrid Inbound Parse webhook endpoints for email lead ingestion."""

import hashlib
import hmac
import logging
import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.email_body_parser import EmailBodyParser
from app.domain.services.lead_service import LeadService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.persistence.database import get_db
from app.persistence.models.email_ingestion_log import EmailIngestionLog, IngestionStatus
from app.persistence.repositories.email_ingestion_repository import EmailIngestionLogRepository
from app.persistence.repositories.email_repository import TenantEmailConfigRepository
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class SendGridInboundPayload:
    """Parsed SendGrid Inbound Parse payload.

    SendGrid sends email data as multipart/form-data with these fields:
    - from: Sender email (may include name: "John Doe <john@example.com>")
    - to: Recipient email (the parse address)
    - subject: Email subject
    - text: Plain text body (if available)
    - html: HTML body (if available)
    - headers: Raw email headers as string
    - envelope: JSON string with routing info
    - sender_ip: IP address of sending server
    """

    def __init__(
        self,
        from_email: str,
        to: str,
        subject: str,
        text: str | None,
        html: str | None,
        headers: str,
        envelope: str,
        sender_ip: str | None = None,
    ):
        self.from_email = from_email
        self.to = to
        self.subject = subject
        self.text = text
        self.html = html
        self.headers = headers
        self.envelope = envelope
        self.sender_ip = sender_ip
        self._parsed_headers: dict[str, str] | None = None

    @property
    def message_id(self) -> str | None:
        """Extract Message-ID from headers."""
        if self._parsed_headers is None:
            self._parse_headers()
        return self._parsed_headers.get("message-id")

    @property
    def date(self) -> str | None:
        """Extract Date from headers."""
        if self._parsed_headers is None:
            self._parse_headers()
        return self._parsed_headers.get("date")

    @property
    def original_to(self) -> str | None:
        """Extract original To address from headers (before forwarding)."""
        if self._parsed_headers is None:
            self._parse_headers()
        # Check X-Forwarded-To or original To
        return self._parsed_headers.get("x-forwarded-to") or self._parsed_headers.get("to")

    def _parse_headers(self) -> None:
        """Parse raw headers string into dict."""
        self._parsed_headers = {}
        if not self.headers:
            return
        for line in self.headers.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                self._parsed_headers[key.strip().lower()] = value.strip()

    def get_body(self) -> str:
        """Get email body, preferring plain text over HTML."""
        if self.text and self.text.strip():
            return self.text
        if self.html and self.html.strip():
            # Convert HTML to text using EmailBodyParser's method
            parser = EmailBodyParser()
            return parser._strip_html_tags(self.html)
        return ""

    def get_sender_email(self) -> str:
        """Extract just the email address from the from field.

        Handles formats like:
        - "john@example.com"
        - "John Doe <john@example.com>"
        """
        from_field = self.from_email
        match = re.search(r"<([^>]+)>", from_field)
        if match:
            return match.group(1).lower()
        return from_field.strip().lower()

    def get_dedup_key(self) -> str:
        """Get deduplication key (Message-ID or hash fallback).

        Primary: RFC 2822 Message-ID header
        Fallback: SHA-256 hash of (from + subject + date + body prefix)
        """
        if self.message_id:
            return self.message_id
        # Fallback: hash of from + subject + date + body snippet
        content = f"{self.from_email}|{self.subject}|{self.date}|{self.get_body()[:500]}"
        return f"hash:{hashlib.sha256(content.encode()).hexdigest()}"

    def to_raw_payload(self) -> dict[str, Any]:
        """Convert to dictionary for storage in raw_payload field."""
        return {
            "from": self.from_email,
            "to": self.to,
            "subject": self.subject,
            "text_length": len(self.text or ""),
            "html_length": len(self.html or ""),
            "message_id": self.message_id,
            "date": self.date,
            "sender_ip": self.sender_ip,
            # Store actual body for replay capability
            "text": self.text,
            "html": self.html,
            "headers": self.headers,
        }


def _verify_webhook_secret(
    request: Request,
    webhook_secret: str,
) -> bool:
    """Verify SendGrid webhook shared secret.

    Uses a shared secret header for authentication.

    Args:
        request: FastAPI request
        webhook_secret: Expected secret value

    Returns:
        True if valid, False otherwise
    """
    # Check shared secret header
    provided_secret = request.headers.get("X-Sendgrid-Webhook-Secret")
    if provided_secret and hmac.compare_digest(provided_secret, webhook_secret):
        return True

    return False


def _should_capture_lead(subject: str, email_config) -> bool:
    """Check if email subject matches configured lead capture prefixes.

    Args:
        subject: Email subject line
        email_config: TenantEmailConfig with lead_capture_subject_prefixes

    Returns:
        True if subject matches a prefix, False otherwise
    """
    prefixes = email_config.lead_capture_subject_prefixes if email_config else None

    if prefixes is None:
        return False  # No prefixes configured = no capture

    if len(prefixes) == 0:
        return True  # Empty list = capture all

    subject_lower = (subject or "").lower().strip()

    # Strip common forwarding prefixes (Fwd:, Re:, Fw:, etc.)
    for prefix in ["fwd:", "re:", "fw:", "fyi:"]:
        while subject_lower.startswith(prefix):
            subject_lower = subject_lower[len(prefix) :].strip()

    for prefix in prefixes:
        if subject_lower.startswith((prefix or "").lower().strip()):
            return True

    return False


@router.post("/inbound")
async def sendgrid_inbound_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    # SendGrid sends multipart/form-data
    from_field: Annotated[str, Form(alias="from")] = "",
    to: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    text: Annotated[str | None, Form()] = None,
    html: Annotated[str | None, Form()] = None,
    headers: Annotated[str, Form()] = "",
    envelope: Annotated[str, Form()] = "",
    sender_ip: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle SendGrid Inbound Parse webhook.

    This endpoint:
    1. Parses SendGrid payload
    2. Resolves tenant from parse address
    3. Verifies webhook secret
    4. Deduplicates by Message-ID
    5. Queues for async processing (or processes sync in dev)
    6. Returns immediate 200 ACK

    Returns 200 even for errors to prevent SendGrid retries (we handle retries internally).
    """
    logger.info(f"[SENDGRID] Received inbound webhook: to={to}, subject={subject[:50] if subject else '(empty)'}...")

    # Parse payload
    payload = SendGridInboundPayload(
        from_email=from_field,
        to=to,
        subject=subject,
        text=text,
        html=html,
        headers=headers,
        envelope=envelope,
        sender_ip=sender_ip,
    )

    # Resolve tenant from parse address (the 'to' field)
    config_repo = TenantEmailConfigRepository(db)
    email_config = await config_repo.get_by_sendgrid_parse_address(to)

    if not email_config:
        logger.warning(f"[SENDGRID] No tenant found for parse address: {to}")
        # Return 200 to prevent retries (but log for investigation)
        return Response(status_code=200, content="OK")

    tenant_id = email_config.tenant_id

    # Verify webhook secret
    if email_config.sendgrid_webhook_secret:
        if not _verify_webhook_secret(request, email_config.sendgrid_webhook_secret):
            logger.warning(f"[SENDGRID] Invalid webhook secret for tenant {tenant_id}")
            raise HTTPException(status_code=403, detail="Invalid signature")
    elif settings.sendgrid_default_webhook_secret:
        # Fallback to global default secret
        if not _verify_webhook_secret(request, settings.sendgrid_default_webhook_secret):
            logger.warning(f"[SENDGRID] Invalid default webhook secret for tenant {tenant_id}")
            raise HTTPException(status_code=403, detail="Invalid signature")

    # Check if SendGrid ingestion is enabled for this tenant
    if not email_config.sendgrid_enabled:
        logger.info(f"[SENDGRID] SendGrid disabled for tenant {tenant_id}")
        return Response(status_code=200, content="OK")

    # Deduplication: attempt to create ingestion log
    dedup_key = payload.get_dedup_key()
    ingestion_repo = EmailIngestionLogRepository(db)

    try:
        ingestion_log = await ingestion_repo.create(
            tenant_id=tenant_id,
            message_id=dedup_key,
            message_id_hash=hashlib.sha256(dedup_key.encode()).hexdigest() if dedup_key.startswith("hash:") else None,
            from_email=payload.get_sender_email(),
            to_email=payload.to,
            subject=payload.subject,
            status=IngestionStatus.RECEIVED.value,
            raw_payload=payload.to_raw_payload(),
        )
        logger.info(f"[SENDGRID] Created ingestion log: id={ingestion_log.id}, dedup_key={dedup_key[:50]}...")
    except IntegrityError:
        # Duplicate detected via unique constraint
        logger.info(f"[SENDGRID] Duplicate email detected: {dedup_key[:50]}...")
        await db.rollback()
        return Response(status_code=200, content="OK (duplicate)")

    # Queue for async processing or process synchronously
    if settings.cloud_tasks_email_worker_url:
        cloud_tasks = CloudTasksClient()
        await cloud_tasks.create_task_async(
            payload={
                "ingestion_log_id": ingestion_log.id,
                "tenant_id": tenant_id,
            },
            url=f"{settings.cloud_tasks_email_worker_url}/process-sendgrid-email",
        )
        logger.info(f"[SENDGRID] Queued for processing: ingestion_log_id={ingestion_log.id}")
    else:
        # Synchronous processing (for dev/testing)
        logger.info(f"[SENDGRID] Processing synchronously (no Cloud Tasks configured)")
        await _process_sendgrid_email(db, tenant_id, payload, ingestion_log)

    return Response(status_code=200, content="OK")


async def _process_sendgrid_email(
    db: AsyncSession,
    tenant_id: int,
    payload: SendGridInboundPayload,
    ingestion_log: EmailIngestionLog,
) -> dict[str, Any]:
    """Process SendGrid email payload and create lead.

    Args:
        db: Database session
        tenant_id: Tenant ID
        payload: Parsed SendGrid payload
        ingestion_log: Ingestion log record for status tracking

    Returns:
        Dictionary with processing result
    """
    logger.info(f"[SENDGRID] Processing email for tenant {tenant_id}: subject={payload.subject}")

    ingestion_repo = EmailIngestionLogRepository(db)
    body_parser = EmailBodyParser()
    lead_service = LeadService(db)

    try:
        # Check if subject matches lead capture prefixes
        config_repo = TenantEmailConfigRepository(db)
        email_config = await config_repo.get_by_tenant_id(tenant_id)

        if not _should_capture_lead(payload.subject, email_config):
            logger.info(f"[SENDGRID] Subject does not match lead capture prefixes: {payload.subject}")
            await ingestion_repo.update_status(
                ingestion_log.id,
                IngestionStatus.SKIPPED,
                error_message="Subject does not match lead capture prefixes",
            )
            return {"status": "skipped", "reason": "subject_mismatch"}

        # Parse email body for lead data
        email_body = payload.get_body()
        parsed = body_parser.parse(email_body)

        logger.info(
            f"[SENDGRID] Parsed data: name={parsed.get('name')}, "
            f"email={parsed.get('email')}, phone={parsed.get('phone')}"
        )

        # Build metadata
        metadata = {
            "source": "email",
            "email_subject": payload.subject,
            "ingestion_method": "sendgrid_inbound_parse",
            "sender_email": payload.get_sender_email(),
        }
        if parsed.get("additional_fields"):
            metadata.update(parsed["additional_fields"])

        # Capture lead using existing LeadService
        lead = await lead_service.capture_lead(
            tenant_id=tenant_id,
            email=parsed.get("email"),
            phone=parsed.get("phone"),
            name=parsed.get("name"),
            metadata=metadata,
        )

        if lead:
            logger.info(f"[SENDGRID] Lead captured: id={lead.id}")
            await ingestion_repo.update_status(
                ingestion_log.id,
                IngestionStatus.PROCESSED,
                lead_id=lead.id,
            )
            return {"status": "processed", "lead_id": lead.id}
        else:
            logger.warning(f"[SENDGRID] Lead creation returned None")
            await ingestion_repo.update_status(
                ingestion_log.id,
                IngestionStatus.FAILED,
                error_message="Lead creation returned None",
            )
            return {"status": "failed", "reason": "lead_creation_failed"}

    except Exception as e:
        logger.error(f"[SENDGRID] Error processing email: {e}", exc_info=True)
        await ingestion_repo.update_status(
            ingestion_log.id,
            IngestionStatus.FAILED,
            error_message=str(e),
        )
        return {"status": "failed", "reason": str(e)}


class SendGridProcessPayload(BaseModel):
    """Payload for Cloud Tasks async processing."""

    ingestion_log_id: int
    tenant_id: int


@router.get("/health")
async def sendgrid_health() -> dict[str, str]:
    """Health check for SendGrid webhook endpoint."""
    return {"status": "healthy", "service": "sendgrid-inbound-parse"}
