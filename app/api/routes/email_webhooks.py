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
        print(f"[EMAIL_WEBHOOK] Received pubsub push request", flush=True)
        
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
            print(f"[EMAIL_WEBHOOK] Parsed notification: email={notification.email_address}, history_id={notification.history_id}", flush=True)
        except ValueError as e:
            print(f"[EMAIL_WEBHOOK] Failed to parse notification: {e}", flush=True)
            logger.error(f"Failed to parse Gmail notification: {e}")
            # Return 200 to prevent Pub/Sub retries for malformed messages
            return {"status": "ignored", "reason": "invalid_format"}
        
        logger.info(
            f"Gmail notification received: email={notification.email_address}, "
            f"history_id={notification.history_id}, message_id={push_request.message.messageId}"
        )
        
        # Queue for async processing via Cloud Tasks
        if settings.cloud_tasks_email_worker_url:
            print(f"[EMAIL_WEBHOOK] Using Cloud Tasks worker: {settings.cloud_tasks_email_worker_url}", flush=True)
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
            print(f"[EMAIL_WEBHOOK] Processing synchronously (no Cloud Tasks URL configured)", flush=True)
            logger.warning("Cloud Tasks email worker URL not configured, processing synchronously")
            email_service = EmailService(db)
            results = await email_service.process_gmail_notification(
                email_address=notification.email_address,
                history_id=notification.history_id,
            )
            print(f"[EMAIL_WEBHOOK] Processed {len(results)} messages", flush=True)
            logger.info(f"Email processed synchronously: {len(results)} messages")
        
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


@router.post("/outlook/webhook", response_model=None)
async def outlook_change_notification(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Handle Microsoft Graph change notifications for Outlook mail.

    Handles two types of requests:
    1. Subscription validation: Microsoft sends ?validationToken=... that must be echoed as text/plain
    2. Change notifications: POST with JSON body containing changed resources
    """
    # Step 1: Handle subscription validation handshake
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("[OUTLOOK_WEBHOOK] Subscription validation request received")
        return Response(content=validation_token, media_type="text/plain")

    try:
        body = await request.json()
        notifications = body.get("value", [])
        logger.info(f"[OUTLOOK_WEBHOOK] Received {len(notifications)} change notification(s)")

        from app.persistence.repositories.email_repository import TenantEmailConfigRepository

        for notification in notifications:
            change_type = notification.get("changeType")
            if change_type != "created":
                continue

            subscription_id = notification.get("subscriptionId")
            client_state = notification.get("clientState")
            resource = notification.get("resource", "")

            # Extract message ID from resource path
            # Format: "Users/{user-id}/Messages/{message-id}" or "me/mailFolders('Inbox')/messages/{id}"
            message_id = resource.split("/")[-1] if resource else None

            if not subscription_id or not message_id:
                logger.warning(f"[OUTLOOK_WEBHOOK] Missing subscription_id or message_id in notification")
                continue

            # Verify client_state against stored secret
            config_repo = TenantEmailConfigRepository(db)
            config = await config_repo.get_by_subscription_id(subscription_id)
            if not config:
                logger.warning(f"[OUTLOOK_WEBHOOK] Unknown subscription_id: {subscription_id}")
                continue

            if config.outlook_client_state and config.outlook_client_state != client_state:
                logger.warning(f"[OUTLOOK_WEBHOOK] Client state mismatch for tenant {config.tenant_id}")
                continue

            # Queue for async processing via Cloud Tasks
            if settings.cloud_tasks_email_worker_url:
                cloud_tasks = CloudTasksClient()
                await cloud_tasks.create_task_async(
                    payload={
                        "subscription_id": subscription_id,
                        "message_id": message_id,
                        "tenant_id": config.tenant_id,
                    },
                    url=f"{settings.cloud_tasks_email_worker_url}/process-outlook-notification",
                )
                logger.info(f"[OUTLOOK_WEBHOOK] Queued notification for tenant {config.tenant_id}")
            else:
                # Fallback: process synchronously
                logger.warning("[OUTLOOK_WEBHOOK] No Cloud Tasks URL, processing synchronously")
                email_service = EmailService(db)
                await email_service.process_outlook_notification(
                    tenant_id=config.tenant_id,
                    message_id=message_id,
                )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"[OUTLOOK_WEBHOOK] Error processing notification: {e}", exc_info=True)
        # Return 202 to prevent Microsoft retries for processing errors
        return {"status": "accepted"}


@router.get("/health")
async def email_webhook_health() -> dict[str, str]:
    """Health check for email webhook endpoint.
    
    Used by GCP to verify the endpoint is accessible.
    
    Returns:
        Health status
    """
    return {"status": "healthy", "service": "email-webhooks"}
