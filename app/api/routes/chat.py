"""Public chat endpoint for web chat widget."""

import hmac
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.chat_service import ChatService
from app.infrastructure.rate_limiter import rate_limit
from app.persistence.database import get_db
from app.persistence.models.tenant_widget_config import TenantWidgetConfig
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Chat request from web widget."""

    tenant_id: int
    session_id: str | None = None  # If None, creates new conversation
    message: str
    user_name: str | None = None  # Optional, for lead capture
    user_email: str | None = None  # Optional, for lead capture
    user_phone: str | None = None  # Optional, for lead capture
    api_key: str | None = None  # Widget API key for authentication


class ChatResponse(BaseModel):
    """Chat response to web widget."""

    session_id: str
    response: str
    requires_contact_info: bool = False  # True if we need name/email/phone
    conversation_complete: bool = False  # True if max turns reached or timeout
    lead_captured: bool = False  # True if lead was captured in this turn
    escalation_requested: bool = False  # True if customer requested to speak with human
    escalation_id: int | None = None  # Escalation record ID if escalation was triggered
    scheduling: dict | None = None  # Scheduling data {mode, slots[], booking_link, booking_confirmed}
    handoff_initiated: bool = False  # True if chat-to-SMS handoff was triggered
    handoff_phone: str | None = None  # Phone number handoff was sent to


async def _validate_widget_api_key(
    db: AsyncSession,
    tenant_id: int,
    api_key: str | None,
) -> bool:
    """Validate widget API key for tenant.

    Args:
        db: Database session
        tenant_id: Tenant ID
        api_key: API key from request

    Returns:
        True if valid, False otherwise
    """
    stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        # No config exists - tenant may not exist
        return False

    if not config.widget_api_key:
        # No API key configured for tenant - allow request
        return True

    if not api_key:
        # No API key provided in request - allow for backwards compatibility
        # This supports existing widget embeds that don't include apiKey
        logger.info(f"Chat request without API key for tenant {tenant_id} (allowed)")
        return True

    # API key provided - validate it (constant-time comparison for security)
    return hmac.compare_digest(config.widget_api_key, api_key)


@router.post("", response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_widget_api_key: Annotated[str | None, Header()] = None,
    _rate_limit: None = Depends(rate_limit("chat")),
) -> ChatResponse:
    """Public chat endpoint for web chat widget.

    This endpoint requires a valid widget API key for authentication.
    The API key can be provided either:
    - In the request body as 'api_key'
    - In the header as 'X-Widget-Api-Key'

    This endpoint:
    - Validates widget API key
    - Creates or retrieves conversation by session_id
    - Assembles prompt from tenant settings
    - Calls LLM with conversation history
    - Handles lead capture logic
    - Enforces guardrails (max turns, timeout)
    """
    start_time = time.time()

    # Get API key from header or body (header takes precedence)
    api_key = x_widget_api_key or chat_request.api_key

    # Validate API key
    is_valid = await _validate_widget_api_key(db, chat_request.tenant_id, api_key)

    if not is_valid:
        if settings.environment == "production":
            logger.warning(f"Invalid widget API key for tenant {chat_request.tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing widget API key",
            )
        else:
            # In development, log warning but allow request
            if not api_key:
                logger.warning(
                    f"No widget API key provided for tenant {chat_request.tenant_id} "
                    "(allowed in development mode)"
                )

    try:
        chat_service = ChatService(db)

        # Process chat request
        result = await chat_service.process_chat(
            tenant_id=chat_request.tenant_id,
            session_id=chat_request.session_id,
            user_message=chat_request.message,
            user_name=chat_request.user_name,
            user_email=chat_request.user_email,
            user_phone=chat_request.user_phone,
        )
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Log metrics
        logger.info(
            f"Chat request processed - tenant_id={chat_request.tenant_id}, "
            f"session_id={result.session_id}, latency_ms={latency_ms:.2f}, "
            f"llm_latency_ms={result.llm_latency_ms:.2f}, turn_count={result.turn_count}, "
            f"lead_captured={result.lead_captured}"
        )
        
        return ChatResponse(
            session_id=result.session_id,
            response=result.response,
            requires_contact_info=result.requires_contact_info,
            conversation_complete=result.conversation_complete,
            lead_captured=result.lead_captured,
            escalation_requested=result.escalation_requested,
            escalation_id=result.escalation_id,
            scheduling=result.scheduling,
            handoff_initiated=result.handoff_initiated,
            handoff_phone=result.handoff_phone,
        )
        
    except ValueError as e:
        error_message = str(e)
        # Provide user-friendly message for prompt not configured
        if "No prompt configured" in error_message:
            error_message = "Chatbot is not configured. Please contact support."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )
    except Exception as e:
        error_latency = (time.time() - start_time) * 1000
        logger.error(
            f"Chat request failed - tenant_id={chat_request.tenant_id}, "
            f"error={str(e)}, latency_ms={error_latency:.2f}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat service error",
        )

