"""Tenant-facing email endpoints for Gmail OAuth and settings."""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant
from app.infrastructure.gmail_client import GmailAuthError, GmailClient
from app.infrastructure.pubsub import get_gmail_pubsub_topic
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.email_repository import (
    EmailConversationRepository,
    TenantEmailConfigRepository,
)
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models

class EmailSettingsResponse(BaseModel):
    """Email settings visible to tenant."""
    is_enabled: bool
    gmail_email: str | None  # Connected Gmail address
    is_connected: bool  # Whether Gmail is connected
    business_hours_enabled: bool
    auto_reply_outside_hours: bool
    auto_reply_message: str | None
    response_signature: str | None
    max_thread_depth: int
    escalation_rules: dict | None
    watch_active: bool  # Whether Gmail watch is active
    lead_capture_subject_prefixes: list[str] | None  # Email subject prefixes that trigger lead creation
    # SendGrid Inbound Parse settings
    sendgrid_enabled: bool = False
    sendgrid_parse_address: str | None = None
    email_ingestion_method: str = "gmail"  # 'gmail' or 'sendgrid'


class SendGridSetupResponse(BaseModel):
    """Response from SendGrid setup."""
    parse_address: str
    webhook_secret: str
    webhook_url: str
    gmail_forwarding_instructions: str


class UpdateEmailSettingsRequest(BaseModel):
    """Tenant-editable email settings."""
    is_enabled: bool = True
    business_hours_enabled: bool = False
    auto_reply_outside_hours: bool = True
    auto_reply_message: str | None = None
    response_signature: str | None = None
    max_thread_depth: int = 10
    escalation_rules: dict | None = None
    lead_capture_subject_prefixes: list[str] | None = None  # Email subject prefixes that trigger lead creation


class OAuthStartResponse(BaseModel):
    """Response from OAuth start."""
    authorization_url: str
    state: str


class EmailConversationSummary(BaseModel):
    """Summary of an email conversation."""
    id: int
    gmail_thread_id: str
    subject: str | None
    from_email: str
    status: str
    message_count: int
    last_response_at: str | None
    created_at: str


# Endpoints

@router.get("/settings", response_model=EmailSettingsResponse)
async def get_email_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailSettingsResponse:
    """Get email settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)
    
    from app.persistence.models.tenant_email_config import DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    
    if not config:
        # Return defaults if no config exists
        return EmailSettingsResponse(
            is_enabled=False,
            gmail_email=None,
            is_connected=False,
            business_hours_enabled=False,
            auto_reply_outside_hours=True,
            auto_reply_message=None,
            response_signature=None,
            max_thread_depth=10,
            escalation_rules=None,
            watch_active=False,
            lead_capture_subject_prefixes=DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES,
            sendgrid_enabled=False,
            sendgrid_parse_address=None,
            email_ingestion_method="gmail",
        )
    
    # Check if watch is active (use utcnow() for naive datetime comparison)
    from datetime import datetime
    watch_active = False
    if config.watch_expiration:
        watch_active = config.watch_expiration > datetime.utcnow()
    
    # Get lead capture prefixes, fall back to defaults
    prefixes = config.lead_capture_subject_prefixes
    if prefixes is None:
        prefixes = DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    
    return EmailSettingsResponse(
        is_enabled=config.is_enabled,
        gmail_email=config.gmail_email,
        is_connected=bool(config.gmail_refresh_token),
        business_hours_enabled=config.business_hours_enabled,
        auto_reply_outside_hours=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        response_signature=config.response_signature,
        max_thread_depth=config.max_thread_depth or 10,
        escalation_rules=config.escalation_rules,
        watch_active=watch_active,
        lead_capture_subject_prefixes=prefixes,
        sendgrid_enabled=config.sendgrid_enabled,
        sendgrid_parse_address=config.sendgrid_parse_address,
        email_ingestion_method=config.email_ingestion_method or "gmail",
    )


@router.put("/settings", response_model=EmailSettingsResponse)
async def update_email_settings(
    settings_data: UpdateEmailSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailSettingsResponse:
    """Update email settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)
    
    from app.persistence.models.tenant_email_config import DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    
    if not config:
        # Create new config
        config = await config_repo.create_or_update(
            tenant_id=tenant_id,
            is_enabled=False,  # Can't enable without Gmail connected
            business_hours_enabled=settings_data.business_hours_enabled,
            auto_reply_outside_hours=settings_data.auto_reply_outside_hours,
            auto_reply_message=settings_data.auto_reply_message,
            response_signature=settings_data.response_signature,
            max_thread_depth=settings_data.max_thread_depth,
            escalation_rules=settings_data.escalation_rules,
            lead_capture_subject_prefixes=settings_data.lead_capture_subject_prefixes,
        )
    else:
        # Update existing - only allow enabling if Gmail is connected
        if settings_data.is_enabled and not config.gmail_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot enable email without connecting Gmail. Please connect your Gmail account first.",
            )
        
        config = await config_repo.create_or_update(
            tenant_id=tenant_id,
            is_enabled=settings_data.is_enabled,
            business_hours_enabled=settings_data.business_hours_enabled,
            auto_reply_outside_hours=settings_data.auto_reply_outside_hours,
            auto_reply_message=settings_data.auto_reply_message,
            response_signature=settings_data.response_signature,
            max_thread_depth=settings_data.max_thread_depth,
            escalation_rules=settings_data.escalation_rules,
            lead_capture_subject_prefixes=settings_data.lead_capture_subject_prefixes,
        )
    
    from datetime import datetime
    watch_active = False
    if config.watch_expiration:
        watch_active = config.watch_expiration > datetime.utcnow()
    
    # Get lead capture prefixes, fall back to defaults
    prefixes = config.lead_capture_subject_prefixes
    if prefixes is None:
        prefixes = DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    
    return EmailSettingsResponse(
        is_enabled=config.is_enabled,
        gmail_email=config.gmail_email,
        is_connected=bool(config.gmail_refresh_token),
        business_hours_enabled=config.business_hours_enabled,
        auto_reply_outside_hours=config.auto_reply_outside_hours,
        auto_reply_message=config.auto_reply_message,
        response_signature=config.response_signature,
        max_thread_depth=config.max_thread_depth or 10,
        escalation_rules=config.escalation_rules,
        watch_active=watch_active,
        lead_capture_subject_prefixes=prefixes,
        sendgrid_enabled=config.sendgrid_enabled,
        sendgrid_parse_address=config.sendgrid_parse_address,
        email_ingestion_method=config.email_ingestion_method or "gmail",
    )


@router.post("/oauth/start", response_model=OAuthStartResponse)
async def start_oauth_flow(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OAuthStartResponse:
    """Start Gmail OAuth flow.
    
    Returns an authorization URL to redirect the user to Google's consent page.
    The state parameter should be passed back to verify the callback.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail integration not configured. Contact support.",
        )
    
    # Generate state token for CSRF protection
    # Include tenant_id in state for callback verification
    state = f"{tenant_id}:{secrets.token_urlsafe(32)}"
    
    # Get redirect URI
    redirect_uri = settings.gmail_oauth_redirect_uri
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail OAuth redirect URI not configured.",
        )
    
    try:
        authorization_url, returned_state = GmailClient.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
        )
        
        # Store state in session/cache for verification (simplified - in production use Redis)
        # For now, we'll verify using the tenant_id embedded in state
        
        return OAuthStartResponse(
            authorization_url=authorization_url,
            state=state,
        )
        
    except GmailAuthError as e:
        logger.error(f"OAuth start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start OAuth flow: {str(e)}",
        )


@router.get("/oauth/callback")
async def oauth_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Handle Gmail OAuth callback.
    
    This endpoint is called by Google after user consent.
    It exchanges the code for tokens and stores them.
    """
    base_url = settings.frontend_url or "https://chattercheatah-900139201687.us-central1.run.app"

    # Handle OAuth error from Google
    if error:
        logger.error(f"OAuth error from Google: {error}")
        frontend_url = f"{base_url}/email?error=oauth_error&message={error}"
        return RedirectResponse(url=frontend_url, status_code=302)
    
    # Check for missing required parameters
    if not code or not state:
        logger.error(f"OAuth callback missing required parameters: code={code is not None}, state={state is not None}")
        frontend_url = f"{base_url}/email?error=missing_parameters&message=OAuth callback missing code or state. Please check redirect URI configuration in Google Cloud Console."
        return RedirectResponse(url=frontend_url, status_code=302)
    
    # Parse tenant_id from state
    try:
        parts = state.split(":", 1)
        tenant_id = int(parts[0])
    except (ValueError, IndexError):
        logger.error(f"Invalid OAuth state: {state}")
        frontend_url = f"{base_url}/email?error=invalid_state&message=Invalid OAuth state parameter"
        return RedirectResponse(url=frontend_url, status_code=302)
    
    redirect_uri = settings.gmail_oauth_redirect_uri
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail OAuth redirect URI not configured.",
        )
    
    try:
        # Exchange code for tokens
        token_data = GmailClient.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
        )

        # Store tokens in config and enable email processing
        config_repo = TenantEmailConfigRepository(db)
        config = await config_repo.create_or_update(
            tenant_id=tenant_id,
            gmail_email=token_data["email"],
            gmail_refresh_token=token_data["refresh_token"],
            gmail_access_token=token_data["access_token"],
            gmail_token_expires_at=token_data["token_expires_at"],
            is_enabled=True,  # Enable email processing when connecting Gmail
        )
        
        # Setup Gmail watch for push notifications
        topic = get_gmail_pubsub_topic()
        if topic:
            try:
                gmail_client = GmailClient(
                    refresh_token=token_data["refresh_token"],
                    access_token=token_data["access_token"],
                    token_expires_at=token_data["token_expires_at"],
                )
                watch_result = gmail_client.watch_mailbox(topic)
                
                # Update config with watch info
                await config_repo.create_or_update(
                    tenant_id=tenant_id,
                    watch_expiration=watch_result.get("expiration"),
                    last_history_id=watch_result.get("history_id"),
                )
                
            except Exception as e:
                logger.error(f"Failed to setup Gmail watch: {e}")
                # Continue even if watch setup fails - can be retried
        
        logger.info(f"Gmail connected for tenant {tenant_id}: {token_data['email']}")
        
        # Redirect to frontend settings page
        base_url = settings.frontend_url or "https://chattercheatah-900139201687.us-central1.run.app"
        frontend_url = f"{base_url}/settings/email?connected=true&email={token_data['email']}"
        return RedirectResponse(url=frontend_url, status_code=302)
        
    except GmailAuthError as e:
        logger.error(f"OAuth callback failed: {e}")
        # Redirect to frontend with error
        base_url = settings.frontend_url or "https://chattercheatah-900139201687.us-central1.run.app"
        frontend_url = f"{base_url}/settings/email?error={str(e)}"
        return RedirectResponse(url=frontend_url, status_code=302)


@router.delete("/disconnect")
async def disconnect_gmail(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Disconnect Gmail account from tenant.
    
    Removes OAuth tokens and disables email processing.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)
    
    if not config:
        return {"status": "ok", "message": "No Gmail connected"}
    
    # Stop Gmail watch if active
    if config.gmail_refresh_token:
        try:
            gmail_client = GmailClient(
                refresh_token=config.gmail_refresh_token,
                access_token=config.gmail_access_token,
                token_expires_at=config.gmail_token_expires_at,
            )
            gmail_client.stop_watch()
        except Exception as e:
            logger.warning(f"Failed to stop Gmail watch: {e}")
    
    # Clear tokens and disable
    await config_repo.create_or_update(
        tenant_id=tenant_id,
        is_enabled=False,
        gmail_email=None,
        gmail_refresh_token=None,
        gmail_access_token=None,
        gmail_token_expires_at=None,
        watch_expiration=None,
        last_history_id=None,
    )
    
    logger.info(f"Gmail disconnected for tenant {tenant_id}")
    
    return {"status": "ok", "message": "Gmail disconnected successfully"}


@router.post("/refresh-watch")
async def refresh_gmail_watch(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Manually refresh Gmail watch for push notifications.
    
    Gmail watches expire after 7 days. This refreshes the watch.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)
    
    if not config or not config.gmail_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail not connected",
        )
    
    topic = get_gmail_pubsub_topic()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail Pub/Sub topic not configured",
        )
    
    try:
        gmail_client = GmailClient(
            refresh_token=config.gmail_refresh_token,
            access_token=config.gmail_access_token,
            token_expires_at=config.gmail_token_expires_at,
        )

        logger.info(f"[GMAIL_WATCH] Setting up watch for tenant {tenant_id}, topic={topic}")
        watch_result = gmail_client.watch_mailbox(topic)
        logger.info(f"[GMAIL_WATCH] Watch result: history_id={watch_result.get('history_id')}, expiration={watch_result.get('expiration')}")

        # Update config
        await config_repo.create_or_update(
            tenant_id=tenant_id,
            watch_expiration=watch_result.get("expiration"),
            last_history_id=watch_result.get("history_id"),
        )

        # Update tokens if refreshed
        token_info = gmail_client.get_token_info()
        await config_repo.update_tokens(
            tenant_id=tenant_id,
            access_token=token_info["access_token"],
            token_expires_at=token_info["token_expires_at"],
        )

        logger.info(f"[GMAIL_WATCH] Watch refreshed successfully for tenant {tenant_id}")
        return {"status": "ok", "message": "Gmail watch refreshed", "history_id": watch_result.get("history_id")}

    except Exception as e:
        logger.error(f"Failed to refresh Gmail watch: {e}")
        error_str = str(e)

        # Provide helpful error message for token expiration
        # Use 400 instead of 401 to avoid frontend interpreting as auth failure and logging user out
        if "invalid_grant" in error_str or "Token has been expired or revoked" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gmail authorization has expired or been revoked. Please disconnect and reconnect your Gmail account.",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh watch: {error_str}",
        )


@router.get("/conversations", response_model=list[EmailConversationSummary])
async def list_email_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = None,
    contact_id: int | None = None,
    limit: int = 50,
) -> list[EmailConversationSummary]:
    """List email conversations for current tenant.
    
    Optionally filter by contact_id to get conversations for a specific contact.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    conv_repo = EmailConversationRepository(db)
    
    if contact_id:
        # Filter by contact
        conversations = await conv_repo.list_by_contact(
            tenant_id=tenant_id,
            contact_id=contact_id,
            limit=limit,
        )
    else:
        conversations = await conv_repo.list_by_tenant(
            tenant_id=tenant_id,
            status=status_filter,
            limit=limit,
        )
    
    return [
        EmailConversationSummary(
            id=conv.id,
            gmail_thread_id=conv.gmail_thread_id,
            subject=conv.subject,
            from_email=conv.from_email,
            status=conv.status,
            message_count=conv.message_count,
            last_response_at=conv.last_response_at.isoformat() if conv.last_response_at else None,
            created_at=conv.created_at.isoformat(),
        )
        for conv in conversations
    ]


# SendGrid Inbound Parse Configuration Endpoints

import hashlib


@router.post("/sendgrid/setup", response_model=SendGridSetupResponse)
async def setup_sendgrid_inbound(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SendGridSetupResponse:
    """Generate SendGrid Inbound Parse address and webhook secret for tenant.

    Creates a unique parse address for this tenant and generates a webhook secret.
    Returns setup instructions for configuring Gmail forwarding.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    # Check if already configured
    if config and config.sendgrid_parse_address:
        # Return existing configuration
        return SendGridSetupResponse(
            parse_address=config.sendgrid_parse_address,
            webhook_secret=config.sendgrid_webhook_secret or "",
            webhook_url=f"{settings.api_base_url}/api/v1/email/sendgrid/inbound",
            gmail_forwarding_instructions=_get_gmail_forwarding_instructions(
                config.sendgrid_parse_address,
                config.lead_capture_subject_prefixes,
            ),
        )

    # Generate unique parse address
    tenant_hash = hashlib.sha256(f"{tenant_id}-{secrets.token_hex(8)}".encode()).hexdigest()[:12]
    parse_domain = settings.sendgrid_inbound_parse_domain or "parse.yourdomain.com"
    parse_address = f"leads-{tenant_hash}@{parse_domain}"

    # Generate webhook secret
    webhook_secret = secrets.token_urlsafe(32)

    # Get existing prefixes or defaults
    from app.persistence.models.tenant_email_config import DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    prefixes = DEFAULT_LEAD_CAPTURE_SUBJECT_PREFIXES
    if config and config.lead_capture_subject_prefixes:
        prefixes = config.lead_capture_subject_prefixes

    # Save configuration
    await config_repo.create_or_update(
        tenant_id=tenant_id,
        sendgrid_parse_address=parse_address,
        sendgrid_webhook_secret=webhook_secret,
    )

    logger.info(f"SendGrid Inbound Parse configured for tenant {tenant_id}: {parse_address}")

    return SendGridSetupResponse(
        parse_address=parse_address,
        webhook_secret=webhook_secret,
        webhook_url=f"{settings.api_base_url}/api/v1/email/sendgrid/inbound",
        gmail_forwarding_instructions=_get_gmail_forwarding_instructions(parse_address, prefixes),
    )


@router.put("/sendgrid/enable")
async def enable_sendgrid_inbound(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    enabled: bool = True,
) -> dict[str, bool | str]:
    """Enable or disable SendGrid Inbound Parse for tenant.

    When enabled, sets the email_ingestion_method to 'sendgrid'.
    When disabled, reverts to 'gmail'.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantEmailConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if enabled and (not config or not config.sendgrid_parse_address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SendGrid not configured. Call /sendgrid/setup first.",
        )

    # Update configuration
    await config_repo.create_or_update(
        tenant_id=tenant_id,
        sendgrid_enabled=enabled,
        email_ingestion_method="sendgrid" if enabled else "gmail",
    )

    logger.info(f"SendGrid Inbound Parse {'enabled' if enabled else 'disabled'} for tenant {tenant_id}")

    return {
        "sendgrid_enabled": enabled,
        "email_ingestion_method": "sendgrid" if enabled else "gmail",
    }


@router.delete("/sendgrid/disconnect")
async def disconnect_sendgrid(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Remove SendGrid Inbound Parse configuration for tenant.

    Clears parse address and webhook secret, reverts to Gmail ingestion.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    config_repo = TenantEmailConfigRepository(db)

    # Clear SendGrid configuration
    await config_repo.create_or_update(
        tenant_id=tenant_id,
        sendgrid_enabled=False,
        sendgrid_parse_address=None,
        sendgrid_webhook_secret=None,
        email_ingestion_method="gmail",
    )

    logger.info(f"SendGrid Inbound Parse disconnected for tenant {tenant_id}")

    return {"status": "ok", "message": "SendGrid configuration removed"}


def _get_gmail_forwarding_instructions(parse_address: str, prefixes: list[str] | None) -> str:
    """Generate Gmail forwarding setup instructions."""
    prefix_list = prefixes or ["Email Capture from Booking Page", "Get In Touch Form Submission"]
    prefix_str = ", ".join([f'"{p}"' for p in prefix_list])

    return f"""Gmail Forwarding Setup Instructions:

1. Open Gmail Settings (gear icon) > See all settings > Filters and Blocked Addresses

2. Click "Create a new filter"

3. In the "Subject" field, enter keywords to match your lead emails:
   - Current configured prefixes: {prefix_str}
   - Example: subject:(Email Capture OR Get In Touch)

4. Click "Create filter"

5. Check "Forward it to:" and add: {parse_address}
   - If this is your first forwarding address, Gmail will send a confirmation email
   - Check your SendGrid Inbound Parse logs for the confirmation link

6. Optionally check "Apply the label" to organize forwarded emails

7. Click "Create filter"

Note: Gmail will send a confirmation email to verify the forwarding address.
You must click the confirmation link before forwarding will work."""

