"""Public chat endpoint for web chat widget."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.domain.services.chat_service import ChatService
from app.persistence.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class ChatRequest(BaseModel):
    """Chat request from web widget."""

    tenant_id: int
    session_id: str | None = None  # If None, creates new conversation
    message: str
    user_name: str | None = None  # Optional, for lead capture
    user_email: str | None = None  # Optional, for lead capture
    user_phone: str | None = None  # Optional, for lead capture


class ChatResponse(BaseModel):
    """Chat response to web widget."""

    session_id: str
    response: str
    requires_contact_info: bool = False  # True if we need name/email/phone
    conversation_complete: bool = False  # True if max turns reached or timeout
    lead_captured: bool = False  # True if lead was captured in this turn


@router.post("", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    """Public chat endpoint for web widget.
    
    This endpoint:
    - Accepts tenant_id in request (no auth required)
    - Creates or retrieves conversation by session_id
    - Assembles prompt from tenant settings
    - Calls LLM with conversation history
    - Handles lead capture logic
    - Enforces guardrails (max turns, timeout)
    """
    start_time = time.time()
    
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
        
        # Log metrics (basic logging)
        import logging
        logger = logging.getLogger(__name__)
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
        import logging
        logger = logging.getLogger(__name__)
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

