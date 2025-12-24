"""Email webhook endpoints for Gmail push notifications via Pub/Sub."""

import base64
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.domain.services.email_service import EmailService
from app.infrastructure.cloud_tasks import CloudTasksClient
from app.infrastructure.pubsub import GmailPushNotification, verify_pubsub_token
from app.persistence.database import get_db
from app.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


class PubSubMessage(BaseModel):
    """Pub/Sub push notification message structure."""
    
    data: str  # Base64-encoded message data
    messageId: str
    publishTime: str | None = None
    attributes: dict[str, str] | None = None


class PubSubPushRequest(BaseModel):
    """Pub/Sub push notification request body."""
    
    message: PubSubMessage
    subscription: str


@router.post("/pubsub")
async def gmail_pubsub_webhook(
    request: Request,
    push_request: PubSubPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Handle Gmail push notification from Pub/Sub.
    
    This endpoint:
    - Receives push notification from Google Cloud Pub/Sub
    - Verifies authorization (optional but recommended)
    - Parses Gmail notification data
    - Queues notification for async processing via Cloud Tasks
    - Returns immediate 200 ACK
    
    Gmail sends notifications when mailbox changes occur (new emails, etc.)
    The notification contains the email address and history ID.
    
    Args:
        request: FastAPI request
        push_request: Pub/Sub push notification body
        db: Database session
        
    Returns:
        Simple acknowledgment response
    """
    try:
        # Verify Pub/Sub authorization token (optional)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if not verify_pubsub_token(token):
                logger.warning("Invalid Pub/Sub authorization token")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid authorization",
                )
        
        # Parse Gmail push notification
        try:
            notification = GmailPushNotification.from_pubsub_message(
                push_request.message.data
            )
        except ValueError as e:
            logger.error(f"Failed to parse Gmail notification: {e}")
            # Return 200 to prevent Pub/Sub retries for malformed messages
            return {"status": "ignored", "reason": "invalid_format"}
        
        logger.info(
            f"Gmail notification received: email={notification.email_address}, "
            f"history_id={notification.history_id}, message_id={push_request.message.messageId}"
        )
        
        # Queue for async processing via Cloud Tasks
        if settings.cloud_tasks_email_worker_url:
            cloud_tasks = CloudTasksClient()
            await cloud_tasks.create_task_async(
                payload={
                    "email_address": notification.email_address,
                    "history_id": notification.history_id,
                },
                url=f"{settings.cloud_tasks_email_worker_url}/process-email-notification",
            )
            logger.info(f"Email notification queued for {notification.email_address}")
        else:
            # Fallback: process synchronously (not recommended for production)
            logger.warning("Cloud Tasks email worker URL not configured, processing synchronously")
            email_service = EmailService(db)
            await email_service.process_gmail_notification(
                email_address=notification.email_address,
                history_id=notification.history_id,
            )
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {e}", exc_info=True)
        # Return 200 to avoid Pub/Sub retries for processing errors
        # Cloud Tasks will handle retries for queued tasks
        return {"status": "error", "message": "Processing failed"}


@router.post("/pubsub/test")
async def test_gmail_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Test endpoint for Gmail webhook (development only).
    
    Simulates a Gmail push notification for testing.
    
    Args:
        request: FastAPI request
        db: Database session
        
    Returns:
        Test result
    """
    if settings.environment not in ("development", "staging"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test endpoint only available in development",
        )
    
    try:
        body = await request.json()
        email_address = body.get("email_address", "test@example.com")
        history_id = body.get("history_id", "12345")
        
        # Process synchronously for testing
        email_service = EmailService(db)
        results = await email_service.process_gmail_notification(
            email_address=email_address,
            history_id=history_id,
        )
        
        return {
            "status": "ok",
            "messages_processed": len(results),
            "results": [
                {
                    "thread_id": r.thread_id,
                    "message_id": r.message_id,
                    "escalated": r.requires_escalation,
                }
                for r in results
            ],
        }
        
    except Exception as e:
        logger.error(f"Error in test webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/health")
async def email_webhook_health() -> dict[str, str]:
    """Health check for email webhook endpoint.
    
    Used by GCP to verify the endpoint is accessible.
    
    Returns:
        Health status
    """
    return {"status": "healthy", "service": "email-webhooks"}

