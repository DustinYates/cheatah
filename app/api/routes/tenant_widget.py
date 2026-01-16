"""Tenant widget customization endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant
from app.infrastructure.widget_asset_storage import (
    MAX_FILE_SIZE_BYTES,
    widget_asset_storage,
    WidgetAssetStorageError,
)
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_widget_config import TenantWidgetConfig

logger = logging.getLogger(__name__)

router = APIRouter()


# Default settings
DEFAULT_SETTINGS = {
    "colors": {
        "primary": "#007bff",
        "secondary": "#6c757d",
        "background": "#ffffff",
        "text": "#333333",
        "buttonText": "#ffffff",
        "linkColor": "#007bff",
        "borderColor": "#ddd"
    },
    "typography": {
        "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif",
        "fontSize": "14px",
        "fontWeight": "400",
        "lineHeight": "1.5",
        "letterSpacing": "normal"
    },
    "layout": {
        "borderRadius": "10px",
        "boxShadow": "0 4px 20px rgba(0,0,0,0.15)",
        "shadowColor": "rgba(0,0,0,0.15)",
        "opacity": "1",
        "position": "bottom-right",
        "zIndex": "10000",
        "maxWidth": "350px",
        "maxHeight": "500px"
    },
    "behavior": {
        "openBehavior": "click",
        "autoOpenDelay": 0,
        "showOnPages": "*",
        "cooldownDays": 0,
        "autoOpenMessageEnabled": False,
        "autoOpenMessage": ""
    },
    "animations": {
        "type": "none",
        "duration": "0.3s",
        "easing": "ease-in-out"
    },
    "messages": {
        "welcomeMessage": "Chat with us",
        "placeholder": "Type your message...",
        "sendButtonText": "Send"
    },
    "accessibility": {
        "darkMode": False,
        "highContrast": False,
        "focusOutline": True
    },
    "icon": {
        "type": "emoji",
        "emoji": "💬",
        "imageUrl": "",
        "imageSource": "url",  # "upload" or "url"
        "imageAssetId": None,  # UUID of uploaded asset
        "imageAssetUrl": None,  # Public URL of uploaded asset
        "shape": "circle",
        "customBorderRadius": "50%",
        "size": "medium",
        "customSize": "60px",
        "showLabel": False,
        "labelText": "",
        "labelPosition": "inside",
        "labelBackgroundColor": "#ffffff",
        "labelTextColor": "#333333",
        "labelFontSize": "12px",
        "fallbackToEmoji": True
    },
    "attention": {
        "attentionAnimation": "none",
        "attentionCycles": 2,
        "unreadDot": False,
        "unreadDotColor": "#ff3b30",
        "unreadDotPosition": "top-right"
    },
    "motion": {
        "launcherVisibility": "immediate",
        "entryAnimation": "none",
        "openAnimation": "none",
        "delaySeconds": 8,
        "scrollPercent": 35,
        "exitIntentEnabled": False,
        "exitIntentAction": "show"
    },
    "microInteractions": {
        "typingIndicator": False,
        "typingIndicatorDurationMs": 1200,
        "blinkCursor": False,
        "hoverEffect": "scale",
        "buttonAnimation": "none"
    },
    "copy": {
        "launcherPromptsEnabled": False,
        "launcherPrompts": [
            "Have a question?",
            "Need help right now?",
            "Get a quick answer"
        ],
        "launcherPromptRotateSeconds": 6,
        "contextualPromptsEnabled": False,
        "contextualPrompts": [
            {"match": "/pricing", "text": "Want help choosing a plan?"},
            {"match": "/contact", "text": "Prefer texting instead?"}
        ],
        "greetingEnabled": False,
        "greetingMode": "time",
        "greetingMorning": "Good morning! How can we help?",
        "greetingAfternoon": "Good afternoon! How can we help?",
        "greetingEvening": "Good evening! How can we help?",
        "greetingPageRules": []
    },
    "sound": {
        "chimeOnOpen": False,
        "messageTicks": False,
        "hapticFeedback": False,
        "volume": 0.2
    },
    "socialProof": {
        "showResponseTime": False,
        "responseTimeText": "Typically replies in under 1 min",
        "availabilityText": "",
        "showAvatar": False,
        "avatarUrl": "",
        "agentName": "Cheetah Assistant"
    },
    "rules": {
        "animateOncePerSession": True,
        "stopAfterInteraction": True,
        "maxAnimationSeconds": 3,
        "respectReducedMotion": True,
        "disableOnMobile": False
    }
}


# Request/Response Models

class WidgetSettingsResponse(BaseModel):
    """Widget settings response."""
    colors: dict
    typography: dict
    layout: dict
    behavior: dict
    animations: dict
    messages: dict
    accessibility: dict
    icon: dict
    attention: dict
    motion: dict
    microInteractions: dict
    copy: dict
    sound: dict
    socialProof: dict
    rules: dict


class UpdateWidgetSettingsRequest(BaseModel):
    """Request to update widget settings."""
    colors: dict | None = None
    typography: dict | None = None
    layout: dict | None = None
    behavior: dict | None = None
    animations: dict | None = None
    messages: dict | None = None
    accessibility: dict | None = None
    icon: dict | None = None
    attention: dict | None = None
    motion: dict | None = None
    microInteractions: dict | None = None
    copy: dict | None = None
    sound: dict | None = None
    socialProof: dict | None = None
    rules: dict | None = None


# Endpoints

@router.get("/settings", response_model=WidgetSettingsResponse)
async def get_widget_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WidgetSettingsResponse:
    """Get widget settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config or not config.settings:
        # Return defaults if no config exists
        return WidgetSettingsResponse(**DEFAULT_SETTINGS)

    # Merge saved settings with defaults (in case new fields were added)
    merged_settings = DEFAULT_SETTINGS.copy()
    for key in DEFAULT_SETTINGS.keys():
        if key in config.settings:
            merged_settings[key] = {**DEFAULT_SETTINGS[key], **config.settings[key]}

    return WidgetSettingsResponse(**merged_settings)


@router.put("/settings", response_model=WidgetSettingsResponse)
async def update_widget_settings(
    settings_data: UpdateWidgetSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WidgetSettingsResponse:
    """Update widget settings for current tenant."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    # Build new settings by merging provided values with defaults
    new_settings = DEFAULT_SETTINGS.copy()
    for key in DEFAULT_SETTINGS.keys():
        value = getattr(settings_data, key, None)
        if value is not None:
            new_settings[key] = {**DEFAULT_SETTINGS[key], **value}

    if not config:
        # Create new config
        config = TenantWidgetConfig(
            tenant_id=tenant_id,
            settings=new_settings,
        )
        db.add(config)
    else:
        # Update existing config
        config.settings = new_settings

    await db.commit()
    await db.refresh(config)

    return WidgetSettingsResponse(**new_settings)


@router.get("/settings/public", response_model=WidgetSettingsResponse)
async def get_widget_settings_public(
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
) -> WidgetSettingsResponse:
    """Get widget settings for a tenant (public endpoint for widget to fetch).

    This endpoint does NOT require authentication and is called by the widget
    when it loads on a customer's website.
    """
    stmt = select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config or not config.settings:
        # Return defaults if no config exists
        return WidgetSettingsResponse(**DEFAULT_SETTINGS)

    # Merge saved settings with defaults
    merged_settings = DEFAULT_SETTINGS.copy()
    for key in DEFAULT_SETTINGS.keys():
        if key in config.settings:
            merged_settings[key] = {**DEFAULT_SETTINGS[key], **config.settings[key]}

    return WidgetSettingsResponse(**merged_settings)


# Asset Upload Models
class AssetUploadResponse(BaseModel):
    """Response from asset upload."""
    asset_id: str
    public_url: str
    content_type: str
    size_bytes: int


@router.post("/assets", response_model=AssetUploadResponse)
async def upload_widget_asset(
    file: Annotated[UploadFile, File(description="Image file to upload")],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
) -> AssetUploadResponse:
    """Upload a widget asset (icon image).

    Accepts PNG, JPG, WebP, or SVG files up to 1 MB.
    Returns the asset ID and public URL for use in widget settings.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file",
        )

    # Validate file size
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum of {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    # Upload to GCS
    try:
        result = await widget_asset_storage.upload_asset(
            tenant_id=tenant_id,
            file_data=content,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename,
        )
        logger.info(f"Widget asset uploaded for tenant {tenant_id}: {result['asset_id']}")
        return AssetUploadResponse(**result)

    except WidgetAssetStorageError as e:
        logger.warning(f"Widget asset upload failed for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error uploading widget asset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload asset",
        )
