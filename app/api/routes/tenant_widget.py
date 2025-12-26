"""Tenant widget customization endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_tenant
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.tenant_widget_config import TenantWidgetConfig

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
        "cooldownDays": 0
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
