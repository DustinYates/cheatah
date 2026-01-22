"""Email worker for processing queued email notifications from Cloud Tasks."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.domain.services.email_service import EmailService
from app.infrastructure.gmail_client import GmailClient
from app.persistence.database import get_db
from app.persistence.repositories.email_repository import TenantEmailConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailNotificationPayload(BaseModel):
    """Payload for Gmail push notification processing."""
    
    email_address: str
    history_id: str


class EmailProcessPayload(BaseModel):
    """Payload for direct email processing."""

    tenant_id: int
    from_email: str
    to_email: str
    subject: str
    body: str
    thread_id: str
    message_id: str


class SendGridProcessPayload(BaseModel):
    """Payload for SendGrid Inbound Parse processing."""

    ingestion_log_id: int
    tenant_id: int


@router.post("/process-email-notification")
async def process_email_notification(
    request: Request,
    payload: EmailNotificationPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process Gmail push notification.
    
    This endpoint is called by Cloud Tasks to process Gmail push notifications
    asynchronously. It fetches new messages and processes them.
    
    Args:
        request: FastAPI request
        payload: Gmail notification payload (email_address, history_id)
        db: Database session
        
    Returns:
        Processing result
    """
    try:
        # Validate Cloud Tasks request headers (optional but recommended)
        queue_name = request.headers.get("X-CloudTasks-QueueName")
        task_name = request.headers.get("X-CloudTasks-TaskName")
        
        logger.info(
            f"Processing email notification: email={payload.email_address}, "
            f"history_id={payload.history_id}, queue={queue_name}, task={task_name}"
        )
        
        email_service = EmailService(db)
        results = await email_service.process_gmail_notification(
            email_address=payload.email_address,
            history_id=payload.history_id,
        )
        
        # Summarize results
        processed = len(results)
        escalated = sum(1 for r in results if r.requires_escalation)
        leads_captured = sum(1 for r in results if r.lead_captured)
        
        logger.info(
            f"Email notification processed: email={payload.email_address}, "
            f"messages_processed={processed}, escalated={escalated}, leads={leads_captured}"
        )
        
        return {
            "status": "success",
            "messages_processed": processed,
            "escalated": escalated,
            "leads_captured": leads_captured,
        }
        
    except Exception as e:
        logger.error(f"Error processing email notification: {e}", exc_info=True)
        # Return error so Cloud Tasks can retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email notification processing failed: {str(e)}",
        )


@router.post("/process-email")
async def process_email_task(
    request: Request,
    payload: EmailProcessPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process a single email directly.
    
    This endpoint is an alternative to notification-based processing,
    allowing direct processing of a specific email.
    
    Args:
        request: FastAPI request
        payload: Email processing payload
        db: Database session
        
    Returns:
        Processing result
    """
    try:
        logger.info(
            f"Processing email: tenant_id={payload.tenant_id}, "
            f"from={payload.from_email}, thread_id={payload.thread_id}"
        )
        
        # Get tenant email config for Gmail client
        email_config_repo = TenantEmailConfigRepository(db)
        email_config = await email_config_repo.get_by_tenant_id(payload.tenant_id)
        
        gmail_client = None
        if email_config and email_config.gmail_refresh_token:
            gmail_client = GmailClient(
                refresh_token=email_config.gmail_refresh_token,
                access_token=email_config.gmail_access_token,
                token_expires_at=email_config.gmail_token_expires_at,
            )
        
        email_service = EmailService(db)
        result = await email_service.process_inbound_email(
            tenant_id=payload.tenant_id,
            from_email=payload.from_email,
            to_email=payload.to_email,
            subject=payload.subject,
            body=payload.body,
            thread_id=payload.thread_id,
            message_id=payload.message_id,
            gmail_client=gmail_client,
        )
        
        logger.info(
            f"Email processed: tenant_id={payload.tenant_id}, "
            f"thread_id={payload.thread_id}, message_id={result.message_id}"
        )
        
        return {
            "status": "success",
            "message_id": result.message_id,
            "thread_id": result.thread_id,
            "requires_escalation": result.requires_escalation,
            "escalation_id": result.escalation_id,
            "lead_captured": result.lead_captured,
            "lead_id": result.lead_id,
        }
        
    except Exception as e:
        logger.error(f"Error processing email: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email processing failed: {str(e)}",
        )


@router.post("/refresh-gmail-watch")
async def refresh_gmail_watch(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Refresh Gmail watch for all enabled tenants.
    
    Gmail push notification watches expire after 7 days.
    This endpoint should be called periodically (e.g., daily via Cloud Scheduler)
    to refresh watches for all active email configs.
    
    Args:
        request: FastAPI request
        db: Database session
        
    Returns:
        Summary of refresh operations
    """
    try:
        from app.infrastructure.pubsub import get_gmail_pubsub_topic
        
        email_config_repo = TenantEmailConfigRepository(db)
        configs = await email_config_repo.get_all_enabled()
        
        topic = get_gmail_pubsub_topic()
        if not topic:
            return {
                "status": "error",
                "message": "Gmail Pub/Sub topic not configured",
                "refreshed": 0,
                "failed": 0,
            }
        
        refreshed = 0
        failed = 0
        
        for config in configs:
            try:
                if not config.gmail_refresh_token:
                    continue
                    
                gmail_client = GmailClient(
                    refresh_token=config.gmail_refresh_token,
                    access_token=config.gmail_access_token,
                    token_expires_at=config.gmail_token_expires_at,
                )
                
                watch_result = gmail_client.watch_mailbox(topic)
                
                # Update config with new watch expiration
                config.watch_expiration = watch_result.get("expiration")
                config.last_history_id = watch_result.get("history_id")
                
                # Update tokens if refreshed
                token_info = gmail_client.get_token_info()
                await email_config_repo.update_tokens(
                    tenant_id=config.tenant_id,
                    access_token=token_info["access_token"],
                    token_expires_at=token_info["token_expires_at"],
                )
                
                await db.commit()
                refreshed += 1
                
            except Exception as e:
                error_str = str(e)
                logger.error(f"Failed to refresh watch for tenant {config.tenant_id}: {e}")
                failed += 1

                # Send alert for token revocation/expiration
                if "invalid_grant" in error_str or "Token has been expired or revoked" in error_str:
                    try:
                        from app.infrastructure.notifications import NotificationService
                        from app.persistence.models.notification import NotificationType, NotificationPriority

                        notification_service = NotificationService(db)
                        await notification_service.notify_admins(
                            tenant_id=config.tenant_id,
                            subject="Gmail Connection Expired",
                            message=(
                                f"Your Gmail connection for {config.gmail_email} has expired or been revoked. "
                                f"Please reconnect Gmail in Settings > Email to continue receiving email leads."
                            ),
                            methods=["sms", "in_app"],
                            notification_type=NotificationType.SYSTEM,
                            priority=NotificationPriority.URGENT,
                            action_url="/settings/email",
                            metadata={
                                "gmail_email": config.gmail_email,
                                "alert_type": "gmail_token_expired",
                            },
                        )
                        logger.info(f"Sent Gmail token expiration alert for tenant {config.tenant_id}")
                    except Exception as alert_error:
                        logger.error(f"Failed to send Gmail alert for tenant {config.tenant_id}: {alert_error}")

        logger.info(f"Gmail watch refresh complete: refreshed={refreshed}, failed={failed}")
        
        return {
            "status": "success",
            "refreshed": refreshed,
            "failed": failed,
        }
        
    except Exception as e:
        logger.error(f"Error refreshing Gmail watches: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Watch refresh failed: {str(e)}",
        )


@router.post("/process-sendgrid-email")
async def process_sendgrid_email_task(
    request: Request,
    payload: SendGridProcessPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Process SendGrid Inbound Parse email from Cloud Tasks queue.

    This endpoint is called asynchronously by Cloud Tasks after the
    SendGrid webhook receives and deduplicates an inbound email.

    Args:
        request: FastAPI request
        payload: SendGrid processing payload (ingestion_log_id, tenant_id)
        db: Database session

    Returns:
        Processing result
    """
    from app.api.routes.sendgrid_webhooks import SendGridInboundPayload, _process_sendgrid_email
    from app.persistence.models.email_ingestion_log import IngestionStatus
    from app.persistence.repositories.email_ingestion_repository import EmailIngestionLogRepository

    try:
        # Validate Cloud Tasks request headers
        queue_name = request.headers.get("X-CloudTasks-QueueName")
        task_name = request.headers.get("X-CloudTasks-TaskName")

        logger.info(
            f"Processing SendGrid email: ingestion_log_id={payload.ingestion_log_id}, "
            f"tenant_id={payload.tenant_id}, queue={queue_name}, task={task_name}"
        )

        # Retrieve ingestion log
        ingestion_repo = EmailIngestionLogRepository(db)
        ingestion_log = await ingestion_repo.get_by_id(payload.ingestion_log_id)

        if not ingestion_log:
            logger.error(f"Ingestion log not found: {payload.ingestion_log_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingestion log not found",
            )

        # Skip if already processed or duplicate
        if ingestion_log.status in (IngestionStatus.PROCESSED.value, IngestionStatus.DUPLICATE.value):
            logger.info(f"Ingestion log already processed: status={ingestion_log.status}")
            return {"status": "skipped", "reason": ingestion_log.status}

        # Reconstruct payload from raw_payload
        raw = ingestion_log.raw_payload or {}
        sendgrid_payload = SendGridInboundPayload(
            from_email=raw.get("from", ""),
            to=raw.get("to", ""),
            subject=raw.get("subject", ""),
            text=raw.get("text"),
            html=raw.get("html"),
            headers=raw.get("headers", ""),
            envelope="{}",
            sender_ip=raw.get("sender_ip"),
        )

        # Process the email
        result = await _process_sendgrid_email(db, payload.tenant_id, sendgrid_payload, ingestion_log)

        logger.info(
            f"SendGrid email processed: ingestion_log_id={payload.ingestion_log_id}, "
            f"result={result}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing SendGrid email: {e}", exc_info=True)
        # Return error so Cloud Tasks can retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SendGrid email processing failed: {str(e)}",
        )
