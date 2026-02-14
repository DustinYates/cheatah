"""Admin routes for global admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.api.schemas.tenant import (
    AdminTenantResponse,
    AdminTenantUpdate,
    TenantConfigDetailResponse,
    TenantCreate,
    TenantOverviewStats,
    TenantServiceStatus,
    TenantServicesOverview,
    TenantsOverviewResponse,
)
from app.persistence.database import get_db
from app.persistence.models.call import Call
from app.persistence.models.contact import Contact
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import Tenant, User
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.tenant_widget_config import TenantWidgetConfig
from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository
from app.persistence.repositories.tenant_repository import TenantRepository

router = APIRouter()


# --- Jackrabbit API Keys schemas ---

class JackrabbitKeysResponse(BaseModel):
    """Response schema for Jackrabbit API keys."""
    tenant_id: int
    key_1_configured: bool
    key_2_configured: bool
    key_1_masked: str | None = None
    key_2_masked: str | None = None

    class Config:
        from_attributes = True


class JackrabbitKeysUpdate(BaseModel):
    """Update schema for Jackrabbit API keys."""
    jackrabbit_api_key_1: str | None = None
    jackrabbit_api_key_2: str | None = None


def _tenant_to_response(tenant: Tenant) -> AdminTenantResponse:
    """Convert a Tenant model to AdminTenantResponse."""
    return AdminTenantResponse(
        id=tenant.id,
        tenant_number=tenant.tenant_number,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        end_date=tenant.end_date.isoformat() if tenant.end_date else None,
        tier=tenant.tier,
        call_minutes_limit=tenant.call_minutes_limit,
        sms_limit=tenant.sms_limit,
    )


@router.post("/tenants", response_model=AdminTenantResponse)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Create a new tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.create(
        None,  # No tenant_id for tenant creation
        name=tenant_data.name,
        subdomain=tenant_data.subdomain,
        is_active=tenant_data.is_active,
    )
    return _tenant_to_response(tenant)


@router.get("/tenants", response_model=list[AdminTenantResponse])
async def list_tenants(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> list[AdminTenantResponse]:
    """List all tenants."""
    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.list_all(skip=skip, limit=limit)
    return [_tenant_to_response(t) for t in tenants]


@router.get("/tenants/overview", response_model=TenantsOverviewResponse)
async def get_tenants_overview(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(7, ge=1, le=30, description="Number of days for usage stats"),
) -> TenantsOverviewResponse:
    """Get high-level overview stats for all tenants (master admin only)."""
    from datetime import datetime, timedelta
    from app.persistence.models.tenant_email_config import TenantEmailConfig
    from app.persistence.models.anomaly_alert import AnomalyAlert
    from app.persistence.models.service_health_incident import ServiceHealthIncident
    from app.persistence.models.sms_burst_incident import SmsBurstIncident

    # Calculate date range for filtered queries
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.list_all(skip=0, limit=1000)

    # Get stats for each tenant in efficient batch queries
    tenant_ids = [t.id for t in tenants]

    # Query conversation counts per tenant
    conv_counts_query = (
        select(Conversation.tenant_id, func.count(Conversation.id))
        .where(Conversation.tenant_id.in_(tenant_ids))
        .group_by(Conversation.tenant_id)
    )
    conv_result = await db.execute(conv_counts_query)
    conv_counts = {row[0]: row[1] for row in conv_result}

    # Query lead counts per tenant
    lead_counts_query = (
        select(Lead.tenant_id, func.count(Lead.id))
        .where(Lead.tenant_id.in_(tenant_ids))
        .group_by(Lead.tenant_id)
    )
    lead_result = await db.execute(lead_counts_query)
    lead_counts = {row[0]: row[1] for row in lead_result}

    # Query contact counts per tenant (excluding deleted)
    contact_counts_query = (
        select(Contact.tenant_id, func.count(Contact.id))
        .where(Contact.tenant_id.in_(tenant_ids))
        .where(Contact.deleted_at.is_(None))
        .group_by(Contact.tenant_id)
    )
    contact_result = await db.execute(contact_counts_query)
    contact_counts = {row[0]: row[1] for row in contact_result}

    # Query last activity (most recent message) per tenant
    last_activity_query = (
        select(Conversation.tenant_id, func.max(Message.created_at))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id.in_(tenant_ids))
        .group_by(Conversation.tenant_id)
    )
    activity_result = await db.execute(last_activity_query)
    last_activities = {row[0]: row[1].isoformat() if row[1] else None for row in activity_result}

    # Query Gmail status per tenant
    email_config_query = (
        select(
            TenantEmailConfig.tenant_id,
            TenantEmailConfig.gmail_email,
            TenantEmailConfig.gmail_refresh_token,
            TenantEmailConfig.watch_expiration,
        )
        .where(TenantEmailConfig.tenant_id.in_(tenant_ids))
    )
    email_result = await db.execute(email_config_query)
    email_configs = {}
    now = datetime.utcnow()
    for row in email_result:
        gmail_connected = bool(row.gmail_email and row.gmail_refresh_token)
        gmail_watch_active = bool(row.watch_expiration and row.watch_expiration > now)
        email_configs[row.tenant_id] = {
            "gmail_connected": gmail_connected,
            "gmail_email": row.gmail_email if gmail_connected else None,
            "gmail_watch_active": gmail_watch_active,
        }

    # Query SMS config (Telnyx phone numbers and enabled status) per tenant
    sms_config_query = (
        select(
            TenantSmsConfig.tenant_id,
            TenantSmsConfig.telnyx_phone_number,
            TenantSmsConfig.voice_phone_number,
            TenantSmsConfig.is_enabled,
        )
        .where(TenantSmsConfig.tenant_id.in_(tenant_ids))
    )
    sms_config_result = await db.execute(sms_config_query)
    sms_configs = {}
    sms_service_status = {}
    for row in sms_config_result:
        phone_numbers = []
        if row.telnyx_phone_number:
            phone_numbers.append(row.telnyx_phone_number)
        if row.voice_phone_number and row.voice_phone_number != row.telnyx_phone_number:
            phone_numbers.append(row.voice_phone_number)
        sms_configs[row.tenant_id] = phone_numbers
        sms_service_status[row.tenant_id] = {
            "enabled": row.is_enabled or False,
            "configured": len(phone_numbers) > 0,
        }

    # Query SMS message counts (incoming/outgoing) per tenant - filtered by date
    # Incoming = user messages in SMS conversations
    sms_incoming_query = (
        select(Conversation.tenant_id, func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id.in_(tenant_ids))
        .where(Conversation.channel == "sms")
        .where(Message.role == "user")
        .where(Message.created_at >= start_date)
        .group_by(Conversation.tenant_id)
    )
    sms_incoming_result = await db.execute(sms_incoming_query)
    sms_incoming_counts = {row[0]: row[1] for row in sms_incoming_result}

    # Outgoing = assistant messages in SMS conversations
    sms_outgoing_query = (
        select(Conversation.tenant_id, func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id.in_(tenant_ids))
        .where(Conversation.channel == "sms")
        .where(Message.role == "assistant")
        .where(Message.created_at >= start_date)
        .group_by(Conversation.tenant_id)
    )
    sms_outgoing_result = await db.execute(sms_outgoing_query)
    sms_outgoing_counts = {row[0]: row[1] for row in sms_outgoing_result}

    # Query call stats (count and total duration) per tenant - filtered by date
    call_stats_query = (
        select(
            Call.tenant_id,
            func.count(Call.id),
            func.coalesce(func.sum(Call.duration), 0),
        )
        .where(Call.tenant_id.in_(tenant_ids))
        .where(func.coalesce(Call.started_at, Call.created_at) >= start_date)
        .group_by(Call.tenant_id)
    )
    call_stats_result = await db.execute(call_stats_query)
    call_stats = {row[0]: {"count": row[1], "duration_seconds": row[2]} for row in call_stats_result}

    # Query chatbot leads count per tenant (source is chatbot, web_chat, or web_chat_lead)
    # Note: extra_data is JSON, use PostgreSQL ->> operator for text extraction
    chatbot_leads_query = (
        select(Lead.tenant_id, func.count(Lead.id))
        .where(Lead.tenant_id.in_(tenant_ids))
        .where(
            Lead.extra_data.op('->>')('source').in_(["chatbot", "web_chat", "web_chat_lead"])
        )
        .group_by(Lead.tenant_id)
    )
    chatbot_leads_result = await db.execute(chatbot_leads_query)
    chatbot_leads_counts = {row[0]: row[1] for row in chatbot_leads_result}

    # Query Voice config per tenant
    voice_config_query = (
        select(
            TenantVoiceConfig.tenant_id,
            TenantVoiceConfig.is_enabled,
            TenantVoiceConfig.live_transfer_number,
        )
        .where(TenantVoiceConfig.tenant_id.in_(tenant_ids))
    )
    voice_result = await db.execute(voice_config_query)
    voice_service_status = {}
    for row in voice_result:
        # Voice is configured if the tenant has a phone number capable of voice
        sms_cfg = sms_configs.get(row.tenant_id, [])
        has_phone = len(sms_cfg) > 0
        voice_service_status[row.tenant_id] = {
            "enabled": row.is_enabled or False,
            "configured": has_phone,
        }

    # Query Widget config per tenant
    widget_config_query = (
        select(
            TenantWidgetConfig.tenant_id,
            TenantWidgetConfig.settings,
        )
        .where(TenantWidgetConfig.tenant_id.in_(tenant_ids))
    )
    widget_result = await db.execute(widget_config_query)
    widget_service_status = {
        row.tenant_id: {
            "enabled": row.settings is not None and len(row.settings) > 0,
            "configured": row.settings is not None and len(row.settings) > 0,
        }
        for row in widget_result
    }

    # Query Customer Service config per tenant
    cs_config_query = (
        select(
            TenantCustomerServiceConfig.tenant_id,
            TenantCustomerServiceConfig.is_enabled,
            TenantCustomerServiceConfig.zapier_webhook_url,
        )
        .where(TenantCustomerServiceConfig.tenant_id.in_(tenant_ids))
    )
    cs_result = await db.execute(cs_config_query)
    cs_service_status = {
        row.tenant_id: {
            "enabled": row.is_enabled or False,
            "configured": bool(row.zapier_webhook_url),
        }
        for row in cs_result
    }

    # Query Prompt config per tenant
    prompt_config_query = (
        select(
            TenantPromptConfig.tenant_id,
            TenantPromptConfig.is_active,
            TenantPromptConfig.validated_at,
        )
        .where(TenantPromptConfig.tenant_id.in_(tenant_ids))
    )
    prompt_result = await db.execute(prompt_config_query)
    prompt_service_status = {
        row.tenant_id: {
            "enabled": row.is_active or False,
            "configured": row.validated_at is not None,
        }
        for row in prompt_result
    }

    # Query active alerts across all alert types
    # AnomalyAlert counts
    anomaly_query = (
        select(
            AnomalyAlert.tenant_id,
            func.count(AnomalyAlert.id).label("count"),
            func.max(
                case(
                    (AnomalyAlert.severity == "critical", 3),
                    (AnomalyAlert.severity == "warning", 2),
                    else_=1
                )
            ).label("max_severity")
        )
        .where(AnomalyAlert.tenant_id.in_(tenant_ids))
        .where(AnomalyAlert.status == "active")
        .group_by(AnomalyAlert.tenant_id)
    )
    anomaly_result = await db.execute(anomaly_query)
    anomaly_counts = {row[0]: {"count": row[1], "severity": row[2]} for row in anomaly_result}

    # ServiceHealthIncident counts (tenant-specific only)
    health_query = (
        select(
            ServiceHealthIncident.tenant_id,
            func.count(ServiceHealthIncident.id).label("count"),
            func.max(
                case(
                    (ServiceHealthIncident.severity == "critical", 3),
                    (ServiceHealthIncident.severity == "warning", 2),
                    else_=1
                )
            ).label("max_severity")
        )
        .where(ServiceHealthIncident.tenant_id.in_(tenant_ids))
        .where(ServiceHealthIncident.status == "active")
        .group_by(ServiceHealthIncident.tenant_id)
    )
    health_result = await db.execute(health_query)
    health_counts = {row[0]: {"count": row[1], "severity": row[2]} for row in health_result}

    # SmsBurstIncident counts
    burst_query = (
        select(
            SmsBurstIncident.tenant_id,
            func.count(SmsBurstIncident.id).label("count"),
            func.max(
                case(
                    (SmsBurstIncident.severity == "critical", 3),
                    (SmsBurstIncident.severity == "warning", 2),
                    else_=1
                )
            ).label("max_severity")
        )
        .where(SmsBurstIncident.tenant_id.in_(tenant_ids))
        .where(SmsBurstIncident.status == "active")
        .group_by(SmsBurstIncident.tenant_id)
    )
    burst_result = await db.execute(burst_query)
    burst_counts = {row[0]: {"count": row[1], "severity": row[2]} for row in burst_result}

    # Helper to combine alert counts
    def get_tenant_alerts(tid: int) -> tuple[int, str | None]:
        total = 0
        max_sev = 0
        for counts_dict in [anomaly_counts, health_counts, burst_counts]:
            if tid in counts_dict:
                total += counts_dict[tid]["count"]
                max_sev = max(max_sev, counts_dict[tid]["severity"])
        severity_map = {3: "critical", 2: "warning", 1: "info"}
        return total, severity_map.get(max_sev)

    # Build response
    tenant_stats = []
    active_count = 0
    for tenant in tenants:
        if tenant.is_active:
            active_count += 1
        email_info = email_configs.get(tenant.id, {})
        call_info = call_stats.get(tenant.id, {"count": 0, "duration_seconds": 0})
        # Build services overview for this tenant
        sms_status = sms_service_status.get(tenant.id, {"enabled": False, "configured": False})
        voice_status = voice_service_status.get(tenant.id, {"enabled": False, "configured": False})
        widget_status = widget_service_status.get(tenant.id, {"enabled": False, "configured": False})
        cs_status = cs_service_status.get(tenant.id, {"enabled": False, "configured": False})
        prompt_status = prompt_service_status.get(tenant.id, {"enabled": False, "configured": False})

        services_overview = TenantServicesOverview(
            sms=TenantServiceStatus(
                enabled=sms_status["enabled"],
                configured=sms_status["configured"],
            ),
            voice=TenantServiceStatus(
                enabled=voice_status["enabled"],
                configured=voice_status["configured"],
            ),
            email=TenantServiceStatus(
                enabled=email_info.get("gmail_connected", False),
                configured=email_info.get("gmail_watch_active", False),
            ),
            widget=TenantServiceStatus(
                enabled=widget_status["enabled"],
                configured=widget_status["configured"],
            ),
            customer_service=TenantServiceStatus(
                enabled=cs_status["enabled"],
                configured=cs_status["configured"],
            ),
            prompt=TenantServiceStatus(
                enabled=prompt_status["enabled"],
                configured=prompt_status["configured"],
            ),
        )

        # Get alert data for this tenant
        alert_count, alert_severity = get_tenant_alerts(tenant.id)

        tenant_stats.append(
            TenantOverviewStats(
                id=tenant.id,
                tenant_number=tenant.tenant_number,
                name=tenant.name,
                subdomain=tenant.subdomain,
                is_active=tenant.is_active,
                tier=tenant.tier,
                total_conversations=conv_counts.get(tenant.id, 0),
                total_leads=lead_counts.get(tenant.id, 0),
                total_contacts=contact_counts.get(tenant.id, 0),
                last_activity=last_activities.get(tenant.id),
                gmail_connected=email_info.get("gmail_connected", False),
                gmail_email=email_info.get("gmail_email"),
                gmail_watch_active=email_info.get("gmail_watch_active", False),
                telnyx_phone_numbers=sms_configs.get(tenant.id, []),
                sms_incoming_count=sms_incoming_counts.get(tenant.id, 0),
                sms_outgoing_count=sms_outgoing_counts.get(tenant.id, 0),
                call_count=call_info["count"],
                call_minutes=round(call_info["duration_seconds"] / 60, 1),
                chatbot_leads_count=chatbot_leads_counts.get(tenant.id, 0),
                services=services_overview,
                active_alerts_count=alert_count,
                alert_severity=alert_severity,
            )
        )

    # Sort by last activity (most recent first), then by name
    tenant_stats.sort(
        key=lambda t: (t.last_activity or "", t.name),
        reverse=True,
    )

    return TenantsOverviewResponse(
        tenants=tenant_stats,
        total_tenants=len(tenants),
        active_tenants=active_count,
    )


@router.get("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def get_tenant(
    tenant_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Get a tenant by ID."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return _tenant_to_response(tenant)


@router.put("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_update: AdminTenantUpdate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Update tenant admin fields."""
    tenant_repo = TenantRepository(db)
    update_data = {}
    fields_set = tenant_update.model_fields_set
    if "tenant_number" in fields_set:
        update_data["tenant_number"] = tenant_update.tenant_number
    if "end_date" in fields_set:
        update_data["end_date"] = tenant_update.end_date
    if "tier" in fields_set:
        update_data["tier"] = tenant_update.tier
    if "name" in fields_set:
        update_data["name"] = tenant_update.name
    if "is_active" in fields_set:
        update_data["is_active"] = tenant_update.is_active
    if "call_minutes_limit" in fields_set:
        update_data["call_minutes_limit"] = tenant_update.call_minutes_limit
    if "sms_limit" in fields_set:
        update_data["sms_limit"] = tenant_update.sms_limit

    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return _tenant_to_response(tenant)


@router.get("/tenants/{tenant_id}/config", response_model=TenantConfigDetailResponse)
async def get_tenant_config_detail(
    tenant_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantConfigDetailResponse:
    """Get detailed configuration for a tenant's services."""
    from datetime import datetime
    from app.persistence.models.tenant_email_config import TenantEmailConfig

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    now = datetime.utcnow()

    # SMS config
    sms_result = await db.execute(
        select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
    )
    sms_cfg = sms_result.scalar_one_or_none()
    sms_data = None
    if sms_cfg:
        sms_data = {
            "phone": sms_cfg.telnyx_phone_number,
            "voice_phone": sms_cfg.voice_phone_number,
            "api_key_configured": bool(sms_cfg.telnyx_api_key),
            "messaging_profile_id": sms_cfg.telnyx_messaging_profile_id,
            "enabled": sms_cfg.is_enabled or False,
        }

    # Voice config
    voice_result = await db.execute(
        select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == tenant_id)
    )
    voice_cfg = voice_result.scalar_one_or_none()
    voice_data = None
    if voice_cfg:
        voice_data = {
            "agent_id": voice_cfg.telnyx_agent_id,
            "voice_agent_id": voice_cfg.voice_agent_id,
            "handoff_mode": voice_cfg.handoff_mode,
            "transfer_number": voice_cfg.live_transfer_number,
            "enabled": voice_cfg.is_enabled or False,
        }

    # Email config
    email_result = await db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
    )
    email_cfg = email_result.scalar_one_or_none()
    email_data = None
    if email_cfg:
        email_data = {
            "gmail_email": email_cfg.gmail_email,
            "gmail_connected": bool(email_cfg.gmail_refresh_token),
            "watch_active": bool(email_cfg.watch_expiration and email_cfg.watch_expiration > now),
            "sendgrid_configured": bool(email_cfg.sendgrid_api_key),
        }

    # Widget config
    widget_result = await db.execute(
        select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant_id)
    )
    widget_cfg = widget_result.scalar_one_or_none()
    widget_data = None
    if widget_cfg:
        widget_data = {
            "enabled": widget_cfg.settings is not None and len(widget_cfg.settings) > 0,
            "settings_count": len(widget_cfg.settings) if widget_cfg.settings else 0,
        }

    # Customer service config
    cs_result = await db.execute(
        select(TenantCustomerServiceConfig).where(TenantCustomerServiceConfig.tenant_id == tenant_id)
    )
    cs_cfg = cs_result.scalar_one_or_none()
    cs_data = None
    if cs_cfg:
        cs_data = {
            "enabled": cs_cfg.is_enabled or False,
            "zapier_configured": bool(cs_cfg.zapier_webhook_url),
            "jackrabbit_key1_configured": bool(cs_cfg.jackrabbit_api_key_1),
            "jackrabbit_key2_configured": bool(cs_cfg.jackrabbit_api_key_2),
        }

    # Prompt config
    prompt_result = await db.execute(
        select(TenantPromptConfig).where(TenantPromptConfig.tenant_id == tenant_id)
    )
    prompt_cfg = prompt_result.scalar_one_or_none()
    prompt_data = None
    if prompt_cfg:
        prompt_data = {
            "active": prompt_cfg.is_active or False,
            "validated_at": prompt_cfg.validated_at.isoformat() if prompt_cfg.validated_at else None,
        }

    return TenantConfigDetailResponse(
        tenant_id=tenant_id,
        tenant_name=tenant.name,
        sms=sms_data,
        voice=voice_data,
        email=email_data,
        widget=widget_data,
        customer_service=cs_data,
        prompt=prompt_data,
    )


def _mask_key(key: str | None) -> str | None:
    """Mask an API key for display, showing only last 8 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "••••" + key
    return "••••" + key[-8:]


@router.get("/tenants/{tenant_id}/jackrabbit-keys", response_model=JackrabbitKeysResponse)
async def get_jackrabbit_keys(
    tenant_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JackrabbitKeysResponse:
    """Get Jackrabbit API key status for a tenant."""
    config_repo = CustomerServiceConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)

    if not config:
        return JackrabbitKeysResponse(
            tenant_id=tenant_id,
            key_1_configured=False,
            key_2_configured=False,
        )

    return JackrabbitKeysResponse(
        tenant_id=tenant_id,
        key_1_configured=bool(config.jackrabbit_api_key_1),
        key_2_configured=bool(config.jackrabbit_api_key_2),
        key_1_masked=_mask_key(config.jackrabbit_api_key_1),
        key_2_masked=_mask_key(config.jackrabbit_api_key_2),
    )


@router.put("/tenants/{tenant_id}/jackrabbit-keys", response_model=JackrabbitKeysResponse)
async def update_jackrabbit_keys(
    tenant_id: int,
    keys_update: JackrabbitKeysUpdate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JackrabbitKeysResponse:
    """Set or update Jackrabbit API keys for a tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    config_repo = CustomerServiceConfigRepository(db)
    update_data = {}
    if keys_update.jackrabbit_api_key_1 is not None:
        update_data["jackrabbit_api_key_1"] = keys_update.jackrabbit_api_key_1 or None
    if keys_update.jackrabbit_api_key_2 is not None:
        update_data["jackrabbit_api_key_2"] = keys_update.jackrabbit_api_key_2 or None

    config = await config_repo.create_or_update(tenant_id, **update_data)

    return JackrabbitKeysResponse(
        tenant_id=tenant_id,
        key_1_configured=bool(config.jackrabbit_api_key_1),
        key_2_configured=bool(config.jackrabbit_api_key_2),
        key_1_masked=_mask_key(config.jackrabbit_api_key_1),
        key_2_masked=_mask_key(config.jackrabbit_api_key_2),
    )


@router.delete("/tenants/{tenant_id}/jackrabbit-keys/{key_number}")
async def delete_jackrabbit_key(
    tenant_id: int,
    key_number: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JackrabbitKeysResponse:
    """Delete a specific Jackrabbit API key (1 or 2) for a tenant."""
    if key_number not in (1, 2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="key_number must be 1 or 2",
        )

    config_repo = CustomerServiceConfigRepository(db)
    config = await config_repo.get_by_tenant_id(tenant_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jackrabbit keys configured for this tenant",
        )

    field = f"jackrabbit_api_key_{key_number}"
    setattr(config, field, None)
    await db.commit()
    await db.refresh(config)

    return JackrabbitKeysResponse(
        tenant_id=tenant_id,
        key_1_configured=bool(config.jackrabbit_api_key_1),
        key_2_configured=bool(config.jackrabbit_api_key_2),
        key_1_masked=_mask_key(config.jackrabbit_api_key_1),
        key_2_masked=_mask_key(config.jackrabbit_api_key_2),
    )


# --- Call Duration Backfill ---


class BackfillCallDurationResponse(BaseModel):
    """Response schema for call duration backfill."""
    total_calls_found: int
    calls_updated: int
    calls_failed: int
    details: list[dict]


@router.post("/backfill-call-durations")
async def backfill_call_durations(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: int | None = None,
    limit: int = 100,
) -> BackfillCallDurationResponse:
    """Backfill call durations for calls with missing duration data.

    This endpoint finds calls where:
    - duration is 0 or NULL
    - started_at equals ended_at (or ended_at is NULL)

    For each call, it attempts to calculate the duration from the Telnyx API
    using the conversation timestamps or message timestamps.

    Args:
        tenant_id: Optional tenant ID to filter calls
        limit: Maximum number of calls to process (default 100)
    """
    import logging
    from datetime import timedelta
    from app.infrastructure.telephony.telnyx_provider import TelnyxAIService

    logger = logging.getLogger(__name__)

    # Find calls with missing duration data
    query = select(Call).where(
        (Call.duration == 0) | (Call.duration.is_(None)),
        (Call.ended_at.is_(None)) | (Call.ended_at == Call.started_at),
    ).order_by(Call.created_at.desc()).limit(limit)

    if tenant_id:
        query = query.where(Call.tenant_id == tenant_id)

    result = await db.execute(query)
    calls = result.scalars().all()

    logger.info(f"Found {len(calls)} calls with missing duration data")

    updated = 0
    failed = 0
    details = []

    # Get unique tenant IDs for API key lookup
    tenant_ids = set(call.tenant_id for call in calls)

    # Fetch Telnyx API keys for each tenant
    tenant_api_keys = {}
    for tid in tenant_ids:
        config_result = await db.execute(
            select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tid)
        )
        config = config_result.scalar_one_or_none()
        if config and config.telnyx_api_key:
            tenant_api_keys[tid] = config.telnyx_api_key

    for call in calls:
        api_key = tenant_api_keys.get(call.tenant_id)
        if not api_key:
            details.append({
                "call_id": call.id,
                "status": "skipped",
                "reason": "no_api_key",
            })
            failed += 1
            continue

        try:
            telnyx_ai = TelnyxAIService(api_key)

            # Try to find conversation by call_sid (call_control_id)
            conv_data = await telnyx_ai.find_conversation_by_call_control_id(call.call_sid)

            if conv_data:
                # Try created_at/updated_at timestamps first
                conv_created = conv_data.get("created_at")
                conv_updated = conv_data.get("updated_at")

                if conv_created and conv_updated and conv_created != conv_updated:
                    from dateutil import parser as date_parser
                    start_dt = date_parser.parse(str(conv_created))
                    end_dt = date_parser.parse(str(conv_updated))
                    calculated_duration = int((end_dt - start_dt).total_seconds())

                    if calculated_duration > 0:
                        call.duration = calculated_duration
                        call.started_at = start_dt.replace(tzinfo=None)
                        call.ended_at = end_dt.replace(tzinfo=None)
                        updated += 1
                        details.append({
                            "call_id": call.id,
                            "status": "updated",
                            "duration": calculated_duration,
                            "source": "conversation_timestamps",
                        })
                        continue

                # Fallback: try message timestamps
                conv_id = conv_data.get("id")
                if conv_id:
                    msgs = await telnyx_ai.get_conversation_messages(conv_id)
                    if msgs and len(msgs) >= 2:
                        # Messages are returned newest-first, so use last element as start
                        first_ts = msgs[-1].get("created_at") or msgs[-1].get("timestamp")
                        last_ts = msgs[0].get("created_at") or msgs[0].get("timestamp")

                        if first_ts and last_ts:
                            from dateutil import parser as date_parser
                            start_dt = date_parser.parse(str(first_ts))
                            end_dt = date_parser.parse(str(last_ts))
                            calculated_duration = int((end_dt - start_dt).total_seconds())

                            if calculated_duration > 0:
                                call.duration = calculated_duration
                                call.started_at = start_dt.replace(tzinfo=None)
                                call.ended_at = end_dt.replace(tzinfo=None)
                                updated += 1
                                details.append({
                                    "call_id": call.id,
                                    "status": "updated",
                                    "duration": calculated_duration,
                                    "source": "message_timestamps",
                                })
                                continue

            # If we got here, we couldn't calculate duration
            details.append({
                "call_id": call.id,
                "status": "skipped",
                "reason": "no_conversation_found" if not conv_data else "no_timestamps",
            })
            failed += 1

        except Exception as e:
            logger.warning(f"Failed to backfill call {call.id}: {e}")
            details.append({
                "call_id": call.id,
                "status": "error",
                "reason": str(e),
            })
            failed += 1

    # Commit updates
    await db.commit()

    return BackfillCallDurationResponse(
        total_calls_found=len(calls),
        calls_updated=updated,
        calls_failed=failed,
        details=details,
    )
