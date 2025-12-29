"""Telnyx AI Assistant webhooks for dynamic variables."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.prompt_service import PromptService
from app.persistence.database import get_db
from app.persistence.models.tenant_sms_config import TenantSmsConfig

logger = logging.getLogger(__name__)

router = APIRouter()


class TelnyxDynamicVarsRequest(BaseModel):
    """Request from Telnyx AI Assistant for dynamic variables.

    Telnyx sends call metadata when requesting dynamic variables.
    """

    call_control_id: str | None = None
    to: str | None = None  # The Telnyx number being called
    from_: str | None = None  # The caller's number
    direction: str | None = None  # "inbound" or "outbound"

    class Config:
        populate_by_name = True
        # Allow 'from' as alias since it's a Python keyword
        fields = {"from_": {"alias": "from"}}


@router.post("/dynamic-variables")
async def get_dynamic_variables(
    request: TelnyxDynamicVarsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Return dynamic variables for Telnyx AI Assistant.

    Telnyx calls this webhook to fetch variables like the system prompt (X).
    The tenant is identified by the Telnyx phone number being called.

    Args:
        request: Call metadata from Telnyx
        db: Database session

    Returns:
        Dictionary with dynamic variables, including X (the composed prompt)
    """
    to_number = request.to
    from_number = request.from_

    logger.info(
        f"Telnyx dynamic variables request",
        extra={
            "to": to_number,
            "from": from_number,
            "call_control_id": request.call_control_id,
            "direction": request.direction,
        },
    )

    if not to_number:
        logger.warning("No 'to' number in Telnyx request")
        return {"X": _get_fallback_prompt()}

    # Look up tenant by the Telnyx phone number being called
    # Normalize phone number (remove any formatting)
    normalized_to = _normalize_phone(to_number)

    stmt = select(TenantSmsConfig).where(
        TenantSmsConfig.telnyx_phone_number == normalized_to
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    # Also try without normalization if not found
    if not config:
        stmt = select(TenantSmsConfig).where(
            TenantSmsConfig.telnyx_phone_number == to_number
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

    if not config:
        logger.warning(f"No tenant found for Telnyx number: {to_number}")
        return {"X": _get_fallback_prompt()}

    tenant_id = config.tenant_id

    # Compose the voice prompt for this tenant
    prompt_service = PromptService(db)
    composed_prompt = await prompt_service.compose_prompt_voice(tenant_id)

    if not composed_prompt:
        logger.warning(f"No prompt configured for tenant {tenant_id}")
        return {"X": _get_fallback_prompt()}

    logger.info(
        f"Returning dynamic variables for tenant",
        extra={
            "tenant_id": tenant_id,
            "to": to_number,
            "prompt_length": len(composed_prompt),
        },
    )

    return {"X": composed_prompt}


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format.

    Args:
        phone: Phone number in various formats

    Returns:
        Normalized phone number
    """
    # Remove spaces, dashes, parentheses
    normalized = "".join(c for c in phone if c.isdigit() or c == "+")

    # Ensure starts with +
    if not normalized.startswith("+"):
        # Assume US number if no country code
        if len(normalized) == 10:
            normalized = "+1" + normalized
        elif len(normalized) == 11 and normalized.startswith("1"):
            normalized = "+" + normalized

    return normalized


def _get_fallback_prompt() -> str:
    """Return a generic fallback prompt when tenant cannot be identified."""
    return (
        "You are a helpful assistant. "
        "Greet the caller warmly and ask how you can help them today. "
        "Be friendly and conversational. "
        "If you cannot answer a question, offer to take their information "
        "so someone can follow up with them."
    )
