"""API routes for managing escalation settings."""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_tenant
from app.persistence.database import get_db
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.models.tenant import TenantBusinessProfile

logger = logging.getLogger(__name__)

router = APIRouter()


class QuietHours(BaseModel):
    """Quiet hours configuration - when alerts should be suppressed."""

    enabled: bool = Field(default=False, description="Whether quiet hours are enabled")
    start_time: str = Field(default="22:00", description="Start time in HH:MM format (24-hour)")
    end_time: str = Field(default="07:00", description="End time in HH:MM format (24-hour)")
    days: list[str] = Field(
        default=["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        description="Days when quiet hours apply",
    )
    timezone: str = Field(default="America/Chicago", description="Timezone for quiet hours")


class EscalationSettings(BaseModel):
    """Escalation settings configuration."""

    enabled: bool = Field(default=True, description="Whether escalation alerts are enabled")
    notification_methods: list[str] = Field(
        default=["email", "sms"],
        description="Notification methods: email, sms, in_app",
    )
    custom_keywords: list[str] = Field(
        default=[],
        description="Additional custom keywords that trigger escalation",
    )
    alert_phone_override: str | None = Field(
        default=None,
        description="Override phone number for SMS alerts (uses business profile phone if not set)",
    )
    quiet_hours: QuietHours = Field(default_factory=QuietHours, description="Quiet hours configuration")


class EscalationSettingsResponse(BaseModel):
    """Response containing escalation settings."""

    settings: EscalationSettings
    business_phone: str | None = None
    has_config: bool


class UpdateQuietHoursRequest(BaseModel):
    """Request to update quiet hours."""

    enabled: bool = False
    start_time: str = "22:00"
    end_time: str = "07:00"
    days: list[str] = Field(default=["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"])
    timezone: str = "America/Chicago"


class UpdateEscalationSettingsRequest(BaseModel):
    """Request to update escalation settings."""

    enabled: bool = True
    notification_methods: list[str] = Field(default=["email", "sms"])
    custom_keywords: list[str] = Field(default=[])
    alert_phone_override: str | None = None
    quiet_hours: UpdateQuietHoursRequest | None = None


@router.get("/settings", response_model=EscalationSettingsResponse)
async def get_escalation_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> EscalationSettingsResponse:
    """Get escalation settings for the current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Get business profile phone
    stmt = select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
    result = await db.execute(stmt)
    business_profile = result.scalar_one_or_none()
    business_phone = business_profile.phone_number if business_profile else None

    # Get tenant prompt config
    stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    prompt_config = result.scalar_one_or_none()

    if not prompt_config or not prompt_config.config_json:
        return EscalationSettingsResponse(
            settings=EscalationSettings(),
            business_phone=business_phone,
            has_config=False,
        )

    config = prompt_config.config_json
    if isinstance(config, str):
        config = json.loads(config)

    escalation_settings = config.get("escalation_settings", {})

    quiet_hours_data = escalation_settings.get("quiet_hours", {})
    quiet_hours = QuietHours(
        enabled=quiet_hours_data.get("enabled", False),
        start_time=quiet_hours_data.get("start_time", "22:00"),
        end_time=quiet_hours_data.get("end_time", "07:00"),
        days=quiet_hours_data.get("days", ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]),
        timezone=quiet_hours_data.get("timezone", "America/Chicago"),
    )

    return EscalationSettingsResponse(
        settings=EscalationSettings(
            enabled=escalation_settings.get("enabled", True),
            notification_methods=escalation_settings.get("notification_methods", ["email", "sms"]),
            custom_keywords=escalation_settings.get("custom_keywords", []),
            alert_phone_override=escalation_settings.get("alert_phone_override"),
            quiet_hours=quiet_hours,
        ),
        business_phone=business_phone,
        has_config=True,
    )


@router.put("/settings", response_model=dict)
async def update_escalation_settings(
    request: UpdateEscalationSettingsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> dict[str, Any]:
    """Update escalation settings."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Validate notification methods
    valid_methods = ["email", "sms", "in_app"]
    for method in request.notification_methods:
        if method not in valid_methods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification method: {method}. Must be one of: {', '.join(valid_methods)}",
            )

    # Get or create tenant prompt config
    stmt = select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    prompt_config = result.scalar_one_or_none()

    if not prompt_config:
        # Create new prompt config
        prompt_config = TenantPromptConfig(
            tenant_id=tenant_id,
            config_json={},
            schema_version="v1",
            business_type="general",
            is_active=True,
        )
        db.add(prompt_config)

    # Update config_json with escalation settings
    config = prompt_config.config_json or {}
    if isinstance(config, str):
        config = json.loads(config)

    escalation_data = {
        "enabled": request.enabled,
        "notification_methods": request.notification_methods,
        "custom_keywords": request.custom_keywords,
        "alert_phone_override": request.alert_phone_override,
    }

    if request.quiet_hours:
        escalation_data["quiet_hours"] = {
            "enabled": request.quiet_hours.enabled,
            "start_time": request.quiet_hours.start_time,
            "end_time": request.quiet_hours.end_time,
            "days": request.quiet_hours.days,
            "timezone": request.quiet_hours.timezone,
        }

    config["escalation_settings"] = escalation_data

    prompt_config.config_json = config
    flag_modified(prompt_config, "config_json")
    await db.commit()

    logger.info(f"Updated escalation settings for tenant {tenant_id}")

    return {
        "status": "success",
        "message": "Escalation settings saved successfully",
    }


@router.get("/keywords", response_model=dict)
async def get_default_keywords(
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> dict[str, Any]:
    """Get the default escalation keywords used by the system."""
    # These are the keywords from the EscalationService
    default_keywords = [
        "speak to human",
        "talk to person",
        "real person",
        "agent",
        "representative",
        "manager",
        "supervisor",
        "escalate",
    ]

    return {
        "default_keywords": default_keywords,
        "description": "These keywords are always active and cannot be removed. You can add custom keywords in addition to these.",
    }
