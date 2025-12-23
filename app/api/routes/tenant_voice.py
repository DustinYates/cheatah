"""Tenant voice settings API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user
from app.domain.services.voice_config_service import VoiceConfigData, VoiceConfigService
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_voice_config import (
    DEFAULT_ESCALATION_RULES,
    DEFAULT_NOTIFICATION_METHODS,
)

router = APIRouter()


# Request/Response Models

class EscalationRulesConfig(BaseModel):
    """Escalation rules configuration."""
    caller_asks_human: bool = True
    repeated_confusion: dict = Field(default_factory=lambda: {"enabled": True, "threshold": 3})
    high_value_intent: dict = Field(default_factory=lambda: {"enabled": False, "intents": []})
    low_confidence: dict = Field(default_factory=lambda: {"enabled": False, "threshold": 0.5})


class NotificationRecipient(BaseModel):
    """Notification recipient configuration."""
    type: str  # "user_id" or "email"
    value: str | int


class VoiceSettingsResponse(BaseModel):
    """Response model for voice settings."""
    is_enabled: bool
    handoff_mode: str
    live_transfer_number: str | None
    escalation_rules: dict | None
    default_greeting: str | None
    disclosure_line: str | None
    notification_methods: list[str] | None
    notification_recipients: list[dict] | None
    after_hours_message: str | None


class UpdateVoiceSettingsRequest(BaseModel):
    """Request model for updating voice settings."""
    is_enabled: bool | None = None
    handoff_mode: str | None = Field(
        None,
        pattern="^(live_transfer|take_message|schedule_callback|voicemail)$"
    )
    live_transfer_number: str | None = None
    escalation_rules: dict | None = None
    default_greeting: str | None = None
    disclosure_line: str | None = None
    notification_methods: list[str] | None = None
    notification_recipients: list[dict] | None = None
    after_hours_message: str | None = None


class HandoffConfigResponse(BaseModel):
    """Response model for handoff configuration."""
    mode: str
    transfer_number: str | None
    enabled: bool


class EscalationRulesResponse(BaseModel):
    """Response model for escalation rules."""
    caller_asks_human: bool
    repeated_confusion: dict
    high_value_intent: dict
    low_confidence: dict


class NotificationConfigResponse(BaseModel):
    """Response model for notification configuration."""
    methods: list[str]
    recipients: list[dict]


# Endpoints

@router.get("/settings", response_model=VoiceSettingsResponse)
async def get_voice_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VoiceSettingsResponse:
    """Get voice settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    voice_config_service = VoiceConfigService(db)
    config = await voice_config_service.get_or_create_voice_config(tenant_id)
    
    return VoiceSettingsResponse(
        is_enabled=config.is_enabled,
        handoff_mode=config.handoff_mode,
        live_transfer_number=config.live_transfer_number,
        escalation_rules=config.escalation_rules,
        default_greeting=config.default_greeting,
        disclosure_line=config.disclosure_line,
        notification_methods=config.notification_methods,
        notification_recipients=config.notification_recipients,
        after_hours_message=config.after_hours_message,
    )


@router.put("/settings", response_model=VoiceSettingsResponse)
async def update_voice_settings(
    settings_data: UpdateVoiceSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VoiceSettingsResponse:
    """Update voice settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    # Validate live transfer configuration
    if settings_data.handoff_mode == "live_transfer":
        if not settings_data.live_transfer_number:
            # Check if there's already a transfer number configured
            voice_config_service = VoiceConfigService(db)
            existing_config = await voice_config_service.get_voice_config(tenant_id)
            if not existing_config or not existing_config.live_transfer_number:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Live transfer mode requires a transfer phone number",
                )
    
    # Validate notification methods
    valid_methods = ["email", "sms", "in_app"]
    if settings_data.notification_methods:
        for method in settings_data.notification_methods:
            if method not in valid_methods:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid notification method: {method}. Valid methods: {valid_methods}",
                )
    
    voice_config_service = VoiceConfigService(db)
    config_data = VoiceConfigData(
        is_enabled=settings_data.is_enabled,
        handoff_mode=settings_data.handoff_mode,
        live_transfer_number=settings_data.live_transfer_number,
        escalation_rules=settings_data.escalation_rules,
        default_greeting=settings_data.default_greeting,
        disclosure_line=settings_data.disclosure_line,
        notification_methods=settings_data.notification_methods,
        notification_recipients=settings_data.notification_recipients,
        after_hours_message=settings_data.after_hours_message,
    )
    
    config = await voice_config_service.update_voice_config(tenant_id, config_data)
    
    return VoiceSettingsResponse(
        is_enabled=config.is_enabled,
        handoff_mode=config.handoff_mode,
        live_transfer_number=config.live_transfer_number,
        escalation_rules=config.escalation_rules,
        default_greeting=config.default_greeting,
        disclosure_line=config.disclosure_line,
        notification_methods=config.notification_methods,
        notification_recipients=config.notification_recipients,
        after_hours_message=config.after_hours_message,
    )


@router.get("/handoff", response_model=HandoffConfigResponse)
async def get_handoff_config(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HandoffConfigResponse:
    """Get handoff configuration for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    voice_config_service = VoiceConfigService(db)
    config = await voice_config_service.get_handoff_config(tenant_id)
    
    return HandoffConfigResponse(
        mode=config["mode"],
        transfer_number=config["transfer_number"],
        enabled=config["enabled"],
    )


@router.get("/escalation-rules", response_model=EscalationRulesResponse)
async def get_escalation_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationRulesResponse:
    """Get escalation rules for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    voice_config_service = VoiceConfigService(db)
    rules = await voice_config_service.get_escalation_rules(tenant_id)
    
    return EscalationRulesResponse(
        caller_asks_human=rules.get("caller_asks_human", True),
        repeated_confusion=rules.get("repeated_confusion", {"enabled": True, "threshold": 3}),
        high_value_intent=rules.get("high_value_intent", {"enabled": False, "intents": []}),
        low_confidence=rules.get("low_confidence", {"enabled": False, "threshold": 0.5}),
    )


@router.get("/notification-config", response_model=NotificationConfigResponse)
async def get_notification_config(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationConfigResponse:
    """Get notification configuration for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    voice_config_service = VoiceConfigService(db)
    config = await voice_config_service.get_notification_config(tenant_id)
    
    return NotificationConfigResponse(
        methods=config["methods"],
        recipients=config["recipients"],
    )


@router.get("/greeting-disclosure")
async def get_greeting_and_disclosure(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get greeting and disclosure text for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )
    
    voice_config_service = VoiceConfigService(db)
    config = await voice_config_service.get_greeting_and_disclosure(tenant_id)
    
    return config

