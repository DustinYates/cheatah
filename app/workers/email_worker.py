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
                logger.error(f"Failed to refresh watch for tenant {config.tenant_id}: {e}")
                failed += 1
        
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
