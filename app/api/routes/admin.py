"""Admin routes for global admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.api.schemas.tenant import (
    AdminTenantResponse,
    AdminTenantUpdate,
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
from app.persistence.repositories.tenant_repository import TenantRepository

router = APIRouter()


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
) -> TenantsOverviewResponse:
    """Get high-level overview stats for all tenants (master admin only)."""
    from datetime import datetime
    from app.persistence.models.tenant_email_config import TenantEmailConfig

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

    # Query SMS message counts (incoming/outgoing) per tenant
    # Incoming = user messages in SMS conversations
    sms_incoming_query = (
        select(Conversation.tenant_id, func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id.in_(tenant_ids))
        .where(Conversation.channel == "sms")
        .where(Message.role == "user")
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
        .group_by(Conversation.tenant_id)
    )
    sms_outgoing_result = await db.execute(sms_outgoing_query)
    sms_outgoing_counts = {row[0]: row[1] for row in sms_outgoing_result}

    # Query call stats (count and total duration) per tenant
    call_stats_query = (
        select(
            Call.tenant_id,
            func.count(Call.id),
            func.coalesce(func.sum(Call.duration), 0),
        )
        .where(Call.tenant_id.in_(tenant_ids))
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
    voice_service_status = {
        row.tenant_id: {
            "enabled": row.is_enabled or False,
            "configured": bool(row.live_transfer_number),
        }
        for row in voice_result
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

    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return _tenant_to_response(tenant)
